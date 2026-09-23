//! Comandos que delegan en el sidecar Python.
//!
//! El motor (grafo LangGraph, embeddings, busqueda hibrida sobre LanceDB)
//! vive en Python y no tiene equivalente en Rust. Estos comandos hablan con
//! el con HTTP sobre loopback.
//!
//! El sidecar se arranca aparte:
//!
//! ```text
//! python -m core.orchestration.sidecar_server --port 8765
//! ```

use std::time::Duration;

use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

use crate::db::{AppState, RadarError, RadarResult};


/// Canal por el que viaja el progreso hacia el WebView.
pub const RADAR_EVENT_CHANNEL: &str = "radar:events";

/// Un escaneo puede recorrer varios ciclos y analizar decenas de posts;
/// el timeout corto de una API web no sirve aqui.
pub(crate) const SCAN_TIMEOUT: Duration = Duration::from_secs(600);
const SEARCH_TIMEOUT: Duration = Duration::from_secs(60);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(5);

/// URL del sidecar: sale del mismo puerto con el que se lanza (D-C).
pub fn sidecar_url() -> String {
    crate::sidecar::sidecar_base_url()
}

/// Aplica el token al request si esta configurado.
///
/// Se reexporta para que los comandos de mutacion hablen con el sidecar sin
/// duplicar la logica del encabezado.
pub fn with_token_pub(builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
    with_token(builder)
}

fn with_token(builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
    builder.bearer_auth(crate::sidecar::sidecar_token())
}

/// Clasifica un fallo de transporte con el motor (D-A).
///
/// "connection refused" no le dice nada a nadie: la interfaz traduce el
/// codigo (no arrancado, no responde a tiempo) y deja el error de red en
/// el detalle tecnico. Es la unica traduccion: todos los comandos que
/// hablan con el sidecar la usan.
pub fn transport_error(err: reqwest::Error) -> RadarError {
    if err.is_connect() {
        RadarError::SidecarUnreachable(format!("{}: {err}", sidecar_url()))
    } else if err.is_timeout() {
        RadarError::SidecarTimeout(format!("{}: {err}", sidecar_url()))
    } else {
        RadarError::Sidecar(format!("Fallo hablando con el sidecar: {err}"))
    }
}

// ---------------------------------------------------------------------
// Contratos
// ---------------------------------------------------------------------

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchParams {
    pub query: String,
    pub min_score: Option<f64>,
    pub limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScanParams {
    pub subreddit: String,
    pub limit: Option<i64>,
    pub sort: Option<String>,
}

#[derive(Debug, Serialize)]
struct ScanBody {
    subreddit: String,
    limit: i64,
    sort: String,
}

#[derive(Debug, Serialize)]
struct SearchBody {
    query: String,
    #[serde(rename = "minScore")]
    min_score: f64,
    limit: i64,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchEnvelope {
    pub query: String,
    pub hits: Vec<serde_json::Value>,
}

// ---------------------------------------------------------------------
// Comandos
// ---------------------------------------------------------------------

/// Busqueda hibrida densa + BM25 con fusion RRF.
#[tauri::command]
pub async fn search_hybrid(
    state: State<'_, AppState>,
    params: SearchParams,
) -> RadarResult<Vec<serde_json::Value>> {
    let response = with_token(
        state
            .http
            .post(format!("{}/api/search", sidecar_url()))
            .timeout(SEARCH_TIMEOUT)
            .json(&SearchBody {
                query: params.query,
                min_score: params.min_score.unwrap_or(0.0),
                limit: params.limit.unwrap_or(20),
            }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    if !response.status().is_success() {
        return Err(RadarError::Sidecar(format!(
            "El sidecar respondio {} a la busqueda",
            response.status()
        )));
    }

    let envelope: SearchEnvelope = response.json().await.map_err(transport_error)?;
    Ok(envelope.hits)
}

/// Dispara un escaneo completo, retransmitiendo su avance al WebView.
///
/// Consume el flujo SSE del sidecar y reenvia cada evento por el canal
/// `radar:events`. La interfaz pinta el progreso segun llega, sin sondear.
///
/// Devuelve el ultimo evento (`run:finished` o `run:error`), de modo que
/// quien invoca tambien tiene el desenlace sin tener que escuchar el canal.
#[tauri::command]
pub async fn trigger_scan(
    app: AppHandle,
    state: State<'_, AppState>,
    params: ScanParams,
) -> RadarResult<serde_json::Value> {
    let response = with_token(
        state
            .http
            .post(format!("{}/api/scan/stream", sidecar_url()))
            .timeout(SCAN_TIMEOUT)
            .json(&ScanBody {
                subreddit: params.subreddit,
                limit: params.limit.unwrap_or(25),
                sort: params.sort.unwrap_or_else(|| "hot".into()),
            }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    let status = response.status();
    if !status.is_success() {
        let detail = response.text().await.unwrap_or_default();
        return Err(RadarError::Sidecar(format!(
            "El escaneo fallo ({status}): {detail}"
        )));
    }

    relay_sse(&app, response, RADAR_EVENT_CHANNEL).await
}

/// Reenvia cada evento SSE del sidecar por `channel` y devuelve el ultimo.
pub(crate) async fn relay_sse(
    app: &AppHandle,
    response: reqwest::Response,
    channel: &str,
) -> RadarResult<serde_json::Value> {
    let mut stream = response.bytes_stream();
    // Los trozos de red no respetan los limites de los eventos: un evento
    // puede llegar partido en dos y dos eventos en un mismo trozo.
    let mut buffer = String::new();
    let mut last_event = serde_json::Value::Null;

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(transport_error)?;
        buffer.push_str(&String::from_utf8_lossy(&chunk));

        while let Some(position) = buffer.find("

") {
            let block: String = buffer.drain(..position + 2).collect();
            if let Some(event) = parse_sse_block(&block) {
                let _ = app.emit(channel, &event);
                last_event = event;
            }
        }
    }

    Ok(last_event)
}

/// Extrae el JSON de un bloque `data: {...}` del flujo SSE.
fn parse_sse_block(block: &str) -> Option<serde_json::Value> {
    for line in block.lines() {
        if let Some(payload) = line.strip_prefix("data:") {
            return serde_json::from_str(payload.trim()).ok();
        }
    }
    None
}

/// Lo que contesta el puerto del sidecar a `/api/health`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Sonda {
    /// Nuestro sidecar, que acepta el token.
    Responde,
    /// Alguien contesta pero rechaza el token (401): no es nuestro.
    Rechaza,
    /// Nadie contesta, o no con algo reconocible.
    NoResponde,
}

/// Pregunta al puerto del sidecar quien hay (D-B).
pub async fn sondear(client: &reqwest::Client) -> Sonda {
    sondear_en(client, &sidecar_url()).await
}

/// Como `sondear`, contra una URL base dada (la de la configuracion del
/// gestor del sidecar).
pub async fn sondear_en(client: &reqwest::Client, base: &str) -> Sonda {
    let respuesta = with_token(
        client
            .get(format!("{base}/api/health"))
            .timeout(HEALTH_TIMEOUT),
    )
    .send()
    .await;
    match respuesta {
        Ok(r) if r.status().is_success() => Sonda::Responde,
        Ok(r) if r.status() == reqwest::StatusCode::UNAUTHORIZED => Sonda::Rechaza,
        _ => Sonda::NoResponde,
    }
}

/// Consulta la salud del sidecar. Devuelve None si no responde.
pub async fn sidecar_health(client: &reqwest::Client) -> Option<serde_json::Value> {
    sidecar_health_en(client, &sidecar_url()).await
}

/// Como `sidecar_health`, contra una URL base dada.
pub async fn sidecar_health_en(client: &reqwest::Client, base: &str) -> Option<serde_json::Value> {
    let response = with_token(
        client
            .get(format!("{base}/api/health"))
            .timeout(HEALTH_TIMEOUT),
    )
    .send()
    .await
    .ok()?;

    if response.status().is_success() {
        response.json().await.ok()
    } else {
        None
    }
}

/// Una cita traducida.
#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct QuoteTranslation {
    pub text: String,
    /// "gemini" o "offline".
    pub engine: String,
    /// True cuando el texto solo esta traducido en parte.
    pub approximate: bool,
}

#[derive(Debug, Serialize)]
struct TranslateBody {
    texts: Vec<String>,
    target: String,
}

/// Traduce las citas de una oportunidad al idioma de la interfaz.
///
/// El sidecar decide el motor segun haya clave de Gemini o no, y responde
/// siempre: una cita sin traducir se lee, un hueco no.
#[tauri::command]
pub async fn translate_quotes(
    state: State<'_, AppState>,
    texts: Vec<String>,
    target: String,
) -> RadarResult<Vec<QuoteTranslation>> {
    if texts.is_empty() {
        return Ok(Vec::new());
    }

    let response = with_token(
        state
            .http
            .post(format!("{}/api/translate", sidecar_url()))
            .timeout(Duration::from_secs(120))
            .json(&TranslateBody { texts, target }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    let status = response.status();
    if !status.is_success() {
        let detail = response.text().await.unwrap_or_default();
        return Err(RadarError::Sidecar(format!(
            "No se pudo traducir ({status}): {detail}"
        )));
    }

    #[derive(Deserialize)]
    struct Envelope {
        translations: Vec<QuoteTranslation>,
    }

    let envelope: Envelope = response.json().await.map_err(transport_error)?;
    Ok(envelope.translations)
}
