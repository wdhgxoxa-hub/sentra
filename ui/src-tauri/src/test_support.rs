//! Bases de PostgreSQL desechables para los tests.
//!
//! Cada test pide la suya por nombre: cargo los ejecuta en paralelo y dos
//! tests sobre la misma base se pisarían. La base se crea una vez por nombre
//! con las migraciones reales del repositorio; el pool se abre en cada test,
//! porque cada `#[tokio::test]` tiene su propio runtime.
//!
//! Solo se salta un test cuando no hay PostgreSQL (sin credenciales o sin
//! servidor que acepte la conexión), igual que `skipUnless` en Python. Si
//! hay servidor y la base no se puede preparar —una migración que falla, un
//! CREATE DATABASE rechazado— el test FALLA con el motivo: saltárselo
//! haría pasar por verde un test que no ha comprobado nada.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use sqlx::postgres::{PgConnectOptions, PgPoolOptions};
use sqlx::{Connection, Executor, PgConnection, PgPool};

/// Resultado de preparar cada base, por nombre.
static PREPARADAS: Mutex<Option<HashMap<&'static str, Preparacion>>> = Mutex::new(None);

/// Una sola preparación a la vez: CREATE DATABASE copia `template1` y
/// PostgreSQL lo rechaza si otra sesión lo está copiando a la vez.
static CONSTRUCCION: Mutex<()> = Mutex::new(());

#[derive(Clone, Debug)]
enum Preparacion {
    Lista,
    SinPostgres(String),
    Fallida(String),
}

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

async fn abrir(base: &str) -> Result<PgPool, String> {
    let opts = opciones(base).ok_or("sin credenciales de PostgreSQL")?;
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
        .connect_with(opts)
        .await
        .map_err(|e| format!("no se pudo abrir {base}: {e}"))
}

/// Crea la base y le aplica las migraciones de `migraciones`.
async fn construir(base: &str, migraciones: &Path) -> Preparacion {
    let Some(admin_opts) = opciones("postgres") else {
        return Preparacion::SinPostgres("sin credenciales configuradas".into());
    };
    let mut admin = match PgConnection::connect_with(&admin_opts).await {
        Ok(conexion) => conexion,
        Err(e) => return Preparacion::SinPostgres(e.to_string()),
    };
    match preparar(&mut admin, base, migraciones).await {
        Ok(()) => Preparacion::Lista,
        Err(motivo) => Preparacion::Fallida(motivo),
    }
}

async fn preparar(admin: &mut PgConnection, base: &str, dir: &Path) -> Result<(), String> {
    let borrar = format!(r#"DROP DATABASE IF EXISTS "{base}" WITH (FORCE)"#);
    let crear = format!(r#"CREATE DATABASE "{base}""#);
    admin
        .execute(borrar.as_str())
        .await
        .map_err(|e| format!("DROP DATABASE: {e}"))?;
    admin
        .execute(crear.as_str())
        .await
        .map_err(|e| format!("CREATE DATABASE: {e}"))?;

    let pool = abrir(base).await?;
    let mut archivos: Vec<_> = std::fs::read_dir(dir)
        .map_err(|e| format!("{}: {e}", dir.display()))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|e| e == "sql"))
        .collect();
    archivos.sort();

    for archivo in archivos {
        let nombre = archivo.file_name().unwrap_or_default().to_string_lossy().into_owned();
        let sql = std::fs::read_to_string(&archivo).map_err(|e| format!("{nombre}: {e}"))?;
        pool.execute(sql.as_str())
            .await
            .map_err(|e| format!("migración {nombre}: {e}"))?;
    }
    pool.close().await;
    Ok(())
}

/// Carpeta temporal de un test, que se borra al salir de ámbito (R-E).
///
/// También si el test falla: `Drop` se ejecuta al deshacer la pila del
/// pánico. Antes cada pasada de `cargo test` dejaba siete carpetas `rir_*`
/// en el directorio temporal del sistema.
pub struct DirTemporal(PathBuf);

impl DirTemporal {
    pub fn nuevo(nombre: &str) -> Self {
        let dir = std::env::temp_dir().join(format!("rir_{nombre}_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("no se pudo crear la carpeta temporal");
        Self(dir)
    }
}

impl std::ops::Deref for DirTemporal {
    type Target = Path;

    fn deref(&self) -> &Path {
        &self.0
    }
}

impl Drop for DirTemporal {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// Pool sobre una base de pruebas lista, o `None` si no hay PostgreSQL.
///
/// Si hay PostgreSQL y la base no se pudo preparar, entra en pánico con el
/// motivo (ver el comentario del módulo).
///
/// La base se prepara en un hilo con su propio runtime: crear un runtime
/// dentro del del test está prohibido por tokio.
pub async fn base_de_pruebas(base: &'static str) -> Option<PgPool> {
    let preparacion = {
        let _turno = CONSTRUCCION.lock().unwrap_or_else(|e| e.into_inner());
        let ya = PREPARADAS
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .as_ref()
            .and_then(|m| m.get(base).cloned());
        match ya {
            Some(valor) => valor,
            None => {
                let valor = std::thread::spawn(move || {
                    let Some(raiz) = crate::sidecar::project_root_for_tests() else {
                        return Preparacion::Fallida("sin raíz del proyecto".into());
                    };
                    let migraciones = raiz.join("sql").join("migrations");
                    tokio::runtime::Runtime::new()
                        .map(|rt| rt.block_on(construir(base, &migraciones)))
                        .unwrap_or_else(|e| Preparacion::Fallida(format!("runtime: {e}")))
                })
                .join()
                .unwrap_or_else(|_| Preparacion::Fallida("la preparación entró en pánico".into()));
                PREPARADAS
                    .lock()
                    .unwrap_or_else(|e| e.into_inner())
                    .get_or_insert_with(HashMap::new)
                    .insert(base, valor.clone());
                valor
            }
        }
    };
    match preparacion {
        Preparacion::SinPostgres(motivo) => {
            eprintln!("omitido: PostgreSQL no disponible ({motivo})");
            None
        }
        Preparacion::Fallida(motivo) => panic!("base de pruebas {base}: {motivo}"),
        Preparacion::Lista => Some(
            abrir(base)
                .await
                .unwrap_or_else(|motivo| panic!("base de pruebas {base}: {motivo}")),
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn la_carpeta_temporal_se_borra_al_soltarla_aunque_el_test_falle() {
        let normal = DirTemporal::nuevo("higiene_normal");
        std::fs::write(normal.join("x.txt"), b"x").unwrap();
        let ruta_normal = normal.to_path_buf();
        drop(normal);
        assert!(!ruta_normal.exists());

        let ruta_panico = std::env::temp_dir()
            .join(format!("rir_higiene_panico_{}", std::process::id()));
        let resultado = std::panic::catch_unwind(|| {
            let _dir = DirTemporal::nuevo("higiene_panico");
            panic!("el test falla con la carpeta creada");
        });
        assert!(resultado.is_err());
        assert!(!ruta_panico.exists(), "la carpeta sobrevivió al pánico");
    }

    /// Con PostgreSQL, una base que no se puede preparar es un fallo con su
    /// motivo, nunca "sin PostgreSQL": así un test roto no pasa por saltado.
    #[tokio::test]
    async fn una_migracion_rota_es_un_fallo_y_no_un_salto() {
        let hay_postgres = match opciones("postgres") {
            Some(opts) => PgConnection::connect_with(&opts).await.is_ok(),
            None => false,
        };
        if !hay_postgres {
            eprintln!("omitido: PostgreSQL no disponible");
            return;
        }

        let dir = std::env::temp_dir().join(format!("rir_migracion_rota_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("001_rota.sql"), "SELECT * FROM tabla_que_no_existe;").unwrap();

        let resultado = construir("rir_migracion_rota_test", &dir).await;
        let _ = std::fs::remove_dir_all(&dir);

        match resultado {
            Preparacion::Fallida(motivo) => {
                assert!(motivo.contains("001_rota.sql"), "el motivo no dice qué falló: {motivo}");
            }
            otro => panic!("con PostgreSQL, una migración rota debe ser Fallida; fue {otro:?}"),
        }
    }
}
