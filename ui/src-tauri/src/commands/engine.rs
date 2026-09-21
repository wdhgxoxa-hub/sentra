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

/// Base del sidecar. Loopback: no debe ser alcanzable desde la red.
const DEFAULT_SIDECAR_URL: &str = "http://127.0.0.1:8765";
const URL_ENV_VAR: &str = "RIR_SIDECAR_URL";
const TOKEN_ENV_VAR: &str = "RIR_SIDECAR_TOKEN";
const TOKEN_HEADER: &str = "X-Radar-Token";

/// Canal por el que viaja el progreso hacia el WebView.
pub const RADAR_EVENT_CHANNEL: &str = "radar:events";

/// Un escaneo puede recorrer varios ciclos y analizar decenas de posts;
/// el timeout corto de una API web no sirve aqui.
const SCAN_TIMEOUT: Duration = Duration::from_secs(600);
const SEARCH_TIMEOUT: Duration = Duration::from_secs(60);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(5);

pub fn sidecar_url() -> String {
    std::env::var(URL_ENV_VAR).unwrap_or_else(|_| DEFAULT_SIDECAR_URL.to_string())
}

/// Aplica el token al request si esta configurado.
///
/// Se reexporta para que los comandos de mutacion hablen con el sidecar sin
/// duplicar la logica del encabezado.
pub fn with_token_pub(builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
    with_token(builder)
}

fn with_token(builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
    match std::env::var(TOKEN_ENV_VAR) {
        Ok(token) if !token.is_empty() => builder.header(TOKEN_HEADER, token),
        _ => builder,
    }
}

/// Traduce un fallo de transporte en un mensaje que el usuario entienda.
///
/// "connection refused" no le dice nada a nadie; "el sidecar no responde,
/// arrancalo con este comando" si.
fn transport_error(err: reqwest::Error) -> RadarError {
    if err.is_connect() {
        RadarError::Sidecar(format!(
            "El sidecar Python no responde en {}. Arrancalo con: \
             python -m core.orchestration.sidecar_server",
            sidecar_url()
        ))
    } else if err.is_timeout() {
        RadarError::Sidecar("El sidecar tardo demasiado en responder".into())
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
                let _ = app.emit(RADAR_EVENT_CHANNEL, &event);
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

/// Consulta la salud del sidecar. Devuelve None si no responde.
pub async fn sidecar_health(client: &reqwest::Client) -> Option<serde_json::Value> {
    let response = with_token(
        client
            .get(format!("{}/api/health", sidecar_url()))
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
