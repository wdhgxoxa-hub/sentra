//! Comandos de lectura del radar, resueltos contra PostgreSQL.
//!
//! Todas las consultas castean a tipos primitivos en SQL (`::text`,
//! `::float8`). Eso evita arrastrar las features de uuid, chrono y decimal
//! de sqlx, y deja el contrato explicito.
//!
//! Los clusters usan dos structs: uno plano que mapea la fila
//! (`OpportunityClusterRow`) y otro anidado que sale al WebView
//! (`OpportunityCluster`). SQL devuelve columnas planas, pero el frontend
//! trata el desglose del scoring como una unidad y pintarlo es mas claro
//! con un objeto que con cinco campos sueltos.

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::db::{AppState, RadarResult};

/// Tenant de la instalacion local (ver migracion 001).
const LOCAL_TENANT: &str = "00000000-0000-0000-0000-000000000001";

// ---------------------------------------------------------------------
// Parametros
// ---------------------------------------------------------------------

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

// ---------------------------------------------------------------------
// Feed de senales individuales
// ---------------------------------------------------------------------

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

/// Senales individuales que superaron el filtro de higiene.
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

// ---------------------------------------------------------------------
// Oportunidades consolidadas
// ---------------------------------------------------------------------

/// Mapeo directo de la fila: columnas planas, como las devuelve SQL.
#[derive(Debug, sqlx::FromRow)]
struct OpportunityClusterRow {
    id: String,
    cluster_key: String,
    label: String,
    intent_type: String,
    keywords: Vec<String>,
    subreddits: Vec<String>,
    mention_count: i32,
    community_count: i32,
    linked_signals: i64,
    job_statement: String,
    current_solutions: Vec<String>,
    risk_flags: Vec<String>,
    spread_factor: f64,
    frequency_factor: f64,
    severity_factor: f64,
    recency_factor: f64,
    paid_signal_factor: f64,
    raw_score: f64,
    final_score: f64,
    urgency_tier: String,
    qualified: bool,
    evidence: serde_json::Value,
    representative_reddit_id: Option<String>,
    representative_content: Option<String>,
    run_id: Option<String>,
    run_started_at: Option<String>,
    created_at: String,
    validation_status: String,
    validation_notes: Option<String>,
    validation_assignee: Option<String>,
    validated_at: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ScoreBreakdown {
    pub spread_factor: f64,
    pub frequency_factor: f64,
    pub severity_factor: f64,
    pub recency_factor: f64,
    pub paid_signal_factor: f64,
    pub raw_score: f64,
    pub final_score: f64,
}

#[derive(Debug, Serialize)]
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
    pub breakdown: ScoreBreakdown,
    pub urgency_tier: String,
    pub qualified: bool,
    pub evidence: serde_json::Value,
    pub representative_reddit_id: Option<String>,
    pub representative_content: Option<String>,
    pub run_id: Option<String>,
    pub run_started_at: Option<String>,
    pub created_at: String,
    /// Juicio humano sobre el problema. 'new' si nadie lo ha mirado.
    pub validation_status: String,
    pub validation_notes: Option<String>,
    pub validation_assignee: Option<String>,
    pub validated_at: Option<String>,
}

impl From<OpportunityClusterRow> for OpportunityCluster {
    fn from(row: OpportunityClusterRow) -> Self {
        Self {
            breakdown: ScoreBreakdown {
                spread_factor: row.spread_factor,
                frequency_factor: row.frequency_factor,
                severity_factor: row.severity_factor,
                recency_factor: row.recency_factor,
                paid_signal_factor: row.paid_signal_factor,
                raw_score: row.raw_score,
                final_score: row.final_score,
            },
            id: row.id,
            cluster_key: row.cluster_key,
            label: row.label,
            intent_type: row.intent_type,
            keywords: row.keywords,
            subreddits: row.subreddits,
            mention_count: row.mention_count,
            community_count: row.community_count,
            linked_signals: row.linked_signals,
            job_statement: row.job_statement,
            current_solutions: row.current_solutions,
            risk_flags: row.risk_flags,
            urgency_tier: row.urgency_tier,
            qualified: row.qualified,
            evidence: row.evidence,
            representative_reddit_id: row.representative_reddit_id,
            representative_content: row.representative_content,
            run_id: row.run_id,
            run_started_at: row.run_started_at,
            created_at: row.created_at,
            validation_status: row.validation_status,
            validation_notes: row.validation_notes,
            validation_assignee: row.validation_assignee,
            validated_at: row.validated_at,
        }
    }
}

/// Columnas del tablero, compartidas por el listado y el detalle.
const BOARD_COLUMNS: &str = r#"
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
    (spread_factor * 25 + frequency_factor * 25 + severity_factor * 20
     + recency_factor * 15 + paid_signal_factor * 15)::float8 AS raw_score,
    final_score::float8        AS final_score,
    urgency_tier::text         AS urgency_tier,
    qualified,
    evidence,
    representative_reddit_id,
    representative_content,
    run_id::text               AS run_id,
    run_started_at::text       AS run_started_at,
    created_at::text           AS created_at,
    validation_status::text    AS validation_status,
    validation_notes,
    validation_assignee,
    validated_at::text         AS validated_at
"#;

/// Tablero de problemas recurrentes consolidados (migracion 002).
#[tauri::command]
pub async fn get_opportunity_board(
    state: State<'_, AppState>,
    params: BoardParams,
) -> RadarResult<Vec<OpportunityCluster>> {
    // DISTINCT ON por cluster_key: la tabla guarda una lectura por
    // ejecucion, asi que sin esto el tablero mostraria el mismo problema
    // repetido tantas veces como se haya escaneado, como si fueran
    // oportunidades distintas. Interesa la lectura mas reciente de cada uno.
    let sql = format!(
        r#"
        SELECT * FROM (
            SELECT DISTINCT ON (cluster_key) {BOARD_COLUMNS}
            FROM v_opportunity_board
            WHERE tenant_id = $1::uuid
              AND final_score >= $2
              AND (NOT $3 OR qualified)
            ORDER BY cluster_key, created_at DESC
        ) ultimas
        ORDER BY final_score DESC, created_at DESC
        LIMIT $4
        "#
    );

    let rows = sqlx::query_as::<_, OpportunityClusterRow>(&sql)
        .bind(LOCAL_TENANT)
        .bind(params.min_score.unwrap_or(0.0))
        .bind(params.qualified_only.unwrap_or(false))
        .bind(params.limit.unwrap_or(20))
        .fetch_all(&state.pool)
        .await?;

    Ok(rows.into_iter().map(Into::into).collect())
}

/// Ficha de una oportunidad por su clave natural.
///
/// Devuelve la lectura MAS RECIENTE: `opportunity_clusters` guarda una fila
/// por ejecucion, y la ficha debe mostrar el estado actual del problema.
#[tauri::command]
pub async fn get_opportunity_detail(
    state: State<'_, AppState>,
    cluster_key: String,
) -> RadarResult<Option<OpportunityCluster>> {
    cluster_por_clave(&state.pool, &cluster_key).await
}

/// La misma lectura, sin pasar por el comando.
///
/// La necesita el generador de especificaciones, que parte del cluster tal
/// como esta en la base y no de lo que la ventana tuviera cargado.
pub async fn cluster_por_clave(
    pool: &sqlx::PgPool,
    cluster_key: &str,
) -> RadarResult<Option<OpportunityCluster>> {
    let sql = format!(
        r#"
        SELECT {BOARD_COLUMNS}
        FROM v_opportunity_board
        WHERE tenant_id = $1::uuid AND cluster_key = $2
        ORDER BY created_at DESC
        LIMIT 1
        "#
    );

    let row = sqlx::query_as::<_, OpportunityClusterRow>(&sql)
        .bind(LOCAL_TENANT)
        .bind(cluster_key)
        .fetch_optional(pool)
        .await?;

    Ok(row.map(Into::into))
}

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct ClusterHistoryPoint {
    pub id: String,
    pub run_id: Option<String>,
    pub final_score: f64,
    pub urgency_tier: String,
    pub mention_count: i32,
    pub community_count: i32,
    pub qualified: bool,
    pub created_at: String,
}

/// Lecturas sucesivas del mismo problema, de la mas reciente hacia atras.
///
/// Es lo que permite ver que un dolor paso de 2 a 9 comunidades: ese
/// movimiento vale mas que la foto fija.
#[tauri::command]
pub async fn get_cluster_history(
    state: State<'_, AppState>,
    cluster_key: String,
) -> RadarResult<Vec<ClusterHistoryPoint>> {
    let rows = sqlx::query_as::<_, ClusterHistoryPoint>(
        r#"
        SELECT
            id::text            AS id,
            run_id::text        AS run_id,
            final_score::float8 AS final_score,
            urgency_tier::text  AS urgency_tier,
            mention_count,
            community_count,
            qualified,
            created_at::text    AS created_at
        FROM opportunity_clusters
        WHERE tenant_id = $1::uuid AND cluster_key = $2
        ORDER BY created_at DESC
        LIMIT 100
        "#,
    )
    .bind(LOCAL_TENANT)
    .bind(cluster_key)
    .fetch_all(&state.pool)
    .await?;

    Ok(rows)
}

// ---------------------------------------------------------------------
// Configuracion y telemetria
// ---------------------------------------------------------------------

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct SubredditHealth {
    pub subreddit_id: String,
    pub name: String,
    pub status: String,
    pub listing: String,
    pub last_scanned_at: Option<String>,
    pub next_scan_at: Option<String>,
    pub consecutive_failures: i16,
    pub last_run_id: Option<String>,
    pub last_run_status: Option<String>,
    pub last_run_started_at: Option<String>,
    pub last_run_duration_ms: Option<i32>,
    pub fetched: Option<i32>,
    pub qualified: Option<i32>,
    pub error_count: Option<i32>,
}

/// Subreddits vigilados con el resultado de su ultimo escaneo.
///
/// No usa la vista `v_subreddit_health` porque esta no expone `listing`, y
/// el boton de escanear necesita saber con que orden hacerlo.
#[tauri::command]
pub async fn get_subreddits(
    state: State<'_, AppState>,
) -> RadarResult<Vec<SubredditHealth>> {
    let rows = sqlx::query_as::<_, SubredditHealth>(
        r#"
        SELECT DISTINCT ON (s.id)
            s.id::text              AS subreddit_id,
            s.name,
            s.status::text          AS status,
            s.listing::text         AS listing,
            s.last_scanned_at::text AS last_scanned_at,
            s.next_scan_at::text    AS next_scan_at,
            s.consecutive_failures,
            r.id::text              AS last_run_id,
            r.status::text          AS last_run_status,
            r.started_at::text      AS last_run_started_at,
            r.duration_ms           AS last_run_duration_ms,
            r.fetched,
            r.qualified,
            r.error_count
        FROM subreddits s
        LEFT JOIN pipeline_runs r ON r.subreddit_id = s.id
        WHERE s.tenant_id = $1::uuid
        ORDER BY s.id, r.started_at DESC NULLS LAST
        "#,
    )
    .bind(LOCAL_TENANT)
    .fetch_all(&state.pool)
    .await?;

    Ok(rows)
}

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct PipelineRun {
    pub id: String,
    pub subreddit_name: String,
    pub status: String,
    pub trigger_source: String,
    pub started_at: String,
    pub finished_at: Option<String>,
    pub duration_ms: Option<i32>,
    pub cycles: i16,
    pub fetched: i32,
    pub filtered_in: i32,
    pub filtered_out: i32,
    pub analyzed: i32,
    pub stored: i32,
    pub qualified: i32,
    pub rejected: i32,
    pub errors: serde_json::Value,
    pub error_count: i32,
}

/// Telemetria de las ultimas ejecuciones del grafo.
#[tauri::command]
pub async fn get_pipeline_runs(
    state: State<'_, AppState>,
    limit: Option<i64>,
) -> RadarResult<Vec<PipelineRun>> {
    let rows = sqlx::query_as::<_, PipelineRun>(
        r#"
        SELECT
            id::text          AS id,
            subreddit_name,
            status::text      AS status,
            trigger_source,
            started_at::text  AS started_at,
            finished_at::text AS finished_at,
            duration_ms,
            cycles,
            fetched,
            filtered_in,
            filtered_out,
            analyzed,
            stored,
            qualified,
            rejected,
            errors,
            error_count
        FROM pipeline_runs
        WHERE tenant_id = $1::uuid
        ORDER BY started_at DESC
        LIMIT $2
        "#,
    )
    .bind(LOCAL_TENANT)
    .bind(limit.unwrap_or(50))
    .fetch_all(&state.pool)
    .await?;

    Ok(rows)
}

// ---------------------------------------------------------------------
// Top N de la última ejecución (AUD-007)
// ---------------------------------------------------------------------

/// Una oportunidad del Top N, con la posición que le dio el motor.
#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct TopItem {
    pub position: i16,
    pub cluster_key: String,
    pub label: String,
    pub final_score: f64,
    pub mention_count: i32,
    pub community_count: i32,
}

/// Resultado de la última ejecución terminada.
///
/// `target` sale de la base (lo escribió el motor desde `TOP_N`): la interfaz
/// no repite el número. `items` son solo las cualificadas que entraron en el
/// ranking; nunca se rellena.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TopOpportunities {
    pub run_id: String,
    pub status: String,
    /// "demo" o "reddit"; `None` si la ejecución no lo registró.
    pub data_source: Option<String>,
    pub target: i16,
    pub found: i16,
    pub complete: bool,
    /// Motivo de un resultado incompleto; `None` si se alcanzó el objetivo.
    pub reason: Option<String>,
    pub finished_at: Option<String>,
    pub items: Vec<TopItem>,
}

#[derive(sqlx::FromRow)]
struct TopRunRow {
    run_id: String,
    status: String,
    data_source: Option<String>,
    target: i16,
    found: i16,
    reason: Option<String>,
    finished_at: Option<String>,
}

/// La consulta, separada del comando para poder probarla sin Tauri.
pub async fn top_de_la_ultima_ejecucion(
    pool: &sqlx::PgPool,
) -> RadarResult<Option<TopOpportunities>> {
    let Some(run) = sqlx::query_as::<_, TopRunRow>(
        r#"
        SELECT
            id::text              AS run_id,
            status::text          AS status,
            data_source,
            top_n_target          AS target,
            top_n_found           AS found,
            top_n_reason::text    AS reason,
            finished_at::text     AS finished_at
        FROM pipeline_runs
        WHERE tenant_id = $1::uuid
          AND top_n_target IS NOT NULL
          AND status IN ('completed', 'failed')
        ORDER BY started_at DESC
        LIMIT 1
        "#,
    )
    .bind(LOCAL_TENANT)
    .fetch_optional(pool)
    .await?
    else {
        return Ok(None);
    };

    let items = sqlx::query_as::<_, TopItem>(
        r#"
        SELECT
            top_rank            AS position,
            cluster_key,
            label,
            final_score::float8 AS final_score,
            mention_count,
            community_count
        FROM opportunity_clusters
        WHERE tenant_id = $1::uuid
          AND run_id = $2::uuid
          AND top_rank IS NOT NULL
        ORDER BY top_rank
        "#,
    )
    .bind(LOCAL_TENANT)
    .bind(&run.run_id)
    .fetch_all(pool)
    .await?;

    Ok(Some(TopOpportunities {
        complete: run.found >= run.target,
        run_id: run.run_id,
        status: run.status,
        data_source: run.data_source,
        target: run.target,
        found: run.found,
        reason: run.reason,
        finished_at: run.finished_at,
        items,
    }))
}

/// Top N de la última ejecución terminada, o `None` si aún no hay ninguna.
#[tauri::command]
pub async fn get_top_opportunities(
    state: State<'_, AppState>,
) -> RadarResult<Option<TopOpportunities>> {
    top_de_la_ultima_ejecucion(&state.pool).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::base_de_pruebas;

    /// Obtiene la base o salta el test si no hay PostgreSQL configurado.
    macro_rules! base_o_saltar {
        ($nombre:expr) => {
            match base_de_pruebas($nombre).await {
                Some(pool) => pool,
                None => {
                    eprintln!("omitido: sin PostgreSQL local configurado");
                    return;
                }
            }
        };
    }

    async fn sembrar_run(
        pool: &sqlx::PgPool,
        status: &str,
        found: i16,
        reason: Option<&str>,
        hace_minutos: i32,
    ) -> String {
        sqlx::query_scalar::<_, String>(
            r#"
            INSERT INTO pipeline_runs (tenant_id, subreddit_name, status, started_at,
                                       top_n_target, top_n_found, top_n_reason, data_source)
            VALUES ($1::uuid, 'SaaS', $2::run_status, now() - make_interval(mins => $3),
                    6, $4, $5::top_n_reason, 'demo')
            RETURNING id::text
            "#,
        )
        .bind(LOCAL_TENANT)
        .bind(status)
        .bind(hace_minutos)
        .bind(found)
        .bind(reason)
        .fetch_one(pool)
        .await
        .expect("no se pudo sembrar la ejecucion")
    }

    async fn sembrar_cluster(pool: &sqlx::PgPool, run: &str, clave: &str, puntos: f64, rank: Option<i16>) {
        sqlx::query(
            r#"
            INSERT INTO opportunity_clusters (tenant_id, run_id, cluster_key, label,
                mention_count, community_count, final_score, qualified, top_rank)
            VALUES ($1::uuid, $2::uuid, $3, $3, 5, 3, $4, $5, $6)
            "#,
        )
        .bind(LOCAL_TENANT)
        .bind(run)
        .bind(clave)
        .bind(puntos)
        .bind(rank.is_some())
        .bind(rank)
        .execute(pool)
        .await
        .expect("no se pudo sembrar el cluster");
    }

    #[tokio::test]
    async fn sin_ejecuciones_no_hay_top() {
        let pool = base_o_saltar!("rir_top_vacio_test");
        assert!(top_de_la_ultima_ejecucion(&pool).await.unwrap().is_none());
    }

    #[tokio::test]
    async fn solo_las_rankeadas_y_en_su_orden() {
        let pool = base_o_saltar!("rir_top_orden_test");
        let run = sembrar_run(&pool, "completed", 2, Some("datos_insuficientes"), 1).await;
        sembrar_cluster(&pool, &run, "segunda", 70.0, Some(2)).await;
        sembrar_cluster(&pool, &run, "primera", 80.0, Some(1)).await;
        sembrar_cluster(&pool, &run, "fuera", 90.0, None).await;

        let top = top_de_la_ultima_ejecucion(&pool).await.unwrap().expect("sin top");
        let claves: Vec<_> = top.items.iter().map(|i| i.cluster_key.as_str()).collect();
        assert_eq!(claves, ["primera", "segunda"], "no se rellena con las no rankeadas");
        assert_eq!(top.items[0].position, 1);
        assert_eq!((top.target, top.found, top.complete), (6, 2, false));
        assert_eq!(top.reason.as_deref(), Some("datos_insuficientes"));
        assert_eq!(top.data_source.as_deref(), Some("demo"));
    }

    #[tokio::test]
    async fn se_usa_la_ultima_ejecucion_terminada() {
        let pool = base_o_saltar!("rir_top_ultima_test");
        let vieja = sembrar_run(&pool, "completed", 0, Some("fuentes_agotadas"), 30).await;
        let nueva = sembrar_run(&pool, "failed", 0, Some("sin_acceso_reddit"), 10).await;
        let _en_curso = sembrar_run(&pool, "running", 0, Some("limite_ciclos"), 1).await;

        let top = top_de_la_ultima_ejecucion(&pool).await.unwrap().expect("sin top");
        assert_eq!(top.run_id, nueva);
        assert_ne!(top.run_id, vieja);
        assert_eq!(top.reason.as_deref(), Some("sin_acceso_reddit"));
    }
}
