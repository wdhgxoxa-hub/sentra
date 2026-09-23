//! Comandos de configuracion.
//!
//! Todos delegan en el sidecar: las credenciales viven en su `.env` y la
//! fuente de datos es suya. Rust no las toca ni las cachea, para que no
//! haya dos versiones de la verdad.
//!
//! Ningun comando devuelve el secreto: el sidecar solo informa de si esta
//! configurado y de un Client ID enmascarado.

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

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CredentialsInput {
    pub client_id: String,
    pub client_secret: String,
    pub user_agent: String,
    pub username: Option<String>,
    pub password: Option<String>,
}

#[derive(Debug, Serialize)]
struct CredentialsBody {
    #[serde(rename = "clientId")]
    client_id: String,
    #[serde(rename = "clientSecret")]
    client_secret: String,
    #[serde(rename = "userAgent")]
    user_agent: String,
    username: Option<String>,
    password: Option<String>,
}

#[derive(Debug, Serialize)]
struct ModeBody {
    mode: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProbeResult {
    pub ok: bool,
    pub detail: String,
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

/// Cambia la fuente entre el corpus de demostracion y Reddit.
#[tauri::command]
pub async fn set_fetcher_mode(
    state: State<'_, AppState>,
    mode: String,
) -> RadarResult<String> {
    if mode != "synthetic" && mode != "reddit" {
        return Err(RadarError::Invalid(format!(
            "Fuente desconocida: '{mode}'. Admitidas: synthetic, reddit"
        )));
    }

    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/config/mode", sidecar_url()))
            .timeout(TIMEOUT)
            .json(&ModeBody { mode: mode.clone() }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    if !response.status().is_success() {
        return Err(RadarError::Sidecar(format!(
            "El sidecar rechazo el cambio de fuente ({})",
            response.status()
        )));
    }

    Ok(mode)
}

/// Guarda las credenciales de Reddit en el `.env` del proyecto.
#[tauri::command]
pub async fn save_reddit_credentials(
    state: State<'_, AppState>,
    credentials: CredentialsInput,
) -> RadarResult<CredentialsSummary> {
    if credentials.client_id.trim().is_empty() || credentials.client_secret.trim().is_empty() {
        return Err(RadarError::Invalid(
            "El Client ID y el Client Secret son obligatorios".into(),
        ));
    }

    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/credentials", sidecar_url()))
            .timeout(TIMEOUT)
            .json(&CredentialsBody {
                client_id: credentials.client_id,
                client_secret: credentials.client_secret,
                user_agent: credentials.user_agent,
                username: credentials.username.filter(|v| !v.trim().is_empty()),
                password: credentials.password.filter(|v| !v.trim().is_empty()),
            }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    if !response.status().is_success() {
        let detail = response.text().await.unwrap_or_default();
        // Un rechazo con codigo (p. ej. reddit_user_agent_invalid) viaja
        // tal cual para que la interfaz lo traduzca (AUD-014, D-A).
        return Err(rechazo_con_codigo(&detail).unwrap_or_else(|| {
            RadarError::Sidecar(format!("No se pudieron guardar las credenciales: {detail}"))
        }));
    }

    #[derive(Deserialize)]
    struct Envelope {
        credentials: CredentialsSummary,
    }

    let envelope: Envelope = response.json().await.map_err(transport_error)?;
    Ok(envelope.credentials)
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

/// Pide un token real a Reddit con lo que hay guardado.
#[tauri::command]
pub async fn test_reddit_connection(
    state: State<'_, AppState>,
) -> RadarResult<ProbeResult> {
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/credentials/test", sidecar_url()))
            .timeout(TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;

    response.json().await.map_err(transport_error)
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
