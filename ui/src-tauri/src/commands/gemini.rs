//! Clave y modelos de Gemini.
//!
//! La clave de API nunca pasa por aqui: vive en el `.env` del sidecar y solo
//! se envia cuando se guarda. El motor de arquitectura por cluster se retiro
//! con la ficha de oportunidad (C2, D-C3); los documentos del juez llegan en
//! la Fase E.

use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::commands::engine::{como_json, sidecar_url, transport_error, with_token_pub};
use crate::commands::settings::GeminiSummary;
use crate::db::{AppState, RadarResult};

const SHORT_TIMEOUT: Duration = Duration::from_secs(60);

/// Llega anidado (`{ params: { apiKey, model, generalModel } }`): Tauri solo
/// traduce los nombres de primer nivel, asi que el camelCase lo pone serde.
///
/// Un modelo vacio es "automatico" (lo elige el sidecar de la lista en vivo).
/// Una clave vacia conserva la guardada: cambiar de modelo no obliga a
/// teclearla otra vez.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GeminiKeyParams {
    #[serde(default)]
    pub api_key: String,
    #[serde(default)]
    pub model: String,
    #[serde(default)]
    pub general_model: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GeminiBody {
    api_key: String,
    model: String,
    general_model: String,
}

/// Un modelo que la clave puede usar, tal como lo lista el sidecar.
#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GeminiModel {
    pub id: String,
    pub display_name: String,
}

/// Modelos que la clave puede usar (models.list) y el que se usaria en cada
/// uso. Con `ok = false`, `code` dice por que (sin clave, clave mala, red).
#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GeminiModelsResult {
    pub ok: bool,
    pub code: Option<String>,
    pub detail: String,
    pub models: Vec<GeminiModel>,
    pub general: Option<String>,
    pub documents: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProbeResult {
    pub ok: bool,
    pub detail: String,
    /// Codigo del fallo: `gemini_key_rejected` es el unico que dice que la
    /// clave es mala; la red o la cuota no dicen nada de ella (D1).
    #[serde(default)]
    pub code: Option<String>,
}

/// Guarda la clave de Gemini en el `.env` del proyecto.
#[tauri::command]
pub async fn save_gemini_key(
    state: State<'_, AppState>,
    params: GeminiKeyParams,
) -> RadarResult<GeminiSummary> {
    // Sin clave nueva, el sidecar conserva la guardada o responde 400.
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/gemini", sidecar_url()))
            .timeout(SHORT_TIMEOUT)
            .json(&GeminiBody {
                api_key: params.api_key,
                model: params.model,
                general_model: params.general_model,
            }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    #[derive(Deserialize)]
    struct Envelope {
        gemini: GeminiSummary,
    }

    let envelope: Envelope = como_json(response, "No se pudo guardar la clave").await?;
    Ok(envelope.gemini)
}

/// Modelos que la clave guardada puede usar. El sidecar reutiliza la lista
/// unos minutos: cada consulta real a Google es una llamada de la cuota.
#[tauri::command]
pub async fn list_gemini_models(state: State<'_, AppState>) -> RadarResult<GeminiModelsResult> {
    let response = with_token_pub(
        state
            .http
            .get(format!("{}/api/gemini/models", sidecar_url()))
            .timeout(SHORT_TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;

    como_json(response, "Gemini").await
}

/// Comprueba contra Google que la clave guardada sirve.
#[tauri::command]
pub async fn test_gemini_key(state: State<'_, AppState>) -> RadarResult<ProbeResult> {
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/gemini/test", sidecar_url()))
            .timeout(SHORT_TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;

    como_json(response, "Gemini").await
}
