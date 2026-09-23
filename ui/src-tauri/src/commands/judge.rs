//! Juez de nichos (F3): Top 6 por veredicto.
//!
//! Delega en el sidecar (`/api/judge/top`), que lee `niche_verdicts` y la
//! evidencia con su atribución. La forma de la respuesta (JudgeTop) la
//! vigila tests/test_contracts.py contra ui/src/types/radar.ts; Rust la
//! reenvía sin tocarla.

use std::time::Duration;

use tauri::State;

use crate::commands::engine::{sidecar_url, transport_error, with_token_pub};
use crate::db::{AppState, RadarError, RadarResult};

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

/// Top 6 del juez: veredictos, compuertas, corroboración, abogado y evidencia.
#[tauri::command]
pub async fn get_judge_top(
    state: State<'_, AppState>,
    run_id: Option<String>,
) -> RadarResult<serde_json::Value> {
    let response = with_token_pub(
        state
            .http
            .get(url_del_top(&sidecar_url(), run_id.as_deref()))
            .timeout(TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;

    let status = response.status();
    if !status.is_success() {
        let detail = response.text().await.unwrap_or_default();
        return Err(crate::commands::settings::rechazo_con_codigo(&detail).unwrap_or_else(|| {
            RadarError::Sidecar(format!("No se pudo leer el juez ({status}): {detail}"))
        }));
    }
    response.json().await.map_err(transport_error)
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
    fn el_id_de_la_ejecucion_va_codificado() {
        assert_eq!(
            url_del_top("http://x", Some("a b&c")),
            "http://x/api/judge/top?runId=a+b%26c"
        );
    }
}
