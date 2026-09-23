//! Registro de la salida del sidecar (AUD-030, decision D-E).
//!
//! Antes la salida del proceso hijo iba a `Stdio::null()`: si el sidecar
//! moria al arrancar (una dependencia que falta, un puerto ocupado), no
//! quedaba rastro de por que. Ahora stdout y stderr van a un archivo en el
//! directorio de logs de la aplicacion, que rota a los MAX_BYTES y conserva
//! MAX_FILES archivos, y cada linea pasa antes por `redact`: el sidecar
//! maneja claves de Gemini, credenciales de Reddit y el propio token.

use std::fs::{File, OpenOptions};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, PoisonError};
use std::thread::JoinHandle;

/// Tamaño maximo de cada archivo antes de rotar.
pub const MAX_BYTES: u64 = 5 * 1024 * 1024;

/// Archivos que se conservan: el actual y cuatro anteriores.
pub const MAX_FILES: usize = 5;

/// Nombre del archivo, dentro del directorio de logs de la aplicacion.
pub const LOG_FILE_NAME: &str = "sidecar.log";

/// Lo que sustituye a un secreto.
const MASCARA: &str = "***";

/// Prefijo de las claves de API de Google y longitud de lo que le sigue.
const PREFIJO_CLAVE_GOOGLE: &str = "AIza";
const LARGO_CLAVE_GOOGLE: usize = 35;

/// Claves de `clave=valor` cuyo valor se oculta siempre.
const CLAVES_SENSIBLES: &[&str] = &[
    "password",
    "passwd",
    "client_secret",
    "secret",
    "api_key",
    "apikey",
    "token",
    "key",
];

/// Archivo de log que rota por tamaño.
pub struct RotatingLog {
    path: PathBuf,
    max_bytes: u64,
    max_files: usize,
    file: File,
    size: u64,
}

impl RotatingLog {
    pub fn open(path: &Path, max_bytes: u64, max_files: usize) -> io::Result<Self> {
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let file = OpenOptions::new().create(true).append(true).open(path)?;
        let size = file.metadata()?.len();
        Ok(Self {
            path: path.to_path_buf(),
            max_bytes,
            max_files: max_files.max(1),
            file,
            size,
        })
    }

    /// Escribe una linea, rotando antes si no cabe en el archivo actual.
    pub fn write_line(&mut self, line: &str) -> io::Result<()> {
        // Una linea mas larga que el archivo entero se recorta: el limite de
        // tamaño es de cada archivo, no una sugerencia.
        let maximo = usize::try_from(self.max_bytes.saturating_sub(1)).unwrap_or(usize::MAX);
        let mut fin = line.len().min(maximo);
        while !line.is_char_boundary(fin) {
            fin -= 1;
        }
        let linea = format!("{}\n", &line[..fin]);
        let largo = linea.len() as u64;

        if self.size > 0 && self.size + largo > self.max_bytes {
            self.rotate()?;
        }
        self.file.write_all(linea.as_bytes())?;
        self.size += largo;
        Ok(())
    }

    fn numerado(&self, n: usize) -> PathBuf {
        let mut nombre = self.path.as_os_str().to_os_string();
        nombre.push(format!(".{n}"));
        PathBuf::from(nombre)
    }

    /// `sidecar.log` pasa a `.1`, `.1` a `.2`... y el mas viejo se borra.
    fn rotate(&mut self) -> io::Result<()> {
        self.file.flush()?;
        if self.max_files > 1 {
            let ultimo = self.numerado(self.max_files - 1);
            if ultimo.exists() {
                std::fs::remove_file(&ultimo)?;
            }
            for n in (1..self.max_files - 1).rev() {
                let origen = self.numerado(n);
                if origen.exists() {
                    std::fs::rename(&origen, self.numerado(n + 1))?;
                }
            }
            std::fs::rename(&self.path, self.numerado(1))?;
        } else {
            std::fs::remove_file(&self.path)?;
        }
        self.file = OpenOptions::new().create(true).append(true).open(&self.path)?;
        self.size = 0;
        Ok(())
    }
}

fn es_de_clave(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_' || c == '-'
}

fn fin_de_valor(c: char) -> bool {
    c.is_whitespace() || matches!(c, '&' | '"' | '\'' | ';' | ',' | ')' | '}' | ']')
}

/// Oculta los valores con forma de clave de Google.
fn sin_claves_de_google(linea: &str) -> String {
    let mut salida = String::with_capacity(linea.len());
    let mut resto = linea;
    while let Some(pos) = resto.find(PREFIJO_CLAVE_GOOGLE) {
        let tras = &resto[pos + PREFIJO_CLAVE_GOOGLE.len()..];
        let largo = tras.chars().take_while(|&c| es_de_clave(c)).count();
        salida.push_str(&resto[..pos]);
        if largo >= LARGO_CLAVE_GOOGLE {
            salida.push_str(MASCARA);
            resto = &tras[largo..];
        } else {
            salida.push_str(PREFIJO_CLAVE_GOOGLE);
            resto = tras;
        }
    }
    salida.push_str(resto);
    salida
}

/// Oculta lo que sigue a `marca` hasta el fin del valor. `marca` se busca
/// sin distinguir mayusculas y solo al principio de una palabra.
fn sin_valor_tras(linea: &str, marca: &str) -> String {
    let minusculas = linea.to_ascii_lowercase();
    let mut salida = String::with_capacity(linea.len());
    let mut desde = 0;
    while let Some(rel) = minusculas[desde..].find(marca) {
        let pos = desde + rel;
        let al_principio = linea[..pos].chars().next_back().map_or(true, |c| !es_de_clave(c));
        let inicio_valor = pos + marca.len();
        salida.push_str(&linea[desde..inicio_valor]);
        if al_principio {
            let largo = linea[inicio_valor..]
                .find(fin_de_valor)
                .unwrap_or(linea.len() - inicio_valor);
            if largo > 0 {
                salida.push_str(MASCARA);
            }
            desde = inicio_valor + largo;
        } else {
            desde = inicio_valor;
        }
    }
    salida.push_str(&linea[desde..]);
    salida
}

/// Quita de una linea todo lo que parezca un secreto.
///
/// `secrets` son valores conocidos (el token del sidecar); ademas se ocultan
/// las claves con forma de Google, lo que sigue a `Bearer ` y los valores de
/// `password=`, `secret=`, `token=`, `api_key=`...
pub fn redact(line: &str, secrets: &[&str]) -> String {
    let mut limpia = line.to_string();
    for secreto in secrets.iter().filter(|s| !s.is_empty()) {
        limpia = limpia.replace(secreto, MASCARA);
    }
    limpia = sin_claves_de_google(&limpia);
    limpia = sin_valor_tras(&limpia, "bearer ");
    for clave in CLAVES_SENSIBLES {
        limpia = sin_valor_tras(&limpia, &format!("{clave}="));
    }
    limpia
}

/// Copia `fuente` al log linea a linea, filtrada, en un hilo propio.
///
/// Termina cuando la fuente se cierra (el proceso hijo muere). Un fallo al
/// escribir no detiene la lectura: si el hijo llenara su tuberia sin que
/// nadie la vaciara, se quedaria bloqueado.
pub fn volcar<R: Read + Send + 'static>(
    fuente: R,
    destino: Arc<Mutex<RotatingLog>>,
    secretos: Vec<String>,
) -> JoinHandle<()> {
    std::thread::spawn(move || {
        let secretos: Vec<&str> = secretos.iter().map(String::as_str).collect();
        for trozo in BufReader::new(fuente).split(b'\n') {
            let Ok(bytes) = trozo else { break };
            let linea = String::from_utf8_lossy(&bytes);
            let linea = redact(linea.trim_end_matches('\r'), &secretos);
            let mut log = destino.lock().unwrap_or_else(PoisonError::into_inner);
            let _ = log.write_line(&linea);
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::DirTemporal;

    fn directorio(nombre: &str) -> DirTemporal {
        DirTemporal::nuevo(nombre)
    }

    /// Clave con la forma de las de Google, construida en ejecucion: ningun
    /// literal con esa forma llega al repositorio.
    fn clave_de_google() -> String {
        format!("AIza{}", "Q7x".repeat(11) + "Sy")
    }

    #[test]
    fn una_linea_del_hijo_llega_al_archivo() {
        let dir = directorio("log_hijo");
        let ruta = dir.join(LOG_FILE_NAME);
        let log = Arc::new(Mutex::new(RotatingLog::open(&ruta, MAX_BYTES, MAX_FILES).unwrap()));

        #[cfg(windows)]
        let mut hijo = std::process::Command::new("cmd")
            .args(["/C", "echo linea-del-hijo"])
            .stdout(std::process::Stdio::piped())
            .spawn()
            .unwrap();
        #[cfg(not(windows))]
        let mut hijo = std::process::Command::new("sh")
            .args(["-c", "echo linea-del-hijo"])
            .stdout(std::process::Stdio::piped())
            .spawn()
            .unwrap();

        volcar(hijo.stdout.take().unwrap(), log, vec![]).join().unwrap();
        hijo.wait().unwrap();
        let texto = std::fs::read_to_string(&ruta).unwrap_or_default();
        assert!(texto.contains("linea-del-hijo"), "el archivo no tiene la linea: {texto:?}");
    }

    #[test]
    fn una_linea_con_forma_de_clave_llega_enmascarada() {
        let dir = directorio("log_clave");
        let ruta = dir.join(LOG_FILE_NAME);
        let log = Arc::new(Mutex::new(RotatingLog::open(&ruta, MAX_BYTES, MAX_FILES).unwrap()));
        let clave = clave_de_google();
        let token = "f0".repeat(32);
        let lineas = format!(
            "fallo con key={clave} en la URL\nAuthorization: Bearer {token}\n\
             token del proceso {token}\npassword=hunter2&user=x\n"
        );

        volcar(io::Cursor::new(lineas.into_bytes()), log, vec![token.clone()])
            .join()
            .unwrap();
        let texto = std::fs::read_to_string(&ruta).unwrap();
        assert!(!texto.contains(&clave));
        assert!(!texto.contains(&token));
        assert!(!texto.contains("hunter2"));
        assert!(texto.contains("fallo con key="), "se pierde el contexto: {texto:?}");
    }

    #[test]
    fn la_rotacion_respeta_tamano_y_numero_de_archivos() {
        let dir = directorio("log_rotacion");
        let ruta = dir.join(LOG_FILE_NAME);
        let (max_bytes, max_files) = (200, 3);
        let mut log = RotatingLog::open(&ruta, max_bytes, max_files).unwrap();
        for n in 0..100 {
            log.write_line(&format!("linea {n:03} con algo de relleno")).unwrap();
        }
        drop(log);

        let archivos: Vec<_> = std::fs::read_dir(&*dir).unwrap().flatten().collect();
        assert_eq!(archivos.len(), max_files, "debe haber exactamente {max_files} archivos");
        for archivo in &archivos {
            let tam = archivo.metadata().unwrap().len();
            assert!(tam <= max_bytes, "{:?} ocupa {tam} > {max_bytes}", archivo.path());
        }
        // Lo ultimo escrito esta en el archivo actual; lo mas viejo se perdio.
        assert!(std::fs::read_to_string(&ruta).unwrap().contains("linea 099"));
        let todo: String = archivos
            .iter()
            .map(|a| std::fs::read_to_string(a.path()).unwrap())
            .collect();
        assert!(!todo.contains("linea 000"));
    }
}
