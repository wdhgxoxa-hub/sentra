//! Acceso a PostgreSQL.
//!
//! Las lecturas del panel las resuelve Rust directamente contra la base:
//! abrir el dashboard no debe cruzar dos procesos y un serializador para
//! hacer un SELECT. El sidecar Python queda para lo que solo el sabe hacer
//! (ejecutar el grafo, generar embeddings, busqueda hibrida sobre LanceDB).

use std::sync::{PoisonError, RwLock};
use std::time::Duration;

use sqlx::postgres::{PgConnectOptions, PgPool, PgPoolOptions};

/// DSN por defecto, alineado con `core/storage/postgres_store.py`.
const DEFAULT_DSN: &str =
    "postgres://postgres@localhost:5432/reddit_intelligence_radar";

const DSN_ENV_VAR: &str = "RIR_PG_URL";

/// Estado compartido de la aplicacion, accesible desde cualquier comando.
///
/// El cliente HTTP se crea una vez y se reutiliza: reqwest mantiene su
/// propio pool de conexiones, y construir uno por peticion desperdiciaria
/// el handshake con el sidecar.
pub struct AppState {
    pub db: Database,
    pub http: reqwest::Client,
}

/// Fallo de un comando. Llega a la interfaz como `{code, detail}` (D-A):
/// `code` es estable y se traduce; `detail` es tecnico y solo se muestra
/// plegado, bajo «Detalles tecnicos».
#[derive(Debug, thiserror::Error)]
pub enum RadarError {
    #[error("error de base de datos: {0}")]
    Database(#[from] sqlx::Error),

    /// No hay conexion con PostgreSQL: no respondio al arrancar ni en el
    /// ultimo reintento (D-F). Se guarda el motivo para enseñarlo.
    #[error("{0}")]
    DatabaseUnavailable(String),

    /// El motor Python respondio con un fallo sin codigo propio.
    #[error("{0}")]
    Sidecar(String),

    /// El motor Python no acepta conexiones: no esta arrancado.
    #[error("{0}")]
    SidecarUnreachable(String),

    /// El motor Python no respondio a tiempo.
    #[error("{0}")]
    SidecarTimeout(String),

    /// Datos que el usuario puede corregir: un estado desconocido, un
    /// nombre vacio. Se distingue de los fallos de infraestructura porque
    /// la interfaz debe tratarlos de otra manera.
    #[error("{0}")]
    Invalid(String),

    /// Guardar en disco lo que se exporta (AUD-008): la ruta o la escritura
    /// fallaron del lado del sistema de archivos, no del motor.
    #[error("{0}")]
    Archivo(String),

    /// Fallo con codigo propio del motor (Gemini, el plan de arquitectura):
    /// el codigo llega tal cual y lo traduce la interfaz.
    #[error("{detail}")]
    Motor { code: String, detail: String },
}

impl RadarError {
    /// Codigo estable que la interfaz traduce (`errors.<code>` en i18n).
    pub fn code(&self) -> &str {
        match self {
            RadarError::Database(_) => "database",
            RadarError::DatabaseUnavailable(_) => "database_unavailable",
            RadarError::Sidecar(_) => "sidecar",
            RadarError::SidecarUnreachable(_) => "sidecar_unreachable",
            RadarError::SidecarTimeout(_) => "sidecar_timeout",
            RadarError::Invalid(_) => "invalid_input",
            RadarError::Archivo(_) => "file",
            RadarError::Motor { code, .. } => code,
        }
    }
}

/// Tauri necesita serializar el error para devolverlo al WebView.
impl serde::Serialize for RadarError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        use serde::ser::SerializeStruct;

        let mut error = serializer.serialize_struct("RadarError", 2)?;
        error.serialize_field("code", self.code())?;
        error.serialize_field("detail", &self.to_string())?;
        error.end()
    }
}

pub type RadarResult<T> = Result<T, RadarError>;

/// Base de datos por defecto del radar.
const DEFAULT_DATABASE: &str = "reddit_intelligence_radar";

/// Credenciales de conexion, en cascada.
///
/// 1. `RIR_PG_URL`, si esta definida.
/// 2. El `pgpass.conf` del usuario. sqlx, a diferencia de libpq, no lo lee
///    solo; y en una instalacion normal de PostgreSQL en Windows es ahi
///    donde vive la contrasena. Sin este paso la aplicacion no arranca en
///    una maquina perfectamente configurada.
/// 3. El DSN por defecto, sin contrasena (servidor con `trust`).
pub fn connect_options() -> PgConnectOptions {
    if let Ok(url) = std::env::var(DSN_ENV_VAR) {
        if let Ok(options) = url.parse::<PgConnectOptions>() {
            return options;
        }
        log::warn!("{DSN_ENV_VAR} no es una URL valida; se ignora");
    }

    if let Some(options) = options_from_pgpass(DEFAULT_DATABASE) {
        log::info!("Credenciales de PostgreSQL tomadas de pgpass.conf");
        return options;
    }

    DEFAULT_DSN
        .parse::<PgConnectOptions>()
        .expect("el DSN por defecto debe ser valido")
}

/// Busca en `pgpass.conf` una entrada para el servidor local.
///
/// Formato: `host:puerto:base:usuario:contrasena`. Se acepta cualquier
/// entrada de localhost, sea cual sea el usuario: quien la puso ahi sabe
/// con que credenciales quiere conectarse.
pub fn options_from_pgpass(database: &str) -> Option<PgConnectOptions> {
    let appdata = std::env::var("APPDATA").ok()?;
    let path = std::path::Path::new(&appdata)
        .join("postgresql")
        .join("pgpass.conf");
    let content = std::fs::read_to_string(path).ok()?;

    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }

        // La contrasena puede contener ':', asi que solo se parten los
        // cuatro primeros campos.
        let parts: Vec<&str> = line.splitn(5, ':').collect();
        if parts.len() != 5 || parts[0] != "localhost" {
            continue;
        }

        return Some(
            PgConnectOptions::new()
                .host("localhost")
                .port(parts[1].parse().unwrap_or(5432))
                .username(parts[3])
                .password(parts[4])
                .database(database),
        );
    }
    None
}

/// Cuanto se espera a PostgreSQL al conectar. Sin limite, sqlx insiste 30 s
/// antes de rendirse, y la ventana tardaria eso en aparecer.
const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);

/// Estado de la conexion tal como lo ve la interfaz (D-F).
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DatabaseStatus {
    pub connected: bool,
    /// Codigo traducible del fallo; `None` si hay conexion.
    pub code: Option<String>,
    /// Detalle tecnico del fallo, para «Detalles tecnicos».
    pub detail: Option<String>,
}

/// La base de datos de la aplicacion, que puede no estar disponible.
///
/// Antes el arranque hacia `expect` sobre el pool: sin PostgreSQL la app se
/// cerraba sin llegar a abrir ventana. Ahora arranca igual, cada comando que
/// necesita la base recibe `database_unavailable` y la interfaz enseña una
/// pantalla de estado con «Reintentar».
pub struct Database {
    estado: RwLock<Result<PgPool, String>>,
}

impl Database {
    /// Intenta conectar. Nunca falla: un fallo queda guardado como estado.
    pub async fn conectar(opciones: PgConnectOptions) -> Self {
        Self {
            estado: RwLock::new(Self::abrir(opciones).await),
        }
    }

    async fn abrir(opciones: PgConnectOptions) -> Result<PgPool, String> {
        create_pool_with(opciones).await.map_err(|err| {
            log::warn!("PostgreSQL no disponible: {err}");
            err.to_string()
        })
    }

    /// El pool, o `database_unavailable` si no hay conexion.
    pub fn pool(&self) -> RadarResult<PgPool> {
        match &*self.estado.read().unwrap_or_else(PoisonError::into_inner) {
            Ok(pool) => Ok(pool.clone()),
            Err(detalle) => Err(RadarError::DatabaseUnavailable(detalle.clone())),
        }
    }

    pub fn status(&self) -> DatabaseStatus {
        match self.pool() {
            Ok(_) => DatabaseStatus {
                connected: true,
                code: None,
                detail: None,
            },
            Err(error) => DatabaseStatus {
                connected: false,
                code: Some(error.code().to_string()),
                detail: Some(error.to_string()),
            },
        }
    }

    /// Vuelve a intentar la conexion si no la hay. Con conexion no hace nada.
    pub async fn reintentar(&self, opciones: PgConnectOptions) -> DatabaseStatus {
        if self.pool().is_err() {
            let nuevo = Self::abrir(opciones).await;
            *self.estado.write().unwrap_or_else(PoisonError::into_inner) = nuevo;
        }
        self.status()
    }
}

/// Abre el pool de conexiones.
///
/// `search_path` se fija en la propia conexion para que las consultas no
/// tengan que cualificar cada tabla con el esquema.
async fn create_pool_with(opciones: PgConnectOptions) -> Result<PgPool, sqlx::Error> {
    PgPoolOptions::new()
        .max_connections(5)
        .acquire_timeout(CONNECT_TIMEOUT)
        .after_connect(|conn, _meta| {
            Box::pin(async move {
                sqlx::query("SET search_path = radar, public")
                    .execute(conn)
                    .await?;
                Ok(())
            })
        })
        .connect_with(opciones)
        .await
}

#[cfg(test)]
mod tests {
    use super::*;

    const ES: &str = include_str!("../../src/i18n/es.ts");
    const EN: &str = include_str!("../../src/i18n/en.ts");

    /// Un ejemplo de cada variante. El `match` de `ejemplo_de_cada_variante`
    /// no compila si aparece una variante nueva sin su ejemplo aqui.
    fn ejemplos() -> Vec<RadarError> {
        // `Motor` no entra: sus codigos los pone Python y los comprueba
        // tests/test_gemini_robustness.py contra el mismo bloque.
        let todos = vec![
            RadarError::Database(sqlx::Error::PoolClosed),
            RadarError::DatabaseUnavailable("x".into()),
            RadarError::Sidecar("x".into()),
            RadarError::SidecarUnreachable("x".into()),
            RadarError::SidecarTimeout("x".into()),
            RadarError::Invalid("x".into()),
            RadarError::Archivo("x".into()),
        ];
        for error in &todos {
            match error {
                RadarError::Database(_)
                | RadarError::DatabaseUnavailable(_)
                | RadarError::Sidecar(_)
                | RadarError::SidecarUnreachable(_)
                | RadarError::SidecarTimeout(_)
                | RadarError::Invalid(_)
                | RadarError::Archivo(_)
                | RadarError::Motor { .. } => {}
            }
        }
        todos
    }

    /// Claves del bloque `errors: { ... }` de un diccionario de la interfaz.
    fn traducidos(diccionario: &str) -> Vec<String> {
        let inicio = diccionario
            .find("\n  errors: {")
            .expect("el diccionario no tiene bloque errors");
        let bloque = &diccionario[inicio + 1..];
        let fin = bloque.find("\n  },").expect("bloque errors sin cerrar");
        bloque[..fin]
            .lines()
            .skip(1)
            .filter_map(|linea| {
                let linea = linea.trim_start();
                let (clave, _) = linea.split_once(':')?;
                clave
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_')
                    .then(|| clave.to_string())
            })
            .collect()
    }

    /// Nada escucha en el puerto 1: la conexion se rechaza al momento.
    const URL_SIN_BASE: &str = "postgres://nadie@127.0.0.1:1/nada";

    #[tokio::test]
    async fn sin_base_la_app_queda_sin_base_con_codigo_y_sin_panic() {
        let base = Database::conectar(URL_SIN_BASE.parse().unwrap()).await;
        let error = base.pool().expect_err("sin base no puede haber pool");
        assert_eq!(error.code(), "database_unavailable");

        let estado = base.status();
        assert!(!estado.connected);
        assert_eq!(estado.code.as_deref(), Some("database_unavailable"));
        assert!(estado.detail.is_some_and(|d| !d.is_empty()));
    }

    #[tokio::test]
    async fn reintentar_sin_base_sigue_sin_base_y_sin_panic() {
        let base = Database::conectar(URL_SIN_BASE.parse().unwrap()).await;
        let estado = base.reintentar(URL_SIN_BASE.parse().unwrap()).await;
        assert!(!estado.connected);
        assert_eq!(estado.code.as_deref(), Some("database_unavailable"));
    }

    #[test]
    fn el_error_llega_a_la_interfaz_como_codigo_y_detalle() {
        let json = serde_json::to_value(RadarError::Invalid("vacio".into())).unwrap();
        assert_eq!(json, serde_json::json!({"code": "invalid_input", "detail": "vacio"}));
    }

    #[test]
    fn cada_codigo_que_emite_rust_tiene_texto_en_es_y_en() {
        for (idioma, diccionario) in [("es", ES), ("en", EN)] {
            let claves = traducidos(diccionario);
            for error in ejemplos() {
                let json = serde_json::to_value(&error).unwrap();
                let codigo = json["code"].as_str().expect("sin code").to_string();
                assert!(claves.contains(&codigo), "{idioma}.ts no traduce '{codigo}'");
            }
        }
    }
}
