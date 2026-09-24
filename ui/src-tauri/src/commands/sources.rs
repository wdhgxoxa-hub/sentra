//! Fuentes (F2): estado verificado, credenciales, «Probar», encendido,
//! modo comercial y escaneo multifuente.
//!
//! Todo delega en el sidecar, que es quien guarda las credenciales en su
//! `.env` y quien habla con las APIs. Rust no devuelve nunca un secreto: la
//! tarjeta dice que credencial hay, no su valor.

use std::collections::BTreeMap;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, State};

use crate::commands::engine::{
    como_json, rechazo, relay_sse, sidecar_url, transport_error, with_token_pub,
};
use crate::db::{AppState, RadarError, RadarResult};

/// Canal por el que llega el progreso del escaneo multifuente.
pub const SOURCES_EVENT_CHANNEL: &str = "sources:events";

const TIMEOUT: Duration = Duration::from_secs(30);
/// «Probar» puede esperar un Retry-After (30 s como mucho) entre reintentos.
const PROBE_TIMEOUT: Duration = Duration::from_secs(120);

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SourceCredentialState {
    pub name: String,
    pub env_var: String,
    pub secret: bool,
    pub required: bool,
    pub configured: bool,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SourceCard {
    pub source: String,
    pub display_name: String,
    pub terms_url: String,
    pub commercial_use_allowed: bool,
    pub requires_credentials: bool,
    pub credential_fields: Vec<SourceCredentialState>,
    pub status: String,
    pub last_verified_at: Option<String>,
    pub error_code: Option<String>,
    pub detail: Option<String>,
    pub disabled: bool,
    pub excluded_by_commercial_mode: bool,
    pub active: bool,
    pub cost_unit: String,
    pub cost_note: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SourcesOverview {
    pub commercial_mode: bool,
    pub sources: Vec<SourceCard>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SourceProbeResult {
    pub ok: bool,
    pub code: Option<String>,
    pub detail: String,
    pub checked_at: Option<String>,
}

/// Perfil tal como lo envía la interfaz (camelCase).
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScanProfileParams {
    pub name: String,
    pub keywords: Vec<String>,
    pub discovery: bool,
    pub window_days: u32,
    pub languages: Vec<String>,
}

/// Perfil tal como lo valida el sidecar (ScanProfile, snake_case).
#[derive(Debug, Serialize)]
struct ScanProfileBody<'a> {
    name: &'a str,
    keywords: &'a [String],
    discovery: bool,
    window_days: u32,
    languages: &'a [String],
}

#[derive(Debug, Serialize)]
struct MultiScanBody<'a> {
    profile: ScanProfileBody<'a>,
}

#[derive(Debug, Serialize)]
struct EnabledBody {
    enabled: bool,
}

#[derive(Debug, Serialize)]
struct CredentialsBody<'a> {
    values: &'a BTreeMap<String, String>,
}

/// El id va en la ruta: solo minúsculas, dígitos y guion bajo.
fn fuente_valida(source: &str) -> RadarResult<&str> {
    let valida = !source.is_empty()
        && source.len() <= 40
        && source.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_');
    if valida {
        Ok(source)
    } else {
        Err(RadarError::Invalid(format!("Fuente desconocida: '{source}'")))
    }
}

/// Cada fuente con su estado verificado y el modo comercial.
#[tauri::command]
pub async fn list_sources(state: State<'_, AppState>) -> RadarResult<SourcesOverview> {
    let response = with_token_pub(
        state.http.get(format!("{}/api/sources", sidecar_url())).timeout(TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudieron leer las fuentes").await
}

/// Guarda credenciales de una fuente en el `.env` del sidecar.
#[tauri::command]
pub async fn save_source_credentials(
    state: State<'_, AppState>,
    source: String,
    values: BTreeMap<String, String>,
) -> RadarResult<SourceCard> {
    let source = fuente_valida(&source)?;
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/sources/{source}/credentials", sidecar_url()))
            .timeout(TIMEOUT)
            .json(&CredentialsBody { values: &values }),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudieron guardar las credenciales").await
}

/// Llamada mínima real a la API de la fuente.
#[tauri::command]
pub async fn probe_source(
    state: State<'_, AppState>,
    source: String,
) -> RadarResult<SourceProbeResult> {
    let source = fuente_valida(&source)?;
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/sources/{source}/probe", sidecar_url()))
            .timeout(PROBE_TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudo probar la fuente").await
}

/// Enciende o apaga una fuente sin borrar lo último que dijo su API.
#[tauri::command]
pub async fn set_source_enabled(
    state: State<'_, AppState>,
    source: String,
    enabled: bool,
) -> RadarResult<SourceCard> {
    let source = fuente_valida(&source)?;
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/sources/{source}/enabled", sidecar_url()))
            .timeout(TIMEOUT)
            .json(&EnabledBody { enabled }),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudo cambiar la fuente").await
}

/// Modo comercial: excluye las fuentes de «solo uso personal».
#[tauri::command]
pub async fn set_commercial_mode(
    state: State<'_, AppState>,
    enabled: bool,
) -> RadarResult<SourcesOverview> {
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/sources/commercial-mode", sidecar_url()))
            .timeout(TIMEOUT)
            .json(&EnabledBody { enabled }),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudo cambiar el modo comercial").await
}

/// Escaneo multifuente: reenvía el progreso por `sources:events` y devuelve
/// el último evento (`scan:done` o `error`).
#[tauri::command]
pub async fn trigger_multiscan(
    app: AppHandle,
    state: State<'_, AppState>,
    profile: ScanProfileParams,
) -> RadarResult<serde_json::Value> {
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/sources/scan/stream", sidecar_url()))
            // Sin timeout total (AUD2-025): relay_sse corta solo tras SILENCIO_MAX.
            .json(&cuerpo_del_escaneo(&profile)),
    )
    .send()
    .await
    .map_err(transport_error)?;

    let status = response.status();
    if !status.is_success() {
        let detail = response.text().await.unwrap_or_default();
        return Err(rechazo("El escaneo multifuente fallo", &status.to_string(), &detail));
    }
    relay_sse(&app, response, SOURCES_EVENT_CHANNEL).await
}

fn cuerpo_del_escaneo(profile: &ScanProfileParams) -> MultiScanBody<'_> {
    MultiScanBody {
        profile: ScanProfileBody {
            name: &profile.name,
            keywords: &profile.keywords,
            discovery: profile.discovery,
            window_days: profile.window_days,
            languages: &profile.languages,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_id_de_la_fuente_no_puede_salirse_de_la_ruta() {
        assert!(fuente_valida("hackernews").is_ok());
        assert!(fuente_valida("stack_exchange2").is_ok());
        for mala in ["", "../config", "a/b", "HN", "hn?x=1", &"a".repeat(41)] {
            assert!(fuente_valida(mala).is_err(), "debería rechazar '{mala}'");
        }
    }

    #[test]
    fn el_perfil_viaja_al_sidecar_en_snake_case() {
        let perfil = ScanProfileParams {
            name: "facturas".into(),
            keywords: vec!["invoice".into()],
            discovery: false,
            window_days: 180,
            languages: vec!["en".into()],
        };
        let cuerpo = serde_json::to_value(cuerpo_del_escaneo(&perfil)).unwrap();
        assert_eq!(cuerpo["profile"]["window_days"], 180);
        assert!(cuerpo["profile"].get("windowDays").is_none());
        assert_eq!(cuerpo["profile"]["keywords"][0], "invoice");
    }
}
