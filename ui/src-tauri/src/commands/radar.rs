//! Comandos de lectura del radar.
//!
//! Todas las consultas castean a tipos primitivos en SQL (`::text`,
//! `::float8`). Eso evita arrastrar las features de uuid, chrono y decimal
//! de sqlx, y deja el contrato con el frontend explicito: lo que sale de
//! aqui es exactamente lo que declara `ui/src/types/radar.ts`.

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::db::{AppState, RadarResult};

/// Tenant de la instalacion local (ver migracion 001).
const LOCAL_TENANT: &str = "00000000-0000-0000-0000-000000000001";

#[derive(Debug, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FeedParams {
    pub limit: Option<i64>,
    pub min_score: Option<f64>,
    pub subreddit: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BoardParams {
    pub limit: Option<i64>,
    pub min_score: Option<f64>,
    pub qualified_only: Option<bool>,
}

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct RadarFeedEntry {
    pub signal_id: String,
    pub reddit_id: String,
    pub subreddit_name: String,
    pub author: String,
    pub content: String,
    pub created_utc: String,
    pub final_score: f64,
    pub urgency_tier: String,
    pub buying_intent: String,
    pub pain_severity: String,
    pub sentiment: String,
    pub risk_flags: Vec<String>,
    pub qualified: bool,
    pub job_statement: Option<String>,
    pub post_title: Option<String>,
    pub post_permalink: Option<String>,
}

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct OpportunityCluster {
    pub id: String,
    pub cluster_key: String,
    pub label: String,
    pub intent_type: String,
    pub keywords: Vec<String>,
    pub subreddits: Vec<String>,
    pub mention_count: i32,
    pub community_count: i32,
    pub linked_signals: i64,
    pub job_statement: String,
    pub current_solutions: Vec<String>,
    pub risk_flags: Vec<String>,
    pub spread_factor: f64,
    pub frequency_factor: f64,
    pub severity_factor: f64,
    pub recency_factor: f64,
    pub paid_signal_factor: f64,
    pub final_score: f64,
    pub urgency_tier: String,
    pub qualified: bool,
    pub evidence: serde_json::Value,
    pub created_at: String,
}

/// Feed de senales individuales que superaron el filtro de higiene.
#[tauri::command]
pub async fn get_radar_feed(
    state: State<'_, AppState>,
    params: FeedParams,
) -> RadarResult<Vec<RadarFeedEntry>> {
    let rows = sqlx::query_as::<_, RadarFeedEntry>(
        r#"
        SELECT
            signal_id::text        AS signal_id,
            reddit_id,
            subreddit_name,
            author,
            content,
            created_utc::text      AS created_utc,
            final_score::float8    AS final_score,
            urgency_tier::text     AS urgency_tier,
            buying_intent::text    AS buying_intent,
            pain_severity::text    AS pain_severity,
            sentiment::text        AS sentiment,
            risk_flags,
            qualified,
            job_statement,
            post_title,
            post_permalink
        FROM v_radar_feed
        WHERE tenant_id = $1::uuid
          AND final_score >= $2
          AND ($3::text IS NULL OR lower(subreddit_name) = lower($3))
        ORDER BY final_score DESC, created_utc DESC
        LIMIT $4
        "#,
    )
    .bind(LOCAL_TENANT)
    .bind(params.min_score.unwrap_or(0.0))
    .bind(params.subreddit)
    .bind(params.limit.unwrap_or(50))
    .fetch_all(&state.pool)
    .await?;

    Ok(rows)
}

/// Tablero de oportunidades consolidadas (migracion 002).
#[tauri::command]
pub async fn get_opportunity_board(
    state: State<'_, AppState>,
    params: BoardParams,
) -> RadarResult<Vec<OpportunityCluster>> {
    let rows = sqlx::query_as::<_, OpportunityCluster>(
        r#"
        SELECT
            id::text                   AS id,
            cluster_key,
            label,
            intent_type,
            keywords,
            subreddits,
            mention_count,
            community_count,
            linked_signals,
            job_statement,
            current_solutions,
            risk_flags,
            spread_factor::float8      AS spread_factor,
            frequency_factor::float8   AS frequency_factor,
            severity_factor::float8    AS severity_factor,
            recency_factor::float8     AS recency_factor,
            paid_signal_factor::float8 AS paid_signal_factor,
            final_score::float8        AS final_score,
            urgency_tier::text         AS urgency_tier,
            qualified,
            evidence,
            created_at::text           AS created_at
        FROM v_opportunity_board
        WHERE tenant_id = $1::uuid
          AND final_score >= $2
          AND (NOT $3 OR qualified)
        ORDER BY final_score DESC, created_at DESC
        LIMIT $4
        "#,
    )
    .bind(LOCAL_TENANT)
    .bind(params.min_score.unwrap_or(0.0))
    .bind(params.qualified_only.unwrap_or(false))
    .bind(params.limit.unwrap_or(20))
    .fetch_all(&state.pool)
    .await?;

    Ok(rows)
}
