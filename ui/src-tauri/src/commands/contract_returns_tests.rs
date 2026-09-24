//! Contratos de RETORNO entre Rust y `ui/src/types/radar.ts` (AUD-029).
//!
//! Cada comando serializa su struct de retorno con valores de prueba y se
//! compara el conjunto de claves con la interfaz TS que la recibe, leída de
//! `contract/ts_types.json`. Ese JSON lo genera el compilador de TypeScript
//! (`npm run contracts` en `ui/`), no se escribe a mano: si alguien cambia
//! un tipo en TS sin regenerarlo, `npm run contracts:check` falla.
//!
//! Los objetos anidados (desglose, evidencia, credenciales...) se comprueban
//! también, cada uno contra su propia interfaz.

use std::collections::BTreeSet;

use serde::Serialize;
use serde_json::Value;

use crate::commands::gemini;
use crate::commands::health::{AppHealth, ComponentHealth};
use crate::commands::mutations::CancelResult;
use crate::commands::settings::{AppSettings, GeminiSummary};

const TIPOS_TS: &str = include_str!("../../contract/ts_types.json");

fn claves_ts(interfaz: &str) -> BTreeSet<String> {
    let tipos: Value = serde_json::from_str(TIPOS_TS).expect("ts_types.json ilegible");
    tipos["interfaces"][interfaz]
        .as_array()
        .unwrap_or_else(|| panic!("la interfaz '{interfaz}' no está en ts_types.json"))
        .iter()
        .map(|v| v.as_str().unwrap().to_string())
        .collect()
}

fn claves(valor: &Value) -> BTreeSet<String> {
    valor
        .as_object()
        .expect("se esperaba un objeto JSON")
        .keys()
        .cloned()
        .collect()
}

/// Serializa `valor` y exige exactamente las claves de la interfaz TS.
fn cumple<T: Serialize>(valor: &T, interfaz: &str) -> Value {
    let json = serde_json::to_value(valor).unwrap();
    assert_eq!(
        claves(&json),
        claves_ts(interfaz),
        "la serialización Rust no coincide con la interfaz TS '{interfaz}'"
    );
    json
}

fn texto() -> String {
    "x".into()
}

#[test]
fn cancel_scan_devuelve_cancel_result() {
    cumple(
        &CancelResult {
            run_id: texto(),
            was_active: false,
            marked_in_database: false,
        },
        "CancelResult",
    );
}

#[test]
fn la_configuracion_devuelve_app_settings_y_sus_resumenes() {
    let json = cumple(
        &AppSettings {
            env_path: texto(),
            gemini: GeminiSummary {
                configured: false,
                key_masked: texto(),
                model: Some(texto()),
                general_model: Some(texto()),
            },
        },
        "AppSettings",
    );
    assert_eq!(claves(&json["gemini"]), claves_ts("GeminiSummary"));
    let lista = gemini::GeminiModelsResult {
        ok: true,
        code: Some(texto()),
        detail: texto(),
        models: vec![gemini::GeminiModel { id: texto(), display_name: texto() }],
        general: Some(texto()),
        documents: Some(texto()),
    };
    cumple(&lista, "GeminiModelsResult");
    let json_lista = serde_json::to_value(&lista).unwrap();
    assert_eq!(claves(&json_lista["models"][0]), claves_ts("GeminiModel"));
    cumple(
        &gemini::ProbeResult { ok: false, detail: texto(), code: Some("gemini_key_rejected".into()) },
        "ProbeResult",
    );
}

#[test]
fn export_document_devuelve_exported_document() {
    cumple(
        &crate::commands::documents::ExportedDocument { path: texto(), llm_calls: Some(1) },
        "ExportedDocument",
    );
}

#[test]
fn get_app_health_devuelve_app_health() {
    let json = cumple(
        &AppHealth {
            ok: true,
            version: texto(),
            app: ComponentHealth { ok: true, detail: texto() },
            postgres: ComponentHealth { ok: true, detail: texto() },
            sidecar: ComponentHealth { ok: true, detail: texto() },
            sidecar_info: None,
            sidecar_launch: Some(crate::sidecar::LaunchFailure {
                code: "python_not_found".into(),
                detail: texto(),
            }),
            motor_build: texto(),
        },
        "AppHealth",
    );
    assert_eq!(claves(&json["app"]), claves_ts("ComponentHealth"));
    assert_eq!(claves(&json["sidecarLaunch"]), claves_ts("LaunchFailure"));
}

#[test]
fn get_database_status_devuelve_database_status() {
    cumple(
        &crate::db::DatabaseStatus {
            connected: false,
            code: Some("database_unavailable".into()),
            detail: Some(texto()),
        },
        "DatabaseStatus",
    );
}

#[test]
fn las_fuentes_devuelven_sources_overview_source_card_y_probe() {
    use crate::commands::sources::{SourceCard, SourceCredentialState, SourceProbeResult, SourcesOverview};

    let credencial = SourceCredentialState {
        name: texto(),
        env_var: texto(),
        secret: true,
        required: true,
        configured: false,
    };
    cumple(&credencial, "SourceCredentialState");
    let tarjeta = SourceCard {
        source: texto(),
        display_name: texto(),
        terms_url: texto(),
        commercial_use_allowed: true,
        requires_credentials: true,
        credential_fields: vec![credencial],
        status: "verificada".into(),
        last_verified_at: None,
        error_code: None,
        detail: None,
        disabled: false,
        excluded_by_commercial_mode: false,
        active: true,
        cost_unit: "request".into(),
        cost_note: texto(),
    };
    cumple(&tarjeta, "SourceCard");
    cumple(
        &SourcesOverview { commercial_mode: false, sources: vec![tarjeta] },
        "SourcesOverview",
    );
    cumple(
        &SourceProbeResult { ok: true, code: None, detail: texto(), checked_at: None },
        "SourceProbeResult",
    );
}
