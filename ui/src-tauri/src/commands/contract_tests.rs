//! Contratos entre `ui/src/lib/ipc.ts` y los parametros de los comandos.
//!
//! Tauri solo traduce a snake_case los nombres de los argumentos de primer
//! nivel (`clusterKey` -> `cluster_key`). Los campos de un objeto anidado
//! (`{ params: { apiKey } }`) los resuelve serde, y sin
//! `#[serde(rename_all = "camelCase")]` fallan: con "missing field" si el
//! campo es obligatorio, o convertidos en `None` en silencio si es opcional.
//!
//! Por eso cada test copia el payload tal como lo envia el frontend, lo
//! deserializa igual que Tauri (el valor bajo la clave del argumento) y
//! comprueba el valor de cada campo, no solo que no haya error.

use serde::de::DeserializeOwned;
use serde_json::{json, Value};

use crate::commands::architect::GeminiKeyParams;
use crate::commands::engine::{ScanParams, SearchParams};
use crate::commands::mutations::UpsertSubredditParams;
use crate::commands::radar::{BoardParams, FeedParams};
use crate::commands::settings::CredentialsInput;

/// Extrae el argumento `name` del payload de `invoke` y lo deserializa.
fn argumento<T: DeserializeOwned>(payload: &Value, name: &str) -> T {
    let valor = payload
        .get(name)
        .unwrap_or_else(|| panic!("el payload no trae el argumento '{name}'"))
        .clone();
    serde_json::from_value(valor)
        .unwrap_or_else(|err| panic!("'{name}' no respeta el contrato: {err}"))
}

#[test]
fn save_gemini_key_recibe_la_clave_y_el_modelo() {
    // ipc.ts:133 -> invoke("save_gemini_key", { params: { apiKey, model } })
    let payload = json!({ "params": { "apiKey": "clave-de-prueba", "model": "gemini-2.5-flash" } });
    let params: GeminiKeyParams = argumento(&payload, "params");
    assert_eq!(params.api_key, "clave-de-prueba");
    assert_eq!(params.model, "gemini-2.5-flash");
}

#[test]
fn save_reddit_credentials_recibe_todos_los_campos() {
    // ipc.ts:118 -> invoke("save_reddit_credentials", { credentials })
    // con credentials = { clientId, clientSecret, userAgent, username, password }
    // (SettingsView.tsx:82)
    let payload = json!({ "credentials": {
        "clientId": "id", "clientSecret": "secreto", "userAgent": "ua",
        "username": "usuario", "password": "clave"
    }});
    let c: CredentialsInput = argumento(&payload, "credentials");
    assert_eq!(c.client_id, "id");
    assert_eq!(c.client_secret, "secreto");
    assert_eq!(c.user_agent, "ua");
    assert_eq!(c.username.as_deref(), Some("usuario"));
    assert_eq!(c.password.as_deref(), Some("clave"));
}

#[test]
fn get_radar_feed_recibe_limite_puntuacion_y_subreddit() {
    // ipc.ts:54 -> invoke("get_radar_feed", { params }) con FeedParams
    // (RadarView.tsx:29 envia limit y minScore)
    let payload = json!({ "params": { "limit": 40, "minScore": 12.5, "subreddit": "SaaS" } });
    let p: FeedParams = argumento(&payload, "params");
    assert_eq!(p.limit, Some(40));
    assert_eq!(p.min_score, Some(12.5));
    assert_eq!(p.subreddit.as_deref(), Some("SaaS"));
}

#[test]
fn get_opportunity_board_recibe_limite_y_filtro_de_cualificadas() {
    // ipc.ts:58 -> invoke("get_opportunity_board", { params }) con BoardParams
    // (RadarView.tsx:28 envia limit y qualifiedOnly)
    let payload = json!({ "params": { "limit": 24, "minScore": 3.0, "qualifiedOnly": true } });
    let p: BoardParams = argumento(&payload, "params");
    assert_eq!(p.limit, Some(24));
    assert_eq!(p.min_score, Some(3.0));
    assert_eq!(p.qualified_only, Some(true));
}

#[test]
fn search_hybrid_recibe_consulta_puntuacion_y_limite() {
    // ipc.ts:77 -> invoke("search_hybrid", { params }) con SearchParams
    // (SearchConsole.tsx:23 envia query y limit)
    let payload = json!({ "params": { "query": "facturas", "minScore": 20.0, "limit": 20 } });
    let p: SearchParams = argumento(&payload, "params");
    assert_eq!(p.query, "facturas");
    assert_eq!(p.min_score, Some(20.0));
    assert_eq!(p.limit, Some(20));
}

#[test]
fn trigger_scan_recibe_subreddit_limite_y_orden() {
    // ipc.ts:86 -> invoke("trigger_scan", { params }) con ScanParams
    // (PipelineControl.tsx:226-230)
    let payload = json!({ "params": { "subreddit": "SaaS", "limit": 25, "sort": "new" } });
    let p: ScanParams = argumento(&payload, "params");
    assert_eq!(p.subreddit, "SaaS");
    assert_eq!(p.limit, Some(25));
    assert_eq!(p.sort.as_deref(), Some("new"));
}

#[test]
fn upsert_subreddit_recibe_todos_los_campos_opcionales() {
    // ipc.ts:104 -> invoke("upsert_subreddit", { params }) con
    // UpsertSubredditParams (types/radar.ts:431-439; PipelineControl.tsx:52-57)
    let payload = json!({ "params": {
        "name": "SaaS", "listing": "new", "limitPerPage": 50,
        "minOpportunityScore": 70.0, "scanIntervalMinutes": 120,
        "status": "paused", "tags": ["b2b"]
    }});
    let p: UpsertSubredditParams = argumento(&payload, "params");
    assert_eq!(p.name, "SaaS");
    assert_eq!(p.listing.as_deref(), Some("new"));
    assert_eq!(p.limit_per_page, Some(50));
    assert_eq!(p.min_opportunity_score, Some(70.0));
    assert_eq!(p.scan_interval_minutes, Some(120));
    assert_eq!(p.status.as_deref(), Some("paused"));
    assert_eq!(p.tags, Some(vec!["b2b".to_string()]));
}
