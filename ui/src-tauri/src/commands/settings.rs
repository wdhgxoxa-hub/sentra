//! Comandos de configuracion.
//!
//! Delegan en el sidecar: la configuracion vive en su `.env`. Rust no la
//! toca ni la cachea, para que no haya dos versiones de la verdad. Ningun
//! comando devuelve un secreto. El cambio de fuente y las credenciales de
//! Reddit del escaner antiguo se retiraron (C2, D-C5).

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::commands::engine::{sidecar_url, transport_error, with_token_pub};
use crate::db::{AppState, RadarError, RadarResult};

const TIMEOUT: std::time::Duration = std::time::Duration::from_secs(30);

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CredentialsSummary {
    pub configured: bool,
    pub client_id_masked: String,
    pub user_agent: String,
    pub has_user: bool,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GeminiSummary {
    pub configured: bool,
    /// Clave recortada. La entera no sale nunca del sidecar.
    pub key_masked: String,
    /// Modelo de documentos guardado; `None` = automático (el Pro 3.x más reciente).
    pub model: Option<String>,
    /// Modelo general guardado; `None` = automático (el Flash 3.x estable más reciente).
    pub general_model: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppSettings {
    /// "synthetic" o "reddit".
    pub fetcher_mode: String,
    pub credentials: CredentialsSummary,
    pub env_path: String,
    /// Cuantos posts trae el corpus de demostracion.
    pub synthetic_posts: i64,
    /// Estado del motor de arquitectura.
    pub gemini: GeminiSummary,
}

/// Estado actual: fuente de datos y credenciales (sin secretos).
#[tauri::command]
pub async fn get_settings(state: State<'_, AppState>) -> RadarResult<AppSettings> {
    let response = with_token_pub(
        state
            .http
            .get(format!("{}/api/config", sidecar_url()))
            .timeout(TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;

    response.json().await.map_err(transport_error)
}

/// `{"detail": {"code", "detail"}}` de FastAPI como error del motor.
pub(crate) fn rechazo_con_codigo(cuerpo: &str) -> Option<RadarError> {
    let valor: serde_json::Value = serde_json::from_str(cuerpo).ok()?;
    let detalle = valor.get("detail")?;
    Some(RadarError::Motor {
        code: detalle.get("code")?.as_str()?.to_string(),
        detail: detalle.get("detail")?.as_str()?.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn un_rechazo_con_codigo_llega_como_error_del_motor() {
        let cuerpo = r#"{"detail": {"code": "reddit_user_agent_invalid", "detail": "formato"}}"#;
        let error = rechazo_con_codigo(cuerpo).expect("deberia reconocer el codigo");
        assert_eq!(error.code(), "reddit_user_agent_invalid");
        assert_eq!(error.to_string(), "formato");
    }

    #[test]
    fn un_rechazo_sin_codigo_no_se_inventa_uno() {
        assert!(rechazo_con_codigo(r#"{"detail": "No puede estar vacio"}"#).is_none());
        assert!(rechazo_con_codigo("Internal Server Error").is_none());
    }
}
