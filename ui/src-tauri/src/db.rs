//! Acceso a PostgreSQL.
//!
//! Las lecturas del panel las resuelve Rust directamente contra la base:
//! abrir el dashboard no debe cruzar dos procesos y un serializador para
//! hacer un SELECT. El sidecar Python queda para lo que solo el sabe hacer
//! (ejecutar el grafo, generar embeddings, busqueda hibrida sobre LanceDB).

use sqlx::postgres::{PgPool, PgPoolOptions};

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

/// Abre el pool de conexiones.
///
/// `search_path` se fija en la propia conexion para que las consultas no
/// tengan que cualificar cada tabla con el esquema.
pub async fn create_pool() -> Result<PgPool, sqlx::Error> {
    let dsn = std::env::var(DSN_ENV_VAR).unwrap_or_else(|_| DEFAULT_DSN.to_string());

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
        .connect(&dsn)
        .await
}
