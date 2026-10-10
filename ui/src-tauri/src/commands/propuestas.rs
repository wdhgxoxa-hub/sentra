//! Propuestas de escaneo de Claude Desktop (servidor MCP, core/mcp).
//!
//! Claude deja la propuesta en la base; la ventana la lee aqui y Walter la
//! descarta o la revisa en el asistente. Lanzarla es `trigger_multiscan` con
//! su `requestId`, despues de confirmar la estimacion como cualquier escaneo.
//! Ningun comando de aqui escanea ni gasta.

use std::time::Duration;

use tauri::State;

use crate::commands::engine::{como_json, sidecar_url, transport_error, with_token_pub};
use crate::db::{AppState, RadarError, RadarResult};

/// Leer o descartar solo toca una tabla pequeña: si tarda, algo va mal.
const TIMEOUT: Duration = Duration::from_secs(15);

/// Un id de propuesta es un uuid: nada mas puede ir en la ruta.
fn id_valido(id: &str) -> RadarResult<&str> {
    let partes: Vec<&str> = id.split('-').collect();
    let largos = [8, 4, 4, 4, 12];
    let valido = partes.len() == largos.len()
        && partes.iter().zip(largos).all(|(p, n)| p.len() == n && p.chars().all(|c| c.is_ascii_hexdigit()));
    if valido {
        Ok(id)
    } else {
        Err(RadarError::Invalid(format!("Propuesta desconocida: '{id}'")))
    }
}

/// Las propuestas pendientes, de la mas antigua a la mas nueva.
#[tauri::command]
pub async fn get_scan_requests(state: State<'_, AppState>) -> RadarResult<serde_json::Value> {
    let response = with_token_pub(
        state.http.get(format!("{}/api/scan-requests", sidecar_url())).timeout(TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudieron leer las propuestas de Claude").await
}

/// Descarta una propuesta pendiente. No escanea.
#[tauri::command]
pub async fn discard_scan_request(
    state: State<'_, AppState>,
    request_id: String,
) -> RadarResult<serde_json::Value> {
    let id = id_valido(&request_id)?;
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/scan-requests/{id}/discard", sidecar_url()))
            .timeout(TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudo descartar la propuesta").await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_id_de_la_propuesta_no_puede_salirse_de_la_ruta() {
        assert!(id_valido("01a0dad3-844c-7e42-863d-a912d331064d").is_ok());
        for malo in ["", "../discard", "x", "01a0dad3-844c-7e42-863d-a912d331064d/../../x",
                     "01a0dad3-844c-7e42-863d-a912d331064g", "01a0dad3844c7e42863da912d331064d"] {
            assert!(id_valido(malo).is_err(), "debería rechazar '{malo}'");
        }
    }
}
