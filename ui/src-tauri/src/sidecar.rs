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

use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex, OnceLock, PoisonError};
use std::time::Duration;

use crate::commands::engine::{sondear_en, Sonda};
use crate::sidecar_log::{volcar, RotatingLog, LOG_FILE_NAME, MAX_BYTES, MAX_FILES};

const PYTHON_ENV_VAR: &str = "RIR_PYTHON";
const PROJECT_DIR_ENV_VAR: &str = "RIR_PROJECT_DIR";
const PORT_ENV_VAR: &str = "RIR_SIDECAR_PORT";

/// Loopback a proposito: el sidecar no debe ser alcanzable desde la red.
const SIDECAR_HOST: &str = "127.0.0.1";

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

/// Codigos estables de por que no hay sidecar; los traduce la interfaz.
pub const CODIGO_SIN_PYTHON: &str = "python_not_found";
pub const CODIGO_NO_LANZA: &str = "sidecar_spawn_failed";
pub const CODIGO_PUERTO_AJENO: &str = "sidecar_port_in_use";
pub const CODIGO_NO_RESPONDE: &str = "sidecar_unresponsive";

/// Todos los anteriores, para exigir su traduccion.
pub const CODIGOS_DE_ARRANQUE: &[&str] = &[
    CODIGO_SIN_PYTHON,
    CODIGO_NO_LANZA,
    CODIGO_PUERTO_AJENO,
    CODIGO_NO_RESPONDE,
];

/// Interprete de la `.venv` del proyecto, donde lo deja `scripts/setup_env.ps1`.
fn interprete_del_venv(proyecto: &Path) -> PathBuf {
    let venv = proyecto.join(".venv");
    if cfg!(windows) {
        venv.join("Scripts").join("python.exe")
    } else {
        venv.join("bin").join("python")
    }
}

/// Que Python ejecuta el sidecar (D-D).
///
/// `RIR_PYTHON` si esta definida; si no, la `.venv` del proyecto; si no, un
/// error que dice como arreglarlo. Nunca el `python` global del PATH: con el
/// el sidecar arrancaba con otras versiones de las dependencias, o sin
/// ellas, y fallaba de formas que no apuntaban a la causa.
fn resolver_interprete(explicito: Option<String>, proyecto: Option<&Path>) -> Result<PathBuf, String> {
    if let Some(ruta) = explicito.filter(|r| !r.trim().is_empty()) {
        return Ok(PathBuf::from(ruta));
    }
    let Some(proyecto) = proyecto else {
        return Err(
            "No se encontro la raiz del proyecto. Define RIR_PROJECT_DIR, o RIR_PYTHON, \
             o crea el entorno con scripts/setup_env.ps1."
                .into(),
        );
    };
    let venv = interprete_del_venv(proyecto);
    if venv.is_file() {
        Ok(venv)
    } else {
        Err(format!(
            "No existe {}. Crealo con scripts/setup_env.ps1 o define RIR_PYTHON.",
            venv.display()
        ))
    }
}

/// Por que no hay sidecar, para la interfaz.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct LaunchFailure {
    pub code: String,
    pub detail: String,
}

/// URL base del sidecar, derivada de `sidecar_port`.
pub fn sidecar_base_url() -> String {
    format!("http://{SIDECAR_HOST}:{}", sidecar_port())
}

/// Con qué y dónde se lanza el sidecar.
///
/// En producción sale del entorno (`from_env`). Los tests la construyen a
/// mano: cambiar variables de entorno en un test las cambia para todos los
/// que corren a la vez en el mismo proceso.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SidecarConfig {
    /// `RIR_PYTHON`: intérprete explícito (D-D).
    pub python: Option<String>,
    /// Raíz del proyecto, desde la que se ejecuta el módulo.
    pub project_dir: Option<PathBuf>,
    /// Puerto con el que se lanza y en el que se le pregunta (D-C).
    pub port: String,
}

impl SidecarConfig {
    pub fn from_env() -> Self {
        Self {
            python: std::env::var(PYTHON_ENV_VAR).ok(),
            project_dir: resolver_proyecto(std::env::var(PROJECT_DIR_ENV_VAR).ok()),
            port: sidecar_port(),
        }
    }

    fn base_url(&self) -> String {
        format!("http://{SIDECAR_HOST}:{}", self.port)
    }
}

/// Raíz del proyecto: la indicada (`RIR_PROJECT_DIR`) o, si no, la primera
/// carpeta hacia arriba desde el ejecutable que contenga el paquete Python.
///
/// Tiene que ser la raíz para que `core` sea importable. Se busca hacia
/// arriba porque en desarrollo el ejecutable vive en `ui/src-tauri/target/debug`.
fn resolver_proyecto(indicado: Option<String>) -> Option<PathBuf> {
    if let Some(dir) = indicado {
        return Some(PathBuf::from(dir));
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

/// Canal por el que el estado del arranque del motor llega a la interfaz.
pub const SIDECAR_EVENT_CHANNEL: &str = "radar:sidecar";

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
    /// No hay interprete de Python.
    NoInterpreter,
    /// En el puerto contesta un sidecar que rechaza nuestro token: es de
    /// otro proceso. No se lanza otro encima ni se usa.
    PortInUse,
}

pub struct SidecarManager {
    config: SidecarConfig,
    /// Solo contiene algo si el proceso lo lanzamos nosotros.
    child: Mutex<Option<Child>>,
    /// Por que fallo el ultimo arranque; `None` si fue bien o no se intento.
    fallo: Mutex<Option<LaunchFailure>>,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self::with_config(SidecarConfig::from_env())
    }

    pub fn with_config(config: SidecarConfig) -> Self {
        Self {
            config,
            child: Mutex::new(None),
            fallo: Mutex::new(None),
        }
    }

    /// Variables de entorno del proceso hijo.
    fn entorno() -> Vec<(&'static str, String)> {
        vec![(TOKEN_ENV_VAR, sidecar_token().to_string())]
    }

    /// Argumentos del proceso hijo.
    fn argumentos(&self) -> Vec<String> {
        vec!["-m".into(), MODULE.into(), "--port".into(), self.config.port.clone()]
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
    fn spawn(&self, python: &Path, log_dir: Option<&Path>) -> std::io::Result<Child> {
        let log = Self::abrir_log(log_dir);
        let salida = || if log.is_some() { Stdio::piped() } else { Stdio::null() };

        let mut command = Command::new(python);
        command
            .args(self.argumentos())
            .envs(Self::entorno())
            .stdout(salida())
            .stderr(salida())
            .stdin(Stdio::null());

        if let Some(dir) = &self.config.project_dir {
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
        let (status, fallo) = self.arrancar(client, log_dir).await;
        *self.fallo.lock().unwrap_or_else(PoisonError::into_inner) = fallo;
        status
    }

    async fn arrancar(
        &self,
        client: &reqwest::Client,
        log_dir: Option<&Path>,
    ) -> (SidecarStatus, Option<LaunchFailure>) {
        let fallo = |code: &str, detail: String| {
            Some(LaunchFailure {
                code: code.into(),
                detail,
            })
        };

        let url = self.config.base_url();
        match sondear_en(client, &url).await {
            Sonda::Responde => {
                log::info!("Sidecar ya activo en {url}");
                return (SidecarStatus::AlreadyRunning, None);
            }
            Sonda::Rechaza => {
                let detalle = format!(
                    "En {url} contesta otro proceso (rechaza el token o no es el motor de SENTRA)"
                );
                log::error!("{detalle}");
                return (SidecarStatus::PortInUse, fallo(CODIGO_PUERTO_AJENO, detalle));
            }
            Sonda::NoResponde => {}
        }

        let python = match resolver_interprete(
            self.config.python.clone(),
            self.config.project_dir.as_deref(),
        ) {
            Ok(python) => python,
            Err(detalle) => {
                log::error!("{detalle}");
                return (SidecarStatus::NoInterpreter, fallo(CODIGO_SIN_PYTHON, detalle));
            }
        };

        // Un hijo lanzado antes que ya no responde se detiene antes de lanzar
        // otro: reintentar (AUD-056) no puede dejar dos motores.
        self.shutdown();
        log::info!("Arrancando el sidecar Python con {}", python.display());
        match self.spawn(&python, log_dir) {
            Ok(child) => {
                *self.child.lock().unwrap_or_else(PoisonError::into_inner) = Some(child);
            }
            Err(err) => {
                let detalle = format!("{}: {err}", python.display());
                log::error!("No se pudo lanzar el sidecar: {detalle}");
                return (SidecarStatus::FailedToSpawn, fallo(CODIGO_NO_LANZA, detalle));
            }
        }

        for intento in 1..=READY_ATTEMPTS {
            tokio::time::sleep(READY_INTERVAL).await;

            // Si el proceso murio por su cuenta, no tiene sentido seguir
            // esperando a que conteste.
            if let Ok(mut guard) = self.child.lock() {
                if let Some(child) = guard.as_mut() {
                    if let Ok(Some(status)) = child.try_wait() {
                        let detalle = format!("El sidecar termino con {status}; ver sidecar.log");
                        log::error!("{detalle}");
                        *guard = None;
                        return (SidecarStatus::Unresponsive, fallo(CODIGO_NO_RESPONDE, detalle));
                    }
                }
            }

            if sondear_en(client, &url).await == Sonda::Responde {
                log::info!("Sidecar listo tras {} intentos", intento);
                return (SidecarStatus::Started, None);
            }
        }

        let detalle = "El sidecar no respondio a tiempo; ver sidecar.log".to_string();
        log::error!("{detalle}");
        (SidecarStatus::Unresponsive, fallo(CODIGO_NO_RESPONDE, detalle))
    }

    /// Por que fallo el ultimo arranque, si fallo.
    pub fn ultimo_fallo(&self) -> Option<LaunchFailure> {
        self.fallo.lock().unwrap_or_else(PoisonError::into_inner).clone()
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
pub fn project_root_for_tests() -> Option<PathBuf> {
    resolver_proyecto(std::env::var(PROJECT_DIR_ENV_VAR).ok())
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
    use crate::commands::engine::sidecar_health_en;
    use crate::test_support::DirTemporal;

    // Los tests NO tocan variables de entorno: son globales al proceso y
    // cargo ejecuta los tests en paralelo, así que cambiarlas en uno las
    // cambia para todos (antes, los tests de otros módulos leían a veces la
    // raíz de un proyecto temporal y se saltaban). Cada test construye su
    // SidecarConfig, y cada uno que sondea un puerto usa el suyo.

    /// Puerto del test que arranca un sidecar de verdad.
    const TEST_PORT: &str = "8799";
    /// Puerto donde no escucha nadie, para el test sin intérprete.
    const PUERTO_SIN_SIDECAR: &str = "8798";

    fn config(python: Option<String>, project_dir: Option<PathBuf>, port: &str) -> SidecarConfig {
        SidecarConfig {
            python,
            project_dir,
            port: port.into(),
        }
    }

    #[test]
    fn project_dir_finds_the_python_package() {
        // Sin esto, el proceso hijo arrancaria en un directorio donde
        // `core` no es importable y moriria al instante.
        let dir = resolver_proyecto(None).expect("no se encontro la raiz");
        assert!(dir.join("core").join("orchestration").is_dir());
    }

    #[test]
    fn project_dir_honours_the_environment_variable() {
        let dir = resolver_proyecto(Some("C:/ruta/indicada".into())).unwrap();
        assert_eq!(dir, std::path::PathBuf::from("C:/ruta/indicada"));
    }

    #[test]
    fn el_puerto_de_lanzamiento_y_el_de_consulta_salen_del_mismo_valor() {
        let manager = SidecarManager::with_config(config(None, None, TEST_PORT));
        let argumentos = manager.argumentos();
        let puerto = argumentos
            .iter()
            .position(|a| a == "--port")
            .and_then(|i| argumentos.get(i + 1))
            .expect("el sidecar se lanza sin --port");
        assert_eq!(puerto, TEST_PORT);
        assert_eq!(manager.config.base_url(), format!("http://127.0.0.1:{TEST_PORT}"));

        // En producción, el gestor y los comandos leen el mismo puerto (D-C).
        assert_eq!(SidecarConfig::from_env().base_url(), sidecar_base_url());
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
            reqwest::Client::new().get(sidecar_base_url()),
        )
        .build()
        .unwrap();
        let cabecera = peticion.headers()[reqwest::header::AUTHORIZATION]
            .to_str()
            .unwrap()
            .to_string();
        assert_eq!(cabecera, format!("Bearer {}", sidecar_token()));
    }

    fn proyecto_temporal(nombre: &str, con_venv: bool) -> DirTemporal {
        let dir = DirTemporal::nuevo(nombre);
        if con_venv {
            let python = interprete_del_venv(&dir);
            std::fs::create_dir_all(python.parent().unwrap()).unwrap();
            std::fs::write(&python, b"").unwrap();
        }
        dir
    }

    #[test]
    fn rir_python_manda_sobre_todo() {
        let dir = proyecto_temporal("py_explicito", true);
        let elegido = resolver_interprete(Some("C:/otro/python.exe".into()), Some(&*dir));
        assert_eq!(elegido, Ok(std::path::PathBuf::from("C:/otro/python.exe")));
    }

    #[test]
    fn sin_rir_python_se_usa_el_venv_del_proyecto() {
        let dir = proyecto_temporal("py_venv", true);
        assert_eq!(resolver_interprete(None, Some(&*dir)), Ok(interprete_del_venv(&dir)));
    }

    #[test]
    fn sin_venv_ni_rir_python_es_un_error_y_nunca_el_python_global() {
        let dir = proyecto_temporal("py_nada", false);
        for explicito in [None, Some(String::new()), Some("  ".into())] {
            let resultado = resolver_interprete(explicito, Some(&*dir));
            let detalle = resultado.expect_err("sin intérprete no puede haber ruta");
            assert!(detalle.contains("setup_env.ps1"), "el detalle no dice cómo arreglarlo");
        }
        assert!(resolver_interprete(None, None).is_err());
    }

    #[tokio::test]
    async fn sin_interprete_no_se_lanza_nada_y_queda_el_fallo_con_codigo() {
        let dir = proyecto_temporal("py_arranque", false);
        let manager =
            SidecarManager::with_config(config(None, Some(dir.to_path_buf()), PUERTO_SIN_SIDECAR));
        let status = manager.ensure_running(&reqwest::Client::new(), None).await;

        assert_eq!(status, SidecarStatus::NoInterpreter);
        assert!(manager.child.lock().unwrap().is_none(), "no debe haber proceso hijo");
        let fallo = manager.ultimo_fallo().expect("sin fallo registrado");
        assert_eq!(fallo.code, CODIGO_SIN_PYTHON);
    }

    #[test]
    fn cada_codigo_de_arranque_tiene_texto_en_es_y_en() {
        for diccionario in [
            include_str!("../../src/i18n/es.ts"),
            include_str!("../../src/i18n/en.ts"),
        ] {
            let inicio = diccionario.find("\n  errors: {").expect("sin bloque errors");
            let bloque = &diccionario[inicio..];
            let bloque = &bloque[..bloque.find("\n  },").unwrap()];
            for codigo in CODIGOS_DE_ARRANQUE {
                assert!(bloque.contains(&format!("\n    {codigo}:")), "falta {codigo}");
            }
        }
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
        // El test elige su interprete de forma explicita (D-D): el de la
        // .venv del proyecto si existe; si no, el `python` del PATH, pero
        // declarado como interprete explicito, no como valor por defecto.
        let raiz = project_root_for_tests();
        let python = raiz
            .as_deref()
            .map(interprete_del_venv)
            .filter(|p| p.is_file())
            .map(|p| p.display().to_string())
            .unwrap_or_else(|| "python".into());

        let client = reqwest::Client::new();
        let manager = SidecarManager::with_config(config(Some(python), raiz, TEST_PORT));
        let url = manager.config.base_url();
        let logs = DirTemporal::nuevo("sidecar_logs");

        let status = manager.ensure_running(&client, Some(&logs)).await;
        assert_eq!(
            status,
            SidecarStatus::Started,
            "el sidecar deberia arrancar y responder"
        );

        // Responde de verdad, no solo "el proceso existe".
        let health = sidecar_health_en(&client, &url).await;
        assert!(health.is_some(), "no contesto a /api/health");

        manager.shutdown();
        tokio::time::sleep(Duration::from_millis(1500)).await;

        assert!(
            sidecar_health_en(&client, &url).await.is_none(),
            "el sidecar sigue vivo despues de shutdown"
        );

        // Lo que escribio el hijo llego al archivo (D-E), sin el token.
        let registro = std::fs::read_to_string(logs.join(LOG_FILE_NAME)).unwrap_or_default();
        assert!(!registro.trim().is_empty(), "la salida del sidecar no llego al log");
        assert!(!registro.contains(sidecar_token()), "el token llego al log");
    }
}
