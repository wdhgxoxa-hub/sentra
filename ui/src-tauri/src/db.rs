//! Acceso a PostgreSQL.
//!
//! Las lecturas del panel las resuelve Rust directamente contra la base:
//! abrir el dashboard no debe cruzar dos procesos y un serializador para
//! hacer un SELECT. El sidecar Python queda para lo que solo el sabe hacer
//! (ejecutar el grafo, generar embeddings, busqueda hibrida sobre LanceDB).

use std::sync::{PoisonError, RwLock};
use std::time::Duration;

use sqlx::postgres::{PgConnectOptions, PgPool, PgPoolOptions};

/// DSN por defecto, alineado con `core/storage/postgres_store.py`: el rol de
/// SENTRA, no el superusuario. Su contrasena esta en el pgpass propio.
const DEFAULT_DSN: &str =
    "postgres://sentra_owner@localhost:5432/reddit_intelligence_radar";

const DSN_ENV_VAR: &str = "RIR_PG_URL";

/// Puerto del DSN por defecto (fase 2, contenedores), el mismo nombre que en
/// Python (`core/storage/postgres_store.py`). Solo cambia el puerto: la
/// contrasena sigue saliendo del pgpass de SENTRA, de la linea de ese puerto.
const PORT_ENV_VAR: &str = "RIR_PG_PORT";
const PUERTO_POR_DEFECTO: u16 = 5432;

/// El puerto pedido: un numero de 1 a 65535; vacio o invalido, 5432 (con aviso
/// si habia algo).
fn puerto_desde(valor: Option<&str>) -> u16 {
    let valor = valor.unwrap_or_default().trim();
    if valor.is_empty() {
        return PUERTO_POR_DEFECTO;
    }
    match valor.parse::<u16>() {
        Ok(puerto) if puerto > 0 && valor.bytes().all(|b| b.is_ascii_digit()) => puerto,
        _ => {
            log::warn!("{PORT_ENV_VAR}={valor:?} no es un puerto valido; se usa {PUERTO_POR_DEFECTO}");
            PUERTO_POR_DEFECTO
        }
    }
}

/// El DSN por defecto con el puerto indicado.
fn opciones_por_defecto(puerto: u16) -> PgConnectOptions {
    DEFAULT_DSN
        .parse::<PgConnectOptions>()
        .expect("el DSN por defecto debe ser valido")
        .port(puerto)
}

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

/// Credenciales de conexion, en cascada.
///
/// 1. `RIR_PG_URL`, si esta definida.
/// 2. El DSN por defecto (rol `sentra_owner`; puerto de `RIR_PG_PORT`, 5432
///    sin ella) con la contrasena del pgpass
///    propio de SENTRA. sqlx, a diferencia de libpq, no lee pgpass solo. El
///    pgpass.conf que comparten los proyectos no se lee: el 2026-09-24 otro
///    proyecto lo reescribio y SENTRA se quedo sin base (y antes se tomaba
///    su primera linea, fuera del usuario que fuera).
/// 3. Sin contrasena en el pgpass propio, el DSN por defecto tal cual.
pub fn connect_options() -> PgConnectOptions {
    if let Ok(url) = std::env::var(DSN_ENV_VAR) {
        if let Ok(options) = url.parse::<PgConnectOptions>() {
            return options;
        }
        log::warn!("{DSN_ENV_VAR} no es una URL valida; se ignora");
    }

    let puerto = puerto_desde(std::env::var(PORT_ENV_VAR).ok().as_deref());
    let options = opciones_por_defecto(puerto);
    let clave = ruta_pgpass()
        .and_then(|ruta| std::fs::read_to_string(ruta).ok())
        .and_then(|contenido| {
            contrasena_en_pgpass(
                &contenido,
                options.get_host(),
                options.get_port(),
                options.get_database().unwrap_or_default(),
                options.get_username(),
            )
        });
    match clave {
        Some(clave) => {
            log::info!("Credenciales de PostgreSQL tomadas del pgpass de SENTRA");
            options.password(&clave)
        }
        None => options,
    }
}

/// El pgpass propio de SENTRA: `pgpass.conf` en su carpeta local, la misma
/// ruta que `core/rutas.py` (`ruta_pgpass`). El motor la recibe en `PGPASSFILE`.
pub fn ruta_pgpass() -> Option<std::path::PathBuf> {
    Some(carpeta_local()?.join("pgpass.conf"))
}

/// Carpeta local de SENTRA, la misma que `core/rutas.py` (`carpeta_local`):
/// `%LOCALAPPDATA%\SENTRA` en Windows; en Linux `$XDG_DATA_HOME/SENTRA` o
/// `~/.local/share/SENTRA`. Nunca `~/.cache`: un limpiador de caché se
/// llevaría el modelo e5 y el pgpass (como %TEMP% en AUD2-010).
pub fn carpeta_local() -> Option<std::path::PathBuf> {
    carpeta_local_desde(
        std::env::var_os("LOCALAPPDATA"),
        std::env::var_os("XDG_DATA_HOME"),
        std::env::var_os("HOME"),
    )
}

/// La regla de `carpeta_local` sin leer el entorno. Una variable vacía (o
/// solo espacios, como el `strip()` de Python) cuenta como ausente; una
/// `XDG_DATA_HOME` relativa se ignora, como pide la especificación XDG.
fn carpeta_local_desde(
    local: Option<std::ffi::OsString>,
    xdg: Option<std::ffi::OsString>,
    home: Option<std::ffi::OsString>,
) -> Option<std::path::PathBuf> {
    use std::path::PathBuf;
    let con_valor = |v: Option<std::ffi::OsString>| match v?.into_string() {
        Ok(t) if t.trim().is_empty() => None,
        Ok(t) => Some(PathBuf::from(t.trim())),
        Err(crudo) => Some(PathBuf::from(crudo)),
    };
    if let Some(local) = con_valor(local) {
        return Some(local.join("SENTRA"));
    }
    if let Some(xdg) = con_valor(xdg).filter(|x| x.is_absolute()) {
        return Some(xdg.join("SENTRA"));
    }
    Some(PathBuf::from(home?).join(".local").join("share").join("SENTRA"))
}

/// La contrasena de `usuario` en un pgpass, con las reglas de libpq: campos
/// `host:puerto:base:usuario:contrasena`, `*` como comodin en los cuatro
/// primeros, `\:` y `\\` escapados y gana la primera linea que encaja. Solo
/// la del usuario pedido: nunca la de otro.
pub fn contrasena_en_pgpass(
    contenido: &str,
    host: &str,
    puerto: u16,
    base: &str,
    usuario: &str,
) -> Option<String> {
    let puerto = puerto.to_string();
    contenido
        .lines()
        .filter(|linea| !linea.trim_start().starts_with('#'))
        .filter_map(campos_de_pgpass)
        .find(|c| {
            [host, puerto.as_str(), base, usuario]
                .iter()
                .zip(c.iter())
                .all(|(pedido, campo)| campo == "*" || campo == pedido)
        })
        .map(|c| c[4].clone())
}

/// Los cinco campos de una linea de pgpass, sin escapes; `None` si no hay cinco.
fn campos_de_pgpass(linea: &str) -> Option<[String; 5]> {
    let mut campos = vec![String::new()];
    let mut letras = linea.trim_end_matches(['\r', '\n']).chars();
    while let Some(c) = letras.next() {
        match c {
            '\\' => campos.last_mut()?.push(letras.next().unwrap_or('\\')),
            ':' if campos.len() < 5 => campos.push(String::new()),
            _ => campos.last_mut()?.push(c),
        }
    }
    campos.try_into().ok()
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
    use std::ffi::OsString;
    use std::path::PathBuf;

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

    /// El archivo compartido del 2026-09-24: otros proyectos delante. Antes se
    /// tomaba la primera linea de localhost, fuera de quien fuera.
    const COMPARTIDO: &str = "localhost:5432:*:faceless:f\nlocalhost:5432:*:dsfactory:d\n";

    #[test]
    fn el_pgpass_solo_da_la_contrasena_de_su_usuario() {
        let propio = format!("{COMPARTIDO}localhost:5432:reddit_intelligence_radar:sentra_owner:s\n");
        let clave = |contenido: &str| {
            contrasena_en_pgpass(contenido, "localhost", 5432, "reddit_intelligence_radar", "sentra_owner")
        };
        assert_eq!(clave(&propio).as_deref(), Some("s"));
        assert_eq!(clave(COMPARTIDO), None);
    }

    #[test]
    fn el_pgpass_sigue_las_reglas_de_libpq() {
        // Comodines, `\:` y `\\` escapados, comentarios y la primera que encaja.
        let contenido = "# comentario\nlocalhost:5432:otra:sentra_owner:no\n*:*:*:sentra_owner:a\\:b\\\\c\nlocalhost:5432:*:sentra_owner:tarde\n";
        assert_eq!(
            contrasena_en_pgpass(contenido, "localhost", 5432, "reddit_intelligence_radar", "sentra_owner").as_deref(),
            Some("a:b\\c")
        );
        assert_eq!(contrasena_en_pgpass(contenido, "localhost", 5432, "x", "otro"), None);
    }

    #[test]
    fn el_pgpass_de_sentra_vive_en_su_carpeta_local() {
        // Sin tocar el entorno: los tests corren en paralelo.
        let carpeta = carpeta_local().expect("la carpeta local sale en Windows y en Linux");
        assert_eq!(ruta_pgpass(), Some(carpeta.join("pgpass.conf")));
    }

    fn os(valor: &str) -> Option<OsString> {
        Some(OsString::from(valor))
    }

    #[test]
    fn la_carpeta_local_es_la_misma_que_en_python() {
        // Mismos casos que tests/test_ruta_modelos.py (core.rutas.carpeta_local).
        let ruta = |local, xdg, home| carpeta_local_desde(local, xdg, home);
        let p = PathBuf::from;
        // Windows: %LOCALAPPDATA%\SENTRA, gane a lo que haya de XDG.
        assert_eq!(ruta(os("C:/x"), os("/datos/xdg"), os("/home/u")), Some(p("C:/x").join("SENTRA")));
        // Linux: $XDG_DATA_HOME/SENTRA si es absoluta.
        assert_eq!(ruta(None, os("/datos/xdg"), os("/home/u")), Some(p("/datos/xdg/SENTRA")));
        // Relativa o vacía no vale: ~/.local/share/SENTRA. Nunca ~/.cache.
        assert_eq!(ruta(None, os("relativa/xdg"), os("/home/u")), Some(p("/home/u/.local/share/SENTRA")));
        assert_eq!(ruta(os(""), os(""), os("/home/u")), Some(p("/home/u/.local/share/SENTRA")));
        assert_eq!(ruta(None, None, None), None);
    }

    #[test]
    fn el_dsn_por_defecto_usa_el_rol_de_sentra() {
        let opciones: PgConnectOptions = DEFAULT_DSN.parse().unwrap();
        assert_eq!(opciones.get_username(), "sentra_owner");
    }

    #[test]
    fn el_puerto_sale_de_rir_pg_port_como_en_python() {
        // Mismos casos que tests/test_puerto_pg.py (core.storage.postgres_store.puerto_pg).
        assert_eq!(PORT_ENV_VAR, "RIR_PG_PORT");
        assert_eq!(puerto_desde(None), 5432);
        assert_eq!(puerto_desde(Some("")), 5432);
        assert_eq!(puerto_desde(Some("5438")), 5438);
        assert_eq!(puerto_desde(Some(" 5438 ")), 5438);
        for malo in ["abc", "0", "70000", "-5", "54 38"] {
            assert_eq!(puerto_desde(Some(malo)), 5432, "{malo}");
        }
    }

    #[test]
    fn el_puerto_solo_cambia_el_puerto_del_dsn_por_defecto() {
        let opciones = opciones_por_defecto(5438);
        assert_eq!(opciones.get_port(), 5438);
        assert_eq!(opciones.get_host(), "localhost");
        assert_eq!(opciones.get_username(), "sentra_owner");
        assert_eq!(opciones.get_database(), Some("reddit_intelligence_radar"));
        assert_eq!(opciones_por_defecto(5432).get_port(), 5432);
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
