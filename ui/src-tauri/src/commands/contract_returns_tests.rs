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
use serde_json::{json, Value};

use crate::commands::architect;
use crate::commands::blueprint::{BlueprintDoc, BlueprintPhase, BlueprintQuote};
use crate::commands::engine::QuoteTranslation;
use crate::commands::health::{AppHealth, ComponentHealth, SourceState, SourceStatus};
use crate::commands::mutations::{CancelResult, ClusterValidation, SubredditRow};
use crate::commands::radar::{
    ClusterHistoryPoint, EvidenceQuote, OpportunityCluster, PipelineRun, RadarFeedEntry,
    ScoreBreakdown, SubredditHealth, TopItem, TopOpportunities,
};
use crate::commands::settings::{AppSettings, CredentialsSummary, GeminiSummary, ProbeResult};

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

fn desglose() -> ScoreBreakdown {
    ScoreBreakdown {
        spread_factor: 0.2,
        frequency_factor: 0.2,
        severity_factor: 0.0,
        recency_factor: 1.0,
        paid_signal_factor: 0.0,
        raw_score: 25.0,
        final_score: 25.0,
    }
}

fn cita() -> EvidenceQuote {
    EvidenceQuote {
        signal_id: texto(),
        subreddit: texto(),
        author: texto(),
        quote: texto(),
        url: None,
        score: 1.0,
        created_utc: Some(1_758_000_000.0),
    }
}

#[test]
fn get_radar_feed_devuelve_radar_feed_entry() {
    cumple(
        &RadarFeedEntry {
            signal_id: texto(),
            reddit_id: texto(),
            subreddit_name: texto(),
            author: texto(),
            content: texto(),
            created_utc: texto(),
            final_score: 1.0,
            urgency_tier: texto(),
            buying_intent: texto(),
            pain_severity: texto(),
            sentiment: texto(),
            risk_flags: vec![],
            qualified: false,
            job_statement: None,
            post_title: None,
            post_permalink: None,
            data_source: None,
        },
        "RadarFeedEntry",
    );
}

#[test]
fn get_opportunity_board_y_detail_devuelven_opportunity_cluster() {
    let json = cumple(
        &OpportunityCluster {
            id: texto(),
            cluster_key: texto(),
            label: texto(),
            intent_type: texto(),
            keywords: vec![],
            subreddits: vec![],
            mention_count: 1,
            community_count: 1,
            linked_signals: 1,
            job_statement: texto(),
            current_solutions: vec![],
            risk_flags: vec![],
            breakdown: desglose(),
            urgency_tier: texto(),
            qualified: false,
            evidence: vec![cita()],
            representative_reddit_id: None,
            representative_content: None,
            run_id: None,
            run_started_at: None,
            created_at: texto(),
            validation_status: texto(),
            validation_notes: None,
            validation_assignee: None,
            validated_at: None,
            cluster_stats: json!({}),
            data_source: None,
            opportunity_id: texto(),
        },
        "OpportunityCluster",
    );
    assert_eq!(claves(&json["breakdown"]), claves_ts("ScoreBreakdown"));
    assert_eq!(claves(&json["evidence"][0]), claves_ts("EvidenceQuote"));
}

/// La evidencia sale de PostgreSQL con las claves que escribe Python
/// (`aggregation.build_clusters`, snake_case). Rust la lee así y la entrega
/// en camelCase: sin este paso, `signalId` llegaba `undefined` (AUD-032).
#[test]
fn la_evidencia_se_lee_en_snake_case_y_se_entrega_en_camel_case() {
    let de_python = json!({
        "signal_id": "t3_a", "subreddit": "SaaS", "author": "u", "quote": "q",
        "url": "https://reddit.com/x", "score": 55.0, "created_utc": 1758000000.0
    });
    let cita: EvidenceQuote = serde_json::from_value(de_python).unwrap();
    assert_eq!(cita.signal_id, "t3_a");
    assert_eq!(cita.created_utc, Some(1_758_000_000.0));
    cumple(&cita, "EvidenceQuote");
}

#[test]
fn get_cluster_history_devuelve_cluster_history_point() {
    cumple(
        &ClusterHistoryPoint {
            id: texto(),
            run_id: None,
            final_score: 1.0,
            urgency_tier: texto(),
            mention_count: 1,
            community_count: 1,
            qualified: false,
            created_at: texto(),
            data_source: None,
        },
        "ClusterHistoryPoint",
    );
}

#[test]
fn get_subreddits_devuelve_subreddit_health() {
    cumple(
        &SubredditHealth {
            subreddit_id: texto(),
            name: texto(),
            status: texto(),
            listing: texto(),
            last_scanned_at: None,
            next_scan_at: None,
            consecutive_failures: 0,
            last_run_id: None,
            last_run_status: None,
            last_run_started_at: None,
            last_run_duration_ms: None,
            fetched: None,
            qualified: None,
            error_count: None,
            last_run_data_source: None,
        },
        "SubredditHealth",
    );
}

#[test]
fn get_pipeline_runs_devuelve_pipeline_run() {
    cumple(
        &PipelineRun {
            id: texto(),
            subreddit_name: texto(),
            status: texto(),
            trigger_source: texto(),
            started_at: texto(),
            finished_at: None,
            duration_ms: None,
            cycles: 0,
            fetched: 0,
            filtered_in: 0,
            filtered_out: 0,
            analyzed: 0,
            stored: 0,
            qualified: 0,
            rejected: 0,
            errors: json!([]),
            error_count: 0,
            data_source: None,
        },
        "PipelineRun",
    );
}

#[test]
fn get_top_opportunities_devuelve_top_opportunities() {
    let json = cumple(
        &TopOpportunities {
            run_id: texto(),
            status: texto(),
            data_source: None,
            target: 6,
            found: 1,
            complete: false,
            reason: None,
            finished_at: None,
            items: vec![TopItem {
                position: 1,
                cluster_key: texto(),
                label: texto(),
                final_score: 1.0,
                mention_count: 1,
                community_count: 1,
            }],
        },
        "TopOpportunities",
    );
    assert_eq!(claves(&json["items"][0]), claves_ts("TopItem"));
}

#[test]
fn las_mutaciones_devuelven_sus_tipos() {
    cumple(
        &ClusterValidation {
            cluster_key: texto(),
            status: texto(),
            notes: None,
            assigned_to: None,
            validated_at: None,
            score_at_decision: None,
            updated_at: texto(),
        },
        "ClusterValidation",
    );
    cumple(
        &SubredditRow {
            subreddit_id: texto(),
            name: texto(),
            listing: texto(),
            status: texto(),
            limit_per_page: 25,
            min_opportunity_score: 60.0,
            scan_interval_minutes: 60,
            tags: vec![],
        },
        "SubredditRow",
    );
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
            fetcher_mode: texto(),
            credentials: CredentialsSummary {
                configured: false,
                client_id_masked: texto(),
                user_agent: texto(),
                has_user: false,
            },
            env_path: texto(),
            synthetic_posts: 15,
            gemini: GeminiSummary {
                configured: false,
                key_masked: texto(),
                model: texto(),
            },
        },
        "AppSettings",
    );
    assert_eq!(claves(&json["credentials"]), claves_ts("CredentialsSummary"));
    assert_eq!(claves(&json["gemini"]), claves_ts("GeminiSummary"));
    cumple(&ProbeResult { ok: true, detail: texto() }, "ProbeResult");
    cumple(&architect::ProbeResult { ok: true, detail: texto() }, "ProbeResult");
}

#[test]
fn generate_blueprint_devuelve_blueprint_doc() {
    let json = cumple(
        &BlueprintDoc {
            product_name: texto(),
            one_liner: texto(),
            executive_summary: texto(),
            problem: texto(),
            solution: texto(),
            mvp: vec![BlueprintPhase { name: texto(), items: vec![] }],
            why_existing_fail: texto(),
            monetisation: texto(),
            evidence: vec![BlueprintQuote {
                quote: texto(),
                subreddit: texto(),
                author: texto(),
                url: texto(),
            }],
            distinct_quotes: 1,
            markdown: texto(),
            source_notice: texto(),
            data_source: None,
        },
        "BlueprintDoc",
    );
    assert_eq!(claves(&json["mvp"][0]), claves_ts("BlueprintPhase"));
    assert_eq!(claves(&json["evidence"][0]), claves_ts("BlueprintQuote"));
}

#[test]
fn translate_quotes_devuelve_quote_translation() {
    cumple(
        &QuoteTranslation {
            text: texto(),
            engine: texto(),
            approximate: false,
        },
        "QuoteTranslation",
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
            source: Some(SourceStatus {
                state: SourceState::Demo,
                last_success_at: None,
                error_code: None,
            }),
            sidecar_launch: Some(crate::sidecar::LaunchFailure {
                code: "python_not_found".into(),
                detail: texto(),
            }),
        },
        "AppHealth",
    );
    assert_eq!(claves(&json["app"]), claves_ts("ComponentHealth"));
    assert_eq!(claves(&json["source"]), claves_ts("SourceStatus"));
    assert_eq!(claves(&json["sidecarLaunch"]), claves_ts("LaunchFailure"));
}

#[test]
fn generate_architecture_emite_architect_chunk_con_su_fallo_tipado() {
    let json = cumple(
        &architect::ArchitectChunk {
            cluster_key: texto(),
            text: texto(),
            done: false,
            error: Some(architect::ArchitectFailure {
                code: "gemini_incomplete".into(),
                detail: texto(),
                missing: vec![texto()],
            }),
        },
        "ArchitectChunk",
    );
    assert_eq!(claves(&json["error"]), claves_ts("ArchitectFailure"));
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
