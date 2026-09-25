//! Palabras clave propuestas para el asistente de escaneo (Fase 2, D1).
//!
//! Reenvía a `POST /api/scan/keywords`: con Gemini, una llamada que cuenta
//! para los topes; sin clave, sin presupuesto o con error, una propuesta
//! básica sin Gemini. La forma de la respuesta (KeywordProposal) la vigila
//! tests/test_contracts.py; Rust la reenvía sin tocarla.

use std::time::Duration;

use serde::Serialize;
use tauri::State;

use crate::commands::engine::{como_json, sidecar_url, transport_error, with_token_pub};
use crate::db::{AppState, RadarResult};

/// Una llamada al modelo general tarda segundos; el motor corta a los 60 s.
const TIMEOUT: Duration = Duration::from_secs(90);

/// Cuerpo de `POST /api/scan/keywords` (`KeywordsRequest` en el motor).
#[derive(Debug, Serialize)]
pub(crate) struct CuerpoDePalabras<'a> {
    topic: &'a str,
    languages: &'a [String],
}

pub(crate) fn cuerpo_de_palabras<'a>(topic: &'a str, languages: &'a [String]) -> CuerpoDePalabras<'a> {
    CuerpoDePalabras { topic, languages }
}

/// Palabras clave propuestas para un tema, en los idiomas pedidos.
#[tauri::command]
pub async fn propose_keywords(
    state: State<'_, AppState>,
    topic: String,
    languages: Vec<String>,
) -> RadarResult<serde_json::Value> {
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/scan/keywords", sidecar_url()))
            .timeout(TIMEOUT)
            .json(&cuerpo_de_palabras(&topic, &languages)),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudieron proponer palabras clave").await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_cuerpo_lleva_el_tema_y_los_idiomas() {
        let cuerpo = serde_json::to_value(cuerpo_de_palabras("clientes que pagan tarde", &["es".into(), "en".into()]))
            .unwrap();
        assert_eq!(
            cuerpo,
            serde_json::json!({ "topic": "clientes que pagan tarde", "languages": ["es", "en"] })
        );
    }
}
