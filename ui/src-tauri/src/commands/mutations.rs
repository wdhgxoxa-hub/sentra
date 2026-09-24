//! Comandos de escritura: cancelar un escaneo multifuente en curso.
//!
//! La validacion de oportunidades y el alta de subreddits se retiraron con
//! la pipeline antigua (C2, D-C2): sus tablas se conservan sin escrituras.

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::commands::engine::{sidecar_url, with_token_pub};
use crate::db::{AppState, RadarResult};

/// Tenant de la instalacion local (ver migracion 001).
const LOCAL_TENANT: &str = "00000000-0000-0000-0000-000000000001";

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
