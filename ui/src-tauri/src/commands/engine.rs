//! Comandos que delegan en el sidecar Python.
//!
//! El motor (grafo LangGraph, embeddings, busqueda hibrida sobre LanceDB)
//! vive en Python y no tiene equivalente en Rust. Estos comandos son el
//! puente.
//!
//! ESTADO: esqueleto. El sidecar todavia no se lanza ni expone su API HTTP
//! local, asi que cada comando devuelve `NotImplemented` con un mensaje
//! explicito en lugar de fingir un resultado vacio, que se confundiria con
//! "no hay datos".

use serde::{Deserialize, Serialize};

use crate::db::{RadarError, RadarResult};

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
#[serde(rename_all = "camelCase")]
pub struct HybridSearchHit {
    pub id: String,
    pub text: String,
    pub subreddit: String,
    pub opportunity_score: f64,
    pub urgency_tier: String,
    pub job_statement: String,
    pub rrf_score: f64,
    pub dense_rank: Option<i64>,
    pub bm25_rank: Option<i64>,
}

/// Busqueda hibrida densa + BM25 con fusion RRF.
#[tauri::command]
pub async fn search_hybrid(params: SearchParams) -> RadarResult<Vec<HybridSearchHit>> {
    let _ = params;
    Err(RadarError::NotImplemented(
        "La busqueda hibrida requiere el sidecar Python, que aun no se lanza \
         desde Tauri. Disponible por MCP: search_pain_points."
            .into(),
    ))
}

/// Dispara un escaneo completo y devuelve el identificador de la ejecucion.
#[tauri::command]
pub async fn trigger_scan(params: ScanParams) -> RadarResult<String> {
    let _ = params;
    Err(RadarError::NotImplemented(
        "El disparo de escaneos requiere el sidecar Python, que aun no se \
         lanza desde Tauri. Disponible por MCP: scan_subreddit."
            .into(),
    ))
}
