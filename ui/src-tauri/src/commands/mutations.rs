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
/// Va por `cluster_key` y no por el id de una fila de `opportunity_clusters`
/// porque esa tabla guarda una lectura por ejecucion: validar una fila seria
/// validar una foto. El problema sobrevive a cada escaneo.
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
    set_validation(&state.pool, &cluster_key, &status, notes, assigned_to).await
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

    let row = sqlx::query_as::<_, ClusterValidation>(
        r#"
        INSERT INTO cluster_validations (
            tenant_id, cluster_key, status, notes, assigned_to,
            validated_at, score_at_decision
        )
        VALUES (
            $1::uuid, $2, $3::validation_status, $4, $5,
            CASE WHEN $3 = 'validated' THEN now() ELSE NULL END,
            (SELECT final_score FROM opportunity_clusters
              WHERE tenant_id = $1::uuid AND cluster_key = $2
              ORDER BY created_at DESC LIMIT 1)
        )
        ON CONFLICT (tenant_id, cluster_key) DO UPDATE SET
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
    save_subreddit(&state.pool, params).await
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

    let marked = sqlx::query(
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
    .execute(&state.pool)
    .await
    .map(|result| result.rows_affected() > 0)
    .unwrap_or(false);

    Ok(CancelResult {
        run_id,
        was_active,
        marked_in_database: marked,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const TEST_DB: &str = "rir_mutations_test";

    /// Credenciales de la base local, sin incrustar secretos en el codigo.
    ///
    /// sqlx no lee `pgpass.conf` como hace libpq, asi que se lee aqui. Si no
    /// hay credenciales, los tests se saltan en lugar de fallar: no todas las
    /// maquinas tienen un PostgreSQL local.
    fn local_options(database: &str) -> Option<sqlx::postgres::PgConnectOptions> {
        use sqlx::postgres::PgConnectOptions;

        if let Ok(url) = std::env::var("RIR_PG_TEST_URL") {
            return url.parse::<PgConnectOptions>().ok().map(|o| o.database(database));
        }

        let appdata = std::env::var("APPDATA").ok()?;
        let path = std::path::Path::new(&appdata)
            .join("postgresql")
            .join("pgpass.conf");
        let content = std::fs::read_to_string(path).ok()?;

        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let parts: Vec<&str> = line.splitn(5, ':').collect();
            if parts.len() == 5 && parts[0] == "localhost" && parts[3] == "postgres" {
                return Some(
                    PgConnectOptions::new()
                        .host("localhost")
                        .port(parts[1].parse().unwrap_or(5432))
                        .username("postgres")
                        .password(parts[4])
                        .database(database),
                );
            }
        }
        None
    }

    /// La BASE se crea una sola vez; el POOL, uno por test.
    ///
    /// Dos restricciones que chocan: cargo ejecuta los tests en paralelo, asi
    /// que no pueden hacer DROP/CREATE de la misma base a la vez; y cada
    /// `#[tokio::test]` levanta y destruye su propio runtime, asi que un pool
    /// compartido entre ellos acaba con conexiones de un runtime ya muerto
    /// ("A Tokio 1.x context was found, but it is being shutdown").
    ///
    /// La base se prepara en su propio runtime, bajo un `OnceLock`; cada test
    /// abre luego su pool y usa claves propias para no pisar a los demas.
    static DB_READY: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

    fn ensure_database() -> bool {
        *DB_READY.get_or_init(|| {
            // En un hilo aparte: crear un runtime dentro del runtime del
            // test provoca "Cannot start a runtime from within a runtime".
            std::thread::spawn(|| {
                tokio::runtime::Runtime::new()
                    .map(|runtime| runtime.block_on(build_database()))
                    .unwrap_or(false)
            })
            .join()
            .unwrap_or(false)
        })
    }

    async fn shared_pool() -> Option<sqlx::PgPool> {
        if !ensure_database() {
            return None;
        }
        connect_pool().await
    }

    /// Abre un pool nuevo sobre la base ya preparada.
    ///
    /// El search_path se fija en la conexion, igual que en produccion
    /// (ver db.rs): sin eso cada conexion busca las tablas en `public` y no
    /// las encuentra, porque viven en el esquema `radar`.
    async fn connect_pool() -> Option<sqlx::PgPool> {
        sqlx::postgres::PgPoolOptions::new()
            .max_connections(4)
            .after_connect(|conn, _| {
                Box::pin(async move {
                    sqlx::query("SET search_path = radar, public")
                        .execute(conn)
                        .await?;
                    Ok(())
                })
            })
            .connect_with(local_options(TEST_DB)?)
            .await
            .ok()
    }

    /// Crea la base y aplica las migraciones reales.
    ///
    /// Se leen los .sql del repositorio en lugar de replicar el esquema:
    /// un test contra un esquema inventado no prueba nada del de verdad.
    async fn build_database() -> bool {
        use sqlx::{Connection, Executor, PgConnection};

        let Some(admin_options) = local_options("postgres") else {
            return false;
        };
        let Ok(mut admin) = PgConnection::connect_with(&admin_options).await else {
            return false;
        };

        let _ = admin
            .execute(format!(r#"DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)"#).as_str())
            .await;
        admin
            .execute(format!(r#"CREATE DATABASE "{TEST_DB}""#).as_str())
            .await
            .expect("no se pudo crear la base de pruebas");

        let Some(pool) = connect_pool().await else {
            return false;
        };

        let Some(root) = crate::sidecar::project_root_for_tests() else {
            return false;
        };
        let dir = root.join("sql").join("migrations");
        let mut files: Vec<_> = std::fs::read_dir(&dir)
            .expect("sin migraciones")
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.extension().map(|e| e == "sql").unwrap_or(false))
            .collect();
        files.sort();

        for file in files {
            let sql = std::fs::read_to_string(&file).expect("migracion ilegible");
            pool.execute(sql.as_str())
                .await
                .unwrap_or_else(|e| panic!("fallo aplicando {file:?}: {e}"));
        }

        pool.close().await;
        true
    }

    /// Obtiene el pool o salta el test si no hay PostgreSQL configurado.
    macro_rules! pool_or_skip {
        () => {
            match shared_pool().await {
                Some(pool) => pool,
                None => {
                    eprintln!("omitido: sin PostgreSQL local configurado");
                    return;
                }
            }
        };
    }

    // --- Validacion de oportunidades ---

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
