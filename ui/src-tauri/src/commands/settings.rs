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

use crate::commands::engine::{sidecar_url, with_token_pub};
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
pub struct AppSettings {
    /// "synthetic" o "reddit".
    pub fetcher_mode: String,
    pub credentials: CredentialsSummary,
    pub env_path: String,
    /// Cuantos posts trae el corpus de demostracion.
    pub synthetic_posts: i64,
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

fn unreachable(err: reqwest::Error) -> RadarError {
    if err.is_connect() {
        RadarError::Sidecar(format!(
            "El sidecar Python no responde en {}. Sin el no se puede leer ni \
             guardar la configuracion.",
            sidecar_url()
        ))
    } else {
        RadarError::Sidecar(format!("Fallo hablando con el sidecar: {err}"))
    }
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
    .map_err(unreachable)?;

    response.json().await.map_err(unreachable)
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
    .map_err(unreachable)?;

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
    .map_err(unreachable)?;

    if !response.status().is_success() {
        let detail = response.text().await.unwrap_or_default();
        return Err(RadarError::Sidecar(format!(
            "No se pudieron guardar las credenciales: {detail}"
        )));
    }

    #[derive(Deserialize)]
    struct Envelope {
        credentials: CredentialsSummary,
    }

    let envelope: Envelope = response.json().await.map_err(unreachable)?;
    Ok(envelope.credentials)
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
    .map_err(unreachable)?;

    response.json().await.map_err(unreachable)
}
