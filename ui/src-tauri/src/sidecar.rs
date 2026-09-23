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

use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;

use crate::commands::engine::{sondear, sidecar_url, Sonda};
use crate::sidecar_log::{volcar, RotatingLog, LOG_FILE_NAME, MAX_BYTES, MAX_FILES};

const PYTHON_ENV_VAR: &str = "RIR_PYTHON";
const PROJECT_DIR_ENV_VAR: &str = "RIR_PROJECT_DIR";
const PORT_ENV_VAR: &str = "RIR_SIDECAR_PORT";

/// Loopback a proposito: el sidecar no debe ser alcanzable desde la red.
const SIDECAR_HOST: &str = "127.0.0.1";

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

/// Puerto del sidecar: `RIR_SIDECAR_PORT` o 8765 (D-C).
///
/// Es la UNICA fuente: con el se lanza el proceso (`--port`) y con el se
/// construye la URL a la que se le pregunta. Antes eran dos variables
/// (`RIR_SIDECAR_PORT` para lanzar y otra para consultar) y podian
/// discrepar: el sidecar arrancaba en un puerto y se le buscaba en otro.
pub fn sidecar_port() -> String {
    std::env::var(PORT_ENV_VAR).unwrap_or_else(|_| DEFAULT_PORT.to_string())
}

/// Variable por la que el hijo recibe el token (la lee el sidecar).
const TOKEN_ENV_VAR: &str = "RIR_SIDECAR_TOKEN";

/// Bytes aleatorios del token: 32, que en hexadecimal son 64 caracteres.
const TOKEN_BYTES: usize = 32;

/// Token nuevo: TOKEN_BYTES del generador del sistema, en hexadecimal.
fn generar_token() -> String {
    let mut bytes = [0u8; TOKEN_BYTES];
    // Sin aleatoriedad del sistema no hay forma segura de seguir: un token
    // predecible seria peor que no arrancar.
    getrandom::fill(&mut bytes).expect("el sistema no dio bytes aleatorios para el token");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Token del sidecar para toda la vida de este proceso (D-B).
///
/// Se genera al pedirlo por primera vez y no sale nunca de la memoria de
/// Rust salvo hacia el entorno del hijo: ni disco, ni log, ni WebView.
pub fn sidecar_token() -> &'static str {
    static TOKEN: OnceLock<String> = OnceLock::new();
    TOKEN.get_or_init(generar_token)
}

/// URL base del sidecar, derivada de `sidecar_port`.
pub fn sidecar_base_url() -> String {
    format!("http://{SIDECAR_HOST}:{}", sidecar_port())
}

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
    /// En el puerto contesta un sidecar que rechaza nuestro token: es de
    /// otro proceso. No se lanza otro encima ni se usa.
    PortInUse,
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

    /// Variables de entorno del proceso hijo.
    fn entorno() -> Vec<(&'static str, String)> {
        vec![(TOKEN_ENV_VAR, sidecar_token().to_string())]
    }

    /// Argumentos del proceso hijo.
    fn argumentos() -> Vec<String> {
        vec!["-m".into(), MODULE.into(), "--port".into(), sidecar_port()]
    }

    /// Log de la salida del hijo, o `None` si no se puede abrir (D-E).
    fn abrir_log(log_dir: Option<&Path>) -> Option<Arc<Mutex<RotatingLog>>> {
        let ruta = log_dir?.join(LOG_FILE_NAME);
        match RotatingLog::open(&ruta, MAX_BYTES, MAX_FILES) {
            Ok(log) => Some(Arc::new(Mutex::new(log))),
            Err(err) => {
                log::warn!("No se pudo abrir {}: {err}; la salida del sidecar se pierde", ruta.display());
                None
            }
        }
    }

    /// Lanza el proceso hijo.
    ///
    /// Su stdout y stderr van, filtrados, al log rotativo de `log_dir`
    /// (D-E): antes se descartaban y un sidecar que moria al arrancar no
    /// dejaba rastro de por que.
    fn spawn(&self, log_dir: Option<&Path>) -> std::io::Result<Child> {
        let python = std::env::var(PYTHON_ENV_VAR).unwrap_or_else(|_| DEFAULT_PYTHON.to_string());
        let log = Self::abrir_log(log_dir);
        let salida = || if log.is_some() { Stdio::piped() } else { Stdio::null() };

        let mut command = Command::new(python);
        command
            .args(Self::argumentos())
            .envs(Self::entorno())
            .stdout(salida())
            .stderr(salida())
            .stdin(Stdio::null());

        if let Some(dir) = Self::project_dir() {
            command.current_dir(dir);
        }

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = command.spawn()?;
        if let Some(log) = log {
            let secretos = vec![sidecar_token().to_string()];
            if let Some(stdout) = child.stdout.take() {
                volcar(stdout, log.clone(), secretos.clone());
            }
            if let Some(stderr) = child.stderr.take() {
                volcar(stderr, log, secretos);
            }
        }
        Ok(child)
    }

    /// Deja el sidecar listo para recibir comandos.
    ///
    /// Si ya responde, no hace nada. Si no, lo lanza y espera sondeando
    /// `/api/health` hasta que conteste o se agote la paciencia.
    pub async fn ensure_running(
        &self,
        client: &reqwest::Client,
        log_dir: Option<&Path>,
    ) -> SidecarStatus {
        match sondear(client).await {
            Sonda::Responde => {
                log::info!("Sidecar ya activo en {}", sidecar_url());
                return SidecarStatus::AlreadyRunning;
            }
            Sonda::Rechaza => {
                log::error!(
                    "En {} contesta un sidecar que rechaza el token: el puerto es de otro proceso",
                    sidecar_url()
                );
                return SidecarStatus::PortInUse;
            }
            Sonda::NoResponde => {}
        }

        log::info!("Arrancando el sidecar Python...");
        match self.spawn(log_dir) {
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

            if sondear(client).await == Sonda::Responde {
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
    use crate::commands::engine::sidecar_health;

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
    fn el_puerto_de_lanzamiento_y_el_de_consulta_salen_del_mismo_valor() {
        let _guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        std::env::set_var(PORT_ENV_VAR, TEST_PORT);
        let argumentos = SidecarManager::argumentos();
        let url = sidecar_url();
        std::env::remove_var(PORT_ENV_VAR);

        let puerto = argumentos
            .iter()
            .position(|a| a == "--port")
            .and_then(|i| argumentos.get(i + 1))
            .expect("el sidecar se lanza sin --port");
        assert_eq!(puerto, TEST_PORT);
        assert_eq!(url, format!("http://127.0.0.1:{TEST_PORT}"));
    }

    /// D-C: la URL del sidecar ya no se configura aparte; solo el puerto.
    #[test]
    fn nadie_lee_ya_la_variable_de_url_del_sidecar() {
        // Se construye en ejecucion para que este test no se encuentre a si mismo.
        let variable = ["RIR_SIDECAR", "URL"].join("_");
        let raiz = project_root_for_tests().expect("sin raiz del proyecto");
        let mut pendientes = vec![
            raiz.join("ui").join("src-tauri").join("src"),
            raiz.join("ui").join("src"),
            raiz.join("core"),
            raiz.join("scripts"),
        ];
        while let Some(dir) = pendientes.pop() {
            for entrada in std::fs::read_dir(&dir).unwrap().flatten() {
                let ruta = entrada.path();
                if ruta.is_dir() {
                    pendientes.push(ruta);
                } else if ["rs", "ts", "tsx", "py", "ps1"]
                    .iter()
                    .any(|ext| ruta.extension().is_some_and(|e| e == *ext))
                {
                    let texto = std::fs::read_to_string(&ruta).unwrap_or_default();
                    assert!(!texto.contains(&variable), "{} la usa", ruta.display());
                }
            }
        }
    }

    #[test]
    fn el_token_son_32_bytes_aleatorios_en_hex_y_no_se_repite() {
        let token = generar_token();
        assert_eq!(token.len(), 64);
        assert!(token.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(token, generar_token(), "dos generaciones no pueden coincidir");
    }

    #[test]
    fn el_token_del_proceso_es_siempre_el_mismo() {
        assert_eq!(sidecar_token(), sidecar_token());
        assert_eq!(sidecar_token().len(), 64);
    }

    #[test]
    fn el_hijo_recibe_el_token_del_proceso() {
        let entorno = SidecarManager::entorno();
        assert!(entorno.contains(&(TOKEN_ENV_VAR, sidecar_token().to_string())));
    }

    #[test]
    fn cada_peticion_lleva_el_token_como_bearer() {
        let peticion = crate::commands::engine::with_token_pub(
            reqwest::Client::new().get(sidecar_url()),
        )
        .build()
        .unwrap();
        let cabecera = peticion.headers()[reqwest::header::AUTHORIZATION]
            .to_str()
            .unwrap()
            .to_string();
        assert_eq!(cabecera, format!("Bearer {}", sidecar_token()));
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

        let client = reqwest::Client::new();
        let manager = SidecarManager::new();
        let logs = std::env::temp_dir().join(format!("rir_sidecar_logs_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&logs);

        let status = manager.ensure_running(&client, Some(&logs)).await;
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

        // Lo que escribio el hijo llego al archivo (D-E), sin el token.
        let registro = std::fs::read_to_string(logs.join(LOG_FILE_NAME)).unwrap_or_default();
        assert!(!registro.trim().is_empty(), "la salida del sidecar no llego al log");
        assert!(!registro.contains(sidecar_token()), "el token llego al log");
        let _ = std::fs::remove_dir_all(&logs);

        std::env::remove_var(PORT_ENV_VAR);
    }
}
