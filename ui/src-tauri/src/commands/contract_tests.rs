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

use crate::commands::gemini::GeminiKeyParams;
use crate::commands::documents::ExportDocumentParams;
use crate::commands::engine::SearchParams;

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
fn save_gemini_key_recibe_la_clave_y_los_dos_modelos() {
    // ipc.ts -> invoke("save_gemini_key", { params: { apiKey, model, generalModel } })
    let payload = json!({ "params": {
        "apiKey": "clave-de-prueba", "model": "gemini-3.1-pro-preview", "generalModel": ""
    }});
    let params: GeminiKeyParams = argumento(&payload, "params");
    assert_eq!(params.api_key, "clave-de-prueba");
    assert_eq!(params.model, "gemini-3.1-pro-preview");
    assert_eq!(params.general_model, "", "vacío = automático");
}

#[test]
fn save_gemini_key_sin_clave_nueva_cambia_solo_los_modelos() {
    // Elegir modelo no obliga a teclear otra vez la clave: la conserva el sidecar.
    let payload = json!({ "params": { "apiKey": "", "model": "", "generalModel": "gemini-3.5-flash" } });
    let params: GeminiKeyParams = argumento(&payload, "params");
    assert!(params.api_key.is_empty());
    assert_eq!(params.general_model, "gemini-3.5-flash");
}

#[test]
fn search_hybrid_recibe_consulta_y_limite_y_los_reenvia_sin_mas() {
    // ipc.ts -> invoke("search_hybrid", { params }) con SearchParams
    // (SearchConsole.tsx envia query y limit). La busqueda sobre la evidencia
    // (D-C4) no filtra por puntuacion: el cuerpo lleva solo esos dos campos.
    let payload = json!({ "params": { "query": "facturas", "limit": 20 } });
    let p: SearchParams = argumento(&payload, "params");
    assert_eq!(p.query, "facturas");
    assert_eq!(p.limit, Some(20));
    let cuerpo = serde_json::to_value(crate::commands::engine::cuerpo_de_busqueda(p)).unwrap();
    assert_eq!(cuerpo, json!({ "query": "facturas", "limit": 20 }));
}

#[test]
fn export_document_recibe_veredicto_tipo_formato_idioma_y_forzado() {
    // ipc.ts -> invoke("export_document", { params }) con ExportDocumentParams.
    let payload = json!({ "params": {
        "verdictId": "11111111-1111-1111-1111-111111111111", "kind": "plan", "format": "md",
        "language": "en", "force": true
    }});
    let p: ExportDocumentParams = argumento(&payload, "params");
    assert_eq!(p.verdict_id, "11111111-1111-1111-1111-111111111111");
    assert_eq!((p.kind.as_str(), p.format.as_str(), p.language.as_str()), ("plan", "md", "en"));
    assert!(p.force);
    let sin_forzar: ExportDocumentParams = argumento(
        &json!({ "params": { "verdictId": "v", "kind": "dossier", "format": "pdf", "language": "es" } }),
        "params",
    );
    assert!(!sin_forzar.force, "sin force no se fuerza");
}

#[test]
fn trigger_multiscan_recibe_el_perfil_en_camel_case() {
    use crate::commands::sources::ScanProfileParams;

    // ipc.ts -> invoke("trigger_multiscan", { profile: { name, keywords, discovery, windowDays, languages } })
    let payload = json!({ "profile": {
        "name": "facturas", "keywords": ["invoice"], "discovery": false,
        "windowDays": 180, "languages": ["en", "es"]
    }});
    let perfil: ScanProfileParams = argumento(&payload, "profile");
    assert_eq!(perfil.name, "facturas");
    assert_eq!(perfil.keywords, vec!["invoice"]);
    assert!(!perfil.discovery);
    assert_eq!(perfil.window_days, 180);
    assert_eq!(perfil.languages, vec!["en", "es"]);
}

#[test]
fn save_source_credentials_recibe_los_valores_por_campo() {
    use std::collections::BTreeMap;

    // ipc.ts -> invoke("save_source_credentials", { source, values: { token: "..." } })
    let payload = json!({ "source": "github", "values": { "token": "tok" } });
    let fuente: String = argumento(&payload, "source");
    let valores: BTreeMap<String, String> = argumento(&payload, "values");
    assert_eq!(fuente, "github");
    assert_eq!(valores.get("token").map(String::as_str), Some("tok"));
}
