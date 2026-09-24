//! Comandos que delegan en el sidecar Python.
//!
//! El motor (fuentes, juez, embeddings, busqueda) vive en Python y no tiene
//! equivalente en Rust. Estos comandos hablan con el con HTTP sobre loopback.
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
    pub limit: Option<i64>,
}

#[derive(Debug, Serialize)]
pub(crate) struct SearchBody {
    query: String,
    limit: i64,
}

/// Lo que viaja al sidecar: la consulta y el limite (20 si no se indica).
pub(crate) fn cuerpo_de_busqueda(params: SearchParams) -> SearchBody {
    SearchBody {
        query: params.query,
        limit: params.limit.unwrap_or(20),
    }
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

/// Busqueda sobre la evidencia multifuente (D-C4): vectores e5 + texto en
/// PostgreSQL, con fusion RRF. Sin almacen de vectores, el sidecar responde
/// 503 con codigo `search_unavailable`, que llega tal cual a la interfaz.
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
            .json(&cuerpo_de_busqueda(params)),
    )
    .send()
    .await
    .map_err(transport_error)?;

    let status = response.status();
    if !status.is_success() {
        let detail = response.text().await.unwrap_or_default();
        return Err(crate::commands::settings::rechazo_con_codigo(&detail).unwrap_or_else(|| {
            RadarError::Sidecar(format!("El sidecar respondio {status} a la busqueda: {detail}"))
        }));
    }

    let envelope: SearchEnvelope = response.json().await.map_err(transport_error)?;
    Ok(envelope.hits)
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
