//! Bases de PostgreSQL desechables para los tests.
//!
//! Cada test pide la suya por nombre: cargo los ejecuta en paralelo y dos
//! tests sobre la misma base se pisarían. La base se crea una vez por nombre
//! con las migraciones reales del repositorio; el pool se abre en cada test,
//! porque cada `#[tokio::test]` tiene su propio runtime.

use std::collections::HashMap;
use std::sync::Mutex;

use sqlx::postgres::{PgConnectOptions, PgPoolOptions};
use sqlx::{Connection, Executor, PgConnection, PgPool};

/// Bases ya preparadas, por nombre.
static PREPARADAS: Mutex<Option<HashMap<&'static str, bool>>> = Mutex::new(None);

/// Credenciales: `RIR_PG_TEST_URL` o el `pgpass.conf` del usuario, igual que
/// la aplicación (ver db.rs).
fn opciones(base: &str) -> Option<PgConnectOptions> {
    if let Ok(url) = std::env::var("RIR_PG_TEST_URL") {
        return url
            .parse::<PgConnectOptions>()
            .ok()
            .map(|o| o.database(base));
    }
    crate::db::options_from_pgpass(base)
}

async fn abrir(base: &str) -> Option<PgPool> {
    PgPoolOptions::new()
        .max_connections(2)
        .after_connect(|conn, _| {
            Box::pin(async move {
                sqlx::query("SET search_path = radar, public")
                    .execute(conn)
                    .await?;
                Ok(())
            })
        })
        .connect_with(opciones(base)?)
        .await
        .ok()
}

/// Crea la base y le aplica las migraciones de `sql/migrations`.
async fn construir(base: &str) -> bool {
    let Some(admin_opts) = opciones("postgres") else {
        return false;
    };
    let Ok(mut admin) = PgConnection::connect_with(&admin_opts).await else {
        return false;
    };
    let borrar = format!(r#"DROP DATABASE IF EXISTS "{base}" WITH (FORCE)"#);
    let crear = format!(r#"CREATE DATABASE "{base}""#);
    if admin.execute(borrar.as_str()).await.is_err() || admin.execute(crear.as_str()).await.is_err()
    {
        return false;
    }

    let (Some(pool), Some(raiz)) = (abrir(base).await, crate::sidecar::project_root_for_tests())
    else {
        return false;
    };
    let Ok(entradas) = std::fs::read_dir(raiz.join("sql").join("migrations")) else {
        return false;
    };
    let mut archivos: Vec<_> = entradas
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|e| e == "sql"))
        .collect();
    archivos.sort();

    for archivo in archivos {
        let Ok(sql) = std::fs::read_to_string(&archivo) else {
            return false;
        };
        if pool.execute(sql.as_str()).await.is_err() {
            return false;
        }
    }
    pool.close().await;
    true
}

/// Pool sobre una base de pruebas lista, o `None` si no hay PostgreSQL.
///
/// La base se prepara en un hilo con su propio runtime: crear un runtime
/// dentro del del test está prohibido por tokio.
pub async fn base_de_pruebas(base: &'static str) -> Option<PgPool> {
    let ya = PREPARADAS
        .lock()
        .ok()
        .and_then(|g| g.as_ref().and_then(|m| m.get(base).copied()));
    let lista = match ya {
        Some(valor) => valor,
        None => {
            let valor = std::thread::spawn(move || {
                tokio::runtime::Runtime::new()
                    .map(|rt| rt.block_on(construir(base)))
                    .unwrap_or(false)
            })
            .join()
            .unwrap_or(false);
            if let Ok(mut guardia) = PREPARADAS.lock() {
                guardia.get_or_insert_with(HashMap::new).insert(base, valor);
            }
            valor
        }
    };
    if lista {
        abrir(base).await
    } else {
        None
    }
}
