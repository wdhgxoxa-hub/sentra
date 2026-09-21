//! Ciclo de vida del sidecar Python.
//!
//! La aplicacion no sirve de nada sin el motor, asi que se encarga ella de
//! tenerlo en pie: al arrancar comprueba si ya responde y, si no, lo lanza;
//! al cerrarse, lo recoge.
//!
//! Una regla importa por encima del resto: **solo se mata lo que se arranco**.
//! Si al abrir la ventana ya habia un sidecar escuchando, es de otro (una
//! consola de desarrollo, otra instancia) y cerrar esta aplicacion no debe
//! llevarselo por delante.

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use crate::commands::engine::{sidecar_health, sidecar_url};

const PYTHON_ENV_VAR: &str = "RIR_PYTHON";
const PROJECT_DIR_ENV_VAR: &str = "RIR_PROJECT_DIR";
const PORT_ENV_VAR: &str = "RIR_SIDECAR_PORT";

const DEFAULT_PYTHON: &str = "python";
const DEFAULT_PORT: &str = "8765";
const MODULE: &str = "core.orchestration.sidecar_server";

/// Cuanto se espera a que el sidecar quede listo. La primera arrancada carga
/// el modelo de embeddings, que no es instantaneo.
const READY_ATTEMPTS: u32 = 60;
const READY_INTERVAL: Duration = Duration::from_millis(500);

/// En Windows, un proceso hijo lanzado desde una app con ventana abre una
/// consola negra si no se le dice lo contrario.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub enum SidecarStatus {
    /// Ya estaba escuchando: no es nuestro y no se tocara al salir.
    AlreadyRunning,
    /// Lo arrancamos nosotros y respondio a tiempo.
    Started,
    /// Lo arrancamos pero no llego a responder.
    Unresponsive,
    /// Ni siquiera se pudo lanzar el proceso.
    FailedToSpawn,
}

pub struct SidecarManager {
    /// Solo contiene algo si el proceso lo lanzamos nosotros.
    child: Mutex<Option<Child>>,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
        }
    }

    /// Directorio desde el que se ejecuta el modulo de Python.
    ///
    /// Tiene que ser la raiz del proyecto para que `core` sea importable.
    /// Se busca hacia arriba desde el ejecutable porque en desarrollo este
    /// vive en `ui/src-tauri/target/debug`.
    fn project_dir() -> Option<std::path::PathBuf> {
        if let Ok(dir) = std::env::var(PROJECT_DIR_ENV_VAR) {
            return Some(std::path::PathBuf::from(dir));
        }

        let start = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .or_else(|| std::env::current_dir().ok())?;

        let mut candidate = start.as_path();
        loop {
            if candidate.join("core").join("orchestration").is_dir() {
                return Some(candidate.to_path_buf());
            }
            candidate = candidate.parent()?;
        }
    }

    fn port() -> String {
        std::env::var(PORT_ENV_VAR).unwrap_or_else(|_| DEFAULT_PORT.to_string())
    }

    /// Lanza el proceso hijo.
    fn spawn(&self) -> std::io::Result<Child> {
        let python = std::env::var(PYTHON_ENV_VAR).unwrap_or_else(|_| DEFAULT_PYTHON.to_string());

        let mut command = Command::new(python);
        command
            .arg("-m")
            .arg(MODULE)
            .arg("--port")
            .arg(Self::port())
            // La salida del sidecar no interesa aqui: el tiene su propio log
            // y heredarla mantendria vivos los descriptores al cerrar.
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .stdin(Stdio::null());

        if let Some(dir) = Self::project_dir() {
            command.current_dir(dir);
        }

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(CREATE_NO_WINDOW);
        }

        command.spawn()
    }

    /// Deja el sidecar listo para recibir comandos.
    ///
    /// Si ya responde, no hace nada. Si no, lo lanza y espera sondeando
    /// `/api/health` hasta que conteste o se agote la paciencia.
    pub async fn ensure_running(&self, client: &reqwest::Client) -> SidecarStatus {
        if sidecar_health(client).await.is_some() {
            log::info!("Sidecar ya activo en {}", sidecar_url());
            return SidecarStatus::AlreadyRunning;
        }

        log::info!("Arrancando el sidecar Python...");
        match self.spawn() {
            Ok(child) => {
                *self.child.lock().unwrap() = Some(child);
            }
            Err(err) => {
                log::error!("No se pudo lanzar el sidecar: {err}");
                return SidecarStatus::FailedToSpawn;
            }
        }

        for intento in 1..=READY_ATTEMPTS {
            tokio::time::sleep(READY_INTERVAL).await;

            // Si el proceso murio por su cuenta, no tiene sentido seguir
            // esperando a que conteste.
            if let Ok(mut guard) = self.child.lock() {
                if let Some(child) = guard.as_mut() {
                    if let Ok(Some(status)) = child.try_wait() {
                        log::error!("El sidecar termino con {status}");
                        *guard = None;
                        return SidecarStatus::Unresponsive;
                    }
                }
            }

            if sidecar_health(client).await.is_some() {
                log::info!("Sidecar listo tras {} intentos", intento);
                return SidecarStatus::Started;
            }
        }

        log::error!("El sidecar no respondio a tiempo");
        SidecarStatus::Unresponsive
    }

    /// Detiene el proceso hijo, si lo lanzamos nosotros.
    pub fn shutdown(&self) {
        let Ok(mut guard) = self.child.lock() else {
            return;
        };

        if let Some(mut child) = guard.take() {
            log::info!("Deteniendo el sidecar Python");
            let _ = child.kill();
            // `wait` evita dejar un proceso zombi detras.
            let _ = child.wait();
        }
    }
}

/// Raiz del proyecto, para los tests de otros modulos.
#[cfg(test)]
pub fn project_root_for_tests() -> Option<std::path::PathBuf> {
    SidecarManager::project_dir()
}

impl Default for SidecarManager {
    fn default() -> Self {
        Self::new()
    }
}

/// Recoge el proceso tambien si la aplicacion termina de forma abrupta.
impl Drop for SidecarManager {
    fn drop(&mut self) {
        self.shutdown();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Puerto propio, para no chocar con un sidecar de desarrollo.
    const TEST_PORT: &str = "8799";

    /// Las variables de entorno son globales al proceso y cargo ejecuta los
    /// tests en paralelo: sin este cerrojo, el test que finge un directorio
    /// inexistente hace que el que arranca el sidecar de verdad lo lance
    /// desde ahi y muera al instante.
    static ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn project_dir_finds_the_python_package() {
        let _guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        // Sin esto, el proceso hijo arrancaria en un directorio donde
        // `core` no es importable y moriria al instante.
        let dir = SidecarManager::project_dir().expect("no se encontro la raiz");
        assert!(dir.join("core").join("orchestration").is_dir());
    }

    #[test]
    fn project_dir_honours_the_environment_variable() {
        let _guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        std::env::set_var(PROJECT_DIR_ENV_VAR, "C:/ruta/indicada");
        let dir = SidecarManager::project_dir().unwrap();
        std::env::remove_var(PROJECT_DIR_ENV_VAR);
        assert_eq!(dir, std::path::PathBuf::from("C:/ruta/indicada"));
    }

    #[test]
    fn shutdown_without_a_child_is_harmless() {
        SidecarManager::new().shutdown();
    }

    /// Arranca un sidecar de verdad, espera a que responda y lo mata.
    ///
    /// Necesita Python y las dependencias del proyecto instaladas.
    #[tokio::test]
    async fn spawns_waits_and_stops_a_real_sidecar() {
        let _guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        std::env::set_var(PORT_ENV_VAR, TEST_PORT);
        std::env::set_var("RIR_SIDECAR_URL", format!("http://127.0.0.1:{TEST_PORT}"));

        let client = reqwest::Client::new();
        let manager = SidecarManager::new();

        let status = manager.ensure_running(&client).await;
        assert_eq!(
            status,
            SidecarStatus::Started,
            "el sidecar deberia arrancar y responder"
        );

        // Responde de verdad, no solo "el proceso existe".
        let health = sidecar_health(&client).await;
        assert!(health.is_some(), "no contesto a /api/health");

        manager.shutdown();
        tokio::time::sleep(Duration::from_millis(1500)).await;

        assert!(
            sidecar_health(&client).await.is_none(),
            "el sidecar sigue vivo despues de shutdown"
        );

        std::env::remove_var(PORT_ENV_VAR);
        std::env::remove_var("RIR_SIDECAR_URL");
    }
}
