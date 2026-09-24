//! Juez de nichos (F3): Top 6 por veredicto y feed de evidencia reciente.
//!
//! Delega en el sidecar (`/api/judge/top`, `/api/evidence/recent`), que lee
//! `niche_verdicts` y `evidence_items` con su atribución. La forma de las
//! respuestas (JudgeTop, EvidenceFeed) la vigila tests/test_contracts.py
//! contra ui/src/types/radar.ts; Rust la reenvía sin tocarla.

use std::time::Duration;

use tauri::State;

use crate::commands::engine::{como_json, sidecar_url, transport_error, with_token_pub};
use crate::db::{AppState, RadarResult};

const TIMEOUT: Duration = Duration::from_secs(30);

/// URL del Top: de una ejecución concreta o de la última juzgada.
fn url_del_top(base: &str, run_id: Option<&str>) -> String {
    let ruta = format!("{base}/api/judge/top");
    match (run_id.filter(|id| !id.trim().is_empty()), reqwest::Url::parse(&ruta)) {
        (Some(id), Ok(mut url)) => {
            url.query_pairs_mut().append_pair("runId", id);
            url.to_string()
        }
        _ => ruta,
    }
}

/// URL del feed: sin límite, el motor aplica el suyo (y siempre recorta).
fn url_del_feed(base: &str, limit: Option<u32>) -> String {
    let ruta = format!("{base}/api/evidence/recent");
    match limit {
        Some(n) => format!("{ruta}?limit={n}"),
        None => ruta,
    }
}

/// Top 6 del juez: veredictos, compuertas, corroboración, abogado y evidencia.
#[tauri::command]
pub async fn get_judge_top(
    state: State<'_, AppState>,
    run_id: Option<String>,
) -> RadarResult<serde_json::Value> {
    leer(&state, url_del_top(&sidecar_url(), run_id.as_deref())).await
}

/// Evidencia multifuente más reciente, con su atribución (Radar, D-C2).
#[tauri::command]
pub async fn get_evidence_feed(
    state: State<'_, AppState>,
    limit: Option<u32>,
) -> RadarResult<serde_json::Value> {
    leer(&state, url_del_feed(&sidecar_url(), limit)).await
}

async fn leer(state: &AppState, url: String) -> RadarResult<serde_json::Value> {
    let response = with_token_pub(state.http.get(url).timeout(TIMEOUT))
        .send()
        .await
        .map_err(transport_error)?;

    como_json(response, "No se pudo leer el juez").await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sin_ejecucion_pide_la_ultima_juzgada() {
        assert_eq!(url_del_top("http://x", None), "http://x/api/judge/top");
        assert_eq!(url_del_top("http://x", Some("  ")), "http://x/api/judge/top");
    }

    #[test]
    fn el_feed_pide_el_limite_indicado_o_el_del_motor() {
        assert_eq!(url_del_feed("http://x", Some(25)), "http://x/api/evidence/recent?limit=25");
        assert_eq!(url_del_feed("http://x", None), "http://x/api/evidence/recent");
    }

    #[test]
    fn el_id_de_la_ejecucion_va_codificado() {
        assert_eq!(
            url_del_top("http://x", Some("a b&c")),
            "http://x/api/judge/top?runId=a+b%26c"
        );
    }
}
