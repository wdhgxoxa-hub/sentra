//! Comandos de escritura.
//!
//! Separados de `radar.rs` a proposito: leer y escribir tienen riesgos
//! distintos, y tener las mutaciones en un solo archivo hace evidente cual
//! es la superficie con la que un usuario puede cambiar el estado del
//! sistema.

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::commands::engine::{sidecar_url, with_token_pub};
use crate::db::{AppState, RadarError, RadarResult};

/// Tenant de la instalacion local (ver migracion 001).
const LOCAL_TENANT: &str = "00000000-0000-0000-0000-000000000001";

// ---------------------------------------------------------------------
// Validacion de oportunidades
// ---------------------------------------------------------------------

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct ClusterValidation {
    pub cluster_key: String,
    pub status: String,
    pub notes: Option<String>,
    pub assigned_to: Option<String>,
    pub validated_at: Option<String>,
    pub score_at_decision: Option<f64>,
    pub updated_at: String,
}

/// Estados admitidos, espejo del ENUM `validation_status`.
const VALID_STATUSES: [&str; 5] = ["new", "triaged", "validated", "rejected", "shipped"];

/// Registra el juicio humano sobre un problema recurrente.
///
/// Llega la `cluster_key` de la lectura que se esta viendo, pero el juicio
/// se guarda sobre la oportunidad (`opportunity_id`, D-G): la clave cambia
/// cuando el problema gana palabras entre escaneos, y el juicio tiene que
/// seguirle. Validar una fila de `opportunity_clusters` seria validar una
/// foto; validar la clave, perder el juicio en el siguiente escaneo.
///
/// `validated_at` se fija la primera vez que pasa a 'validated' y no se
/// borra despues: interesa saber cuando se tomo la decision aunque luego
/// cambie de estado.
#[tauri::command]
pub async fn update_opportunity_status(
    state: State<'_, AppState>,
    cluster_key: String,
    status: String,
    notes: Option<String>,
    assigned_to: Option<String>,
) -> RadarResult<ClusterValidation> {
    set_validation(&state.db.pool()?, &cluster_key, &status, notes, assigned_to).await
}

/// Logica de la validacion, separada del comando para poder probarla sin
/// levantar Tauri.
pub async fn set_validation(
    pool: &sqlx::PgPool,
    cluster_key: &str,
    status: &str,
    notes: Option<String>,
    assigned_to: Option<String>,
) -> RadarResult<ClusterValidation> {
    if !VALID_STATUSES.contains(&status) {
        return Err(RadarError::Invalid(format!(
            "Estado de validacion desconocido: '{status}'. Admitidos: {}",
            VALID_STATUSES.join(", ")
        )));
    }
    if cluster_key.trim().is_empty() {
        return Err(RadarError::Invalid(
            "Hace falta la clave del problema a validar".into(),
        ));
    }

    // La oportunidad de la ultima lectura con esa clave.
    let lectura = sqlx::query_as::<_, (String, Option<f64>)>(
        r#"
        SELECT opportunity_id::text, final_score::float8
        FROM opportunity_clusters
        WHERE tenant_id = $1::uuid AND cluster_key = $2
        ORDER BY created_at DESC
        LIMIT 1
        "#,
    )
    .bind(LOCAL_TENANT)
    .bind(cluster_key)
    .fetch_optional(pool)
    .await?;
    let Some((opportunity_id, puntuacion)) = lectura else {
        return Err(RadarError::Invalid(format!(
            "No hay ninguna oportunidad con la clave '{cluster_key}'"
        )));
    };

    let row = sqlx::query_as::<_, ClusterValidation>(
        r#"
        INSERT INTO cluster_validations (
            tenant_id, opportunity_id, cluster_key, status, notes, assigned_to,
            validated_at, score_at_decision
        )
        VALUES (
            $1::uuid, $6::uuid, $2, $3::validation_status, $4, $5,
            CASE WHEN $3 = 'validated' THEN now() ELSE NULL END,
            $7
        )
        ON CONFLICT (tenant_id, opportunity_id) DO UPDATE SET
            -- La ultima clave vista, informativa: la identidad no cambia.
            cluster_key  = EXCLUDED.cluster_key,
            status       = EXCLUDED.status,
            notes        = COALESCE(EXCLUDED.notes, cluster_validations.notes),
            assigned_to  = COALESCE(EXCLUDED.assigned_to, cluster_validations.assigned_to),
            -- Se conserva la fecha de la primera validacion.
            validated_at = COALESCE(cluster_validations.validated_at, EXCLUDED.validated_at),
            score_at_decision = EXCLUDED.score_at_decision,
            updated_at   = now()
        RETURNING
            cluster_key,
            status::text            AS status,
            notes,
            assigned_to,
            validated_at::text      AS validated_at,
            score_at_decision::float8 AS score_at_decision,
            updated_at::text        AS updated_at
        "#,
    )
    .bind(LOCAL_TENANT)
    .bind(cluster_key)
    .bind(status)
    .bind(notes)
    .bind(assigned_to)
    .bind(opportunity_id)
    .bind(puntuacion)
    .fetch_one(pool)
    .await?;

    Ok(row)
}

// ---------------------------------------------------------------------
// Configuracion de subreddits
// ---------------------------------------------------------------------

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpsertSubredditParams {
    pub name: String,
    pub listing: Option<String>,
    pub limit_per_page: Option<i16>,
    pub min_opportunity_score: Option<f64>,
    pub scan_interval_minutes: Option<i32>,
    pub status: Option<String>,
    pub tags: Option<Vec<String>>,
}

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct SubredditRow {
    pub subreddit_id: String,
    pub name: String,
    pub listing: String,
    pub status: String,
    pub limit_per_page: i16,
    pub min_opportunity_score: f64,
    pub scan_interval_minutes: i32,
    pub tags: Vec<String>,
}

/// Da de alta o actualiza un subreddit vigilado.
///
/// El nombre se normaliza (`r/SaaS` -> `SaaS`) porque el esquema lo valida
/// con un CHECK y la clave unica ignora mayusculas: `r/saas` y `SaaS` son
/// el mismo sitio.
#[tauri::command]
pub async fn upsert_subreddit(
    state: State<'_, AppState>,
    params: UpsertSubredditParams,
) -> RadarResult<SubredditRow> {
    save_subreddit(&state.db.pool()?, params).await
}

/// Logica del alta/edicion, separada del comando para poder probarla.
pub async fn save_subreddit(
    pool: &sqlx::PgPool,
    params: UpsertSubredditParams,
) -> RadarResult<SubredditRow> {
    let name = params
        .name
        .trim()
        .trim_start_matches("r/")
        .trim_start_matches('/')
        .to_string();

    if name.is_empty() {
        return Err(RadarError::Invalid(
            "El nombre del subreddit no puede estar vacio".into(),
        ));
    }

    let row = sqlx::query_as::<_, SubredditRow>(
        r#"
        INSERT INTO subreddits (
            tenant_id, name, listing, limit_per_page,
            min_opportunity_score, scan_interval_minutes, status, tags
        )
        VALUES (
            $1::uuid, $2, COALESCE($3, 'new')::listing_sort, COALESCE($4, 25),
            COALESCE($5, 60.0), COALESCE($6, 1440),
            COALESCE($7, 'active')::subreddit_status, COALESCE($8, '{}')
        )
        -- Se usan los PARAMETROS y no EXCLUDED: en el VALUES ya pasaron
        -- por COALESCE con su valor por defecto, asi que EXCLUDED nunca es
        -- nulo y machacaria lo que el usuario no quiso tocar.
        ON CONFLICT (tenant_id, name) DO UPDATE SET
            listing               = COALESCE($3::listing_sort, subreddits.listing),
            limit_per_page        = COALESCE($4, subreddits.limit_per_page),
            min_opportunity_score = COALESCE($5, subreddits.min_opportunity_score),
            scan_interval_minutes = COALESCE($6, subreddits.scan_interval_minutes),
            status                = COALESCE($7::subreddit_status, subreddits.status),
            tags                  = COALESCE($8, subreddits.tags),
            updated_at            = now()
        RETURNING
            id::text                     AS subreddit_id,
            name,
            listing::text                AS listing,
            status::text                 AS status,
            limit_per_page,
            min_opportunity_score::float8 AS min_opportunity_score,
            scan_interval_minutes,
            tags
        "#,
    )
    .bind(LOCAL_TENANT)
    .bind(name)
    .bind(params.listing)
    .bind(params.limit_per_page)
    .bind(params.min_opportunity_score)
    .bind(params.scan_interval_minutes)
    .bind(params.status)
    .bind(params.tags)
    .fetch_one(pool)
    .await?;

    Ok(row)
}

// ---------------------------------------------------------------------
// Cancelacion de escaneos
// ---------------------------------------------------------------------

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CancelResult {
    pub run_id: String,
    /// El sidecar tenia ese escaneo en marcha.
    pub was_active: bool,
    /// Se marco la ejecucion como cancelada en PostgreSQL.
    pub marked_in_database: bool,
}

#[derive(Debug, Serialize)]
struct CancelBody {
    #[serde(rename = "runId")]
    run_id: String,
}

#[derive(Debug, Deserialize)]
struct CancelEnvelope {
    #[serde(rename = "wasActive")]
    was_active: bool,
}

/// Interrumpe un escaneo en curso.
///
/// Hace dos cosas, y ninguna depende de que la otra funcione:
///
/// 1. Pide al sidecar que corte el grafo. La interrupcion es cooperativa:
///    ocurre entre nodos, nunca a mitad de uno, para no dejar el almacen
///    a medio escribir.
/// 2. Marca como `cancelled` la ejecucion en PostgreSQL, si ya existe fila.
///    Puede no existir todavia: la fila se crea al persistir, al final.
#[tauri::command]
pub async fn cancel_scan(
    state: State<'_, AppState>,
    run_id: String,
) -> RadarResult<CancelResult> {
    let was_active = match with_token_pub(
        state
            .http
            .post(format!("{}/api/scan/cancel", sidecar_url()))
            .timeout(std::time::Duration::from_secs(10))
            .json(&CancelBody {
                run_id: run_id.clone(),
            }),
    )
    .send()
    .await
    {
        Ok(response) if response.status().is_success() => response
            .json::<CancelEnvelope>()
            .await
            .map(|envelope| envelope.was_active)
            .unwrap_or(false),
        // Que el sidecar no conteste no impide marcar la ejecucion en la
        // base: quiza justo acaba de morirse, y es la razon de cancelar.
        _ => false,
    };

    // Sin base (D-F) la cancelacion en el motor sigue valiendo: solo no
    // queda marcada, igual que si el UPDATE fallara.
    let marked = match state.db.pool() {
        Ok(pool) => sqlx::query(
            r#"
            UPDATE pipeline_runs
               SET status      = 'cancelled',
                   finished_at = COALESCE(finished_at, now())
             WHERE tenant_id = $1::uuid
               AND id::text = $2
               AND status = 'running'
            "#,
        )
        .bind(LOCAL_TENANT)
        .bind(&run_id)
        .execute(&pool)
        .await
        .map(|result| result.rows_affected() > 0)
        .unwrap_or(false),
        Err(_) => false,
    };

    Ok(CancelResult {
        run_id,
        was_active,
        marked_in_database: marked,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    use crate::test_support::base_de_pruebas;

    const TEST_DB: &str = "rir_mutations_test";

    /// Obtiene el pool o salta el test si no hay PostgreSQL (ver test_support:
    /// si lo hay y la base no se puede preparar, el test falla con el motivo).
    macro_rules! pool_or_skip {
        () => {
            match base_de_pruebas(TEST_DB).await {
                Some(pool) => pool,
                None => return,
            }
        };
    }

    // --- Validacion de oportunidades ---

    /// Inserta una lectura de la oportunidad `opportunity_id` con la clave
    /// `clave`, como la escribe el motor tras un escaneo.
    async fn sembrar_lectura(pool: &sqlx::PgPool, clave: &str, opportunity_id: &str) {
        sqlx::query(
            r#"
            WITH r AS (
                INSERT INTO pipeline_runs (tenant_id, subreddit_name, status)
                VALUES ($1::uuid, 'SaaS', 'completed') RETURNING id
            )
            INSERT INTO opportunity_clusters (tenant_id, run_id, cluster_key, label,
                intent_type, mention_count, community_count, final_score, opportunity_id)
            SELECT $1::uuid, id, $2, $2, 'complaint', 2, 1, 42, $3::uuid FROM r
            "#,
        )
        .bind(LOCAL_TENANT)
        .bind(clave)
        .bind(opportunity_id)
        .execute(pool)
        .await
        .expect("no se pudo sembrar la lectura");
    }

    /// UUID nuevo, de la propia base, para no fijar ninguno en el codigo.
    async fn uuid_nuevo(pool: &sqlx::PgPool) -> String {
        sqlx::query_scalar::<_, String>("SELECT uuidv7()::text")
            .fetch_one(pool)
            .await
            .unwrap()
    }

    #[tokio::test]
    async fn a_key_without_readings_is_rejected() {
        let pool = pool_or_skip!();
        let result = set_validation(&pool, "sin-lecturas", "triaged", None, None).await;
        assert!(matches!(result, Err(RadarError::Invalid(_))));
    }

    /// AUD-019: la validacion es de la oportunidad, no de su clave. Cuando el
    /// problema gana palabras y su clave cambia, el juicio y el historial
    /// siguen con el.
    #[tokio::test]
    async fn validation_and_history_survive_a_key_change() {
        let pool = pool_or_skip!();
        let oportunidad = uuid_nuevo(&pool).await;
        sembrar_lectura(&pool, "complaint:factura|manual", &oportunidad).await;
        set_validation(&pool, "complaint:factura|manual", "triaged", Some("mirando".into()), None)
            .await
            .expect("no se pudo validar");

        sembrar_lectura(&pool, "complaint:factura|manual|horas", &oportunidad).await;
        let segunda = set_validation(&pool, "complaint:factura|manual|horas", "validated", None, None)
            .await
            .expect("no se pudo actualizar con la clave nueva");
        assert_eq!(segunda.notes.as_deref(), Some("mirando"), "es el mismo juicio");
        assert_eq!(segunda.cluster_key, "complaint:factura|manual|horas");

        let filas: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM cluster_validations WHERE opportunity_id = $1::uuid",
        )
        .bind(&oportunidad)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(filas, 1, "un solo juicio por oportunidad");

        let historial =
            crate::commands::radar::historial_de(&pool, "complaint:factura|manual|horas")
                .await
                .unwrap();
        assert_eq!(historial.len(), 2, "el historial incluye la lectura con la clave vieja");
    }

    #[tokio::test]
    async fn an_unknown_status_is_rejected() {
        let pool = pool_or_skip!();
        let result = set_validation(&pool, "problema", "inventado", None, None).await;
        assert!(matches!(result, Err(RadarError::Invalid(_))));
    }

    #[tokio::test]
    async fn an_empty_cluster_key_is_rejected() {
        let pool = pool_or_skip!();
        let result = set_validation(&pool, "   ", "validated", None, None).await;
        assert!(matches!(result, Err(RadarError::Invalid(_))));
    }

    #[tokio::test]
    async fn a_validation_can_be_created_and_updated() {
        let pool = pool_or_skip!();
        let oportunidad = uuid_nuevo(&pool).await;
        sembrar_lectura(&pool, "invoice+manual", &oportunidad).await;

        let first = set_validation(&pool, "invoice+manual", "triaged", Some("mirando".into()), None)
            .await
            .expect("no se pudo crear");
        assert_eq!(first.status, "triaged");
        assert_eq!(first.notes.as_deref(), Some("mirando"));
        assert!(first.validated_at.is_none());

        let second = set_validation(&pool, "invoice+manual", "validated", None, Some("david".into()))
            .await
            .expect("no se pudo actualizar");
        assert_eq!(second.status, "validated");
        assert!(second.validated_at.is_some(), "validated exige fecha");
        // Las notas anteriores no se pierden por no repetirlas.
        assert_eq!(second.notes.as_deref(), Some("mirando"));
        assert_eq!(second.assigned_to.as_deref(), Some("david"));
    }

    #[tokio::test]
    async fn the_first_validation_date_is_preserved() {
        let pool = pool_or_skip!();
        let oportunidad = uuid_nuevo(&pool).await;
        sembrar_lectura(&pool, "k", &oportunidad).await;

        let validated = set_validation(&pool, "k", "validated", None, None).await.unwrap();
        let fecha = validated.validated_at.clone().unwrap();

        let rejected = set_validation(&pool, "k", "rejected", None, None).await.unwrap();
        assert_eq!(rejected.status, "rejected");
        assert_eq!(
            rejected.validated_at.as_deref(),
            Some(fecha.as_str()),
            "la fecha de la decision original debe conservarse"
        );
    }

    // --- Subreddits ---

    fn params(name: &str) -> UpsertSubredditParams {
        UpsertSubredditParams {
            name: name.into(),
            listing: None,
            limit_per_page: None,
            min_opportunity_score: None,
            scan_interval_minutes: None,
            status: None,
            tags: None,
        }
    }

    #[tokio::test]
    async fn a_subreddit_name_is_normalised() {
        let pool = pool_or_skip!();
        let row = save_subreddit(&pool, params("r/SaaS")).await.expect("fallo");
        assert_eq!(row.name, "SaaS");
        assert_eq!(row.status, "active");
    }

    #[tokio::test]
    async fn an_empty_subreddit_name_is_rejected() {
        let pool = pool_or_skip!();
        let result = save_subreddit(&pool, params("  r/  ")).await;
        assert!(matches!(result, Err(RadarError::Invalid(_))));
    }

    #[tokio::test]
    async fn upserting_twice_updates_instead_of_duplicating() {
        let pool = pool_or_skip!();
        let first = save_subreddit(&pool, params("devops")).await.unwrap();

        let mut cambio = params("devops");
        cambio.status = Some("paused".into());
        cambio.tags = Some(vec!["infra".into(), "prioritario".into()]);
        let second = save_subreddit(&pool, cambio).await.unwrap();

        assert_eq!(first.subreddit_id, second.subreddit_id, "no debe duplicar");
        assert_eq!(second.status, "paused");
        assert_eq!(second.tags, vec!["infra", "prioritario"]);
    }

    #[tokio::test]
    async fn omitted_fields_keep_their_previous_value() {
        let pool = pool_or_skip!();

        let mut inicial = params("bookkeeping");
        inicial.limit_per_page = Some(50);
        inicial.tags = Some(vec!["contable".into()]);
        save_subreddit(&pool, inicial).await.unwrap();

        // Solo se cambia el estado: lo demas debe sobrevivir.
        let mut pausa = params("bookkeeping");
        pausa.status = Some("paused".into());
        let row = save_subreddit(&pool, pausa).await.unwrap();

        assert_eq!(row.limit_per_page, 50);
        assert_eq!(row.tags, vec!["contable"]);
    }
}
