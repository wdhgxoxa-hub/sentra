//! Acceso a PostgreSQL.
//!
//! Las lecturas del panel las resuelve Rust directamente contra la base:
//! abrir el dashboard no debe cruzar dos procesos y un serializador para
//! hacer un SELECT. El sidecar Python queda para lo que solo el sabe hacer
//! (ejecutar el grafo, generar embeddings, busqueda hibrida sobre LanceDB).

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
    pub pool: PgPool,
    pub http: reqwest::Client,
}

#[derive(Debug, thiserror::Error)]
pub enum RadarError {
    #[error("error de base de datos: {0}")]
    Database(#[from] sqlx::Error),

    #[error("{0}")]
    Sidecar(String),

    /// Datos que el usuario puede corregir: un estado desconocido, un
    /// nombre vacio. Se distingue de los fallos de infraestructura porque
    /// la interfaz debe tratarlos de otra manera.
    #[error("{0}")]
    Invalid(String),

    /// Guardar en disco lo que se exporta (AUD-008): la ruta o la escritura
    /// fallaron del lado del sistema de archivos, no del motor.
    #[error("{0}")]
    Archivo(String),
}

/// Tauri necesita serializar el error para devolverlo al WebView.
impl serde::Serialize for RadarError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
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

/// Abre el pool de conexiones.
///
/// `search_path` se fija en la propia conexion para que las consultas no
/// tengan que cualificar cada tabla con el esquema.
pub async fn create_pool() -> Result<PgPool, sqlx::Error> {
    PgPoolOptions::new()
        .max_connections(5)
        .after_connect(|conn, _meta| {
            Box::pin(async move {
                sqlx::query("SET search_path = radar, public")
                    .execute(conn)
                    .await?;
                Ok(())
            })
        })
        .connect_with(connect_options())
        .await
}
