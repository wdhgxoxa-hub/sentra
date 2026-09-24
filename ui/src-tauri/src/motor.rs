//! Motor fijado a la versión de la interfaz (AUD2-003, DP1 B).
//!
//! La interfaz lleva dentro el código del motor con el que se compiló
//! (`build.rs` lo empaqueta y calcula su huella). Al arrancar lo
//! desempaqueta en `<datos locales>/motor/<huella>/` y el motor se lanza
//! desde allí: cambiar de rama en el repositorio ya no cambia el motor de la
//! release. El `.venv` y los datos (`.env`, vectores) siguen en la carpeta
//! del proyecto, compartidos (`RIR_DATA_DIR`). El motor devuelve su propia
//! huella en `/api/health` y el gestor la compara con `HUELLA`.

use std::path::{Path, PathBuf};

use crate::empaquetado;

/// Marcador que se escribe al final de desempaquetar: sin él, la carpeta
/// está a medias y se rehace.
pub const MARCADOR: &str = ".completo";

/// Huella del código del motor con el que se compiló esta interfaz.
pub const HUELLA: &str = env!("SENTRA_HUELLA_MOTOR");

/// El código del motor, empaquetado por build.rs.
static PAQUETE: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/motor.bin"));

/// Deja el motor de esta versión en `<base>/motor/<HUELLA>/` y devuelve la
/// carpeta. Si ya estaba completo no lo toca; si estaba a medias lo rehace;
/// las carpetas de otras versiones se borran.
pub fn preparar(base: &Path) -> std::io::Result<PathBuf> {
    let versiones = base.join("motor");
    let destino = versiones.join(HUELLA);
    if !destino.join(MARCADOR).is_file() {
        let ficheros = empaquetado::desempaquetar(PAQUETE)
            .ok_or_else(|| std::io::Error::other("el paquete del motor está dañado"))?;
        // Se escribe en una carpeta temporal y se renombra al final: un corte a
        // medias nunca deja una copia que parezca completa.
        let temporal = versiones.join(format!(".{HUELLA}.{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&temporal);
        for (ruta, contenido) in &ficheros {
            let fichero = temporal.join(ruta);
            if let Some(padre) = fichero.parent() {
                std::fs::create_dir_all(padre)?;
            }
            std::fs::write(fichero, contenido)?;
        }
        std::fs::write(temporal.join(MARCADOR), HUELLA)?;
        if destino.exists() {
            std::fs::remove_dir_all(&destino)?;
        }
        std::fs::rename(&temporal, &destino)?;
    }
    // Las otras versiones ya no las lanza nadie.
    for entrada in std::fs::read_dir(&versiones)?.flatten() {
        let ruta = entrada.path();
        if ruta != destino && ruta.is_dir() {
            let _ = std::fs::remove_dir_all(ruta);
        }
    }
    Ok(destino)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base_temporal(nombre: &str) -> PathBuf {
        let base = std::env::temp_dir().join(format!("sentra_{nombre}_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        base
    }

    /// Huella de lo que hay en una carpeta (sin marcadores ni caché de Python),
    /// como `core.rutas.huella_de_carpeta`.
    fn huella_de_carpeta(raiz: &Path) -> String {
        fn recorrer(raiz: &Path, dir: &Path, salida: &mut Vec<(String, Vec<u8>)>) {
            for entrada in std::fs::read_dir(dir).unwrap() {
                let ruta = entrada.unwrap().path();
                let nombre = ruta.file_name().unwrap().to_string_lossy().into_owned();
                if nombre.starts_with('.') || nombre == "__pycache__" {
                    continue;
                }
                if ruta.is_dir() {
                    recorrer(raiz, &ruta, salida);
                } else {
                    let rel = ruta.strip_prefix(raiz).unwrap().components()
                        .map(|c| c.as_os_str().to_string_lossy().into_owned()).collect::<Vec<_>>().join("/");
                    salida.push((rel, std::fs::read(&ruta).unwrap()));
                }
            }
        }
        let mut ficheros = Vec::new();
        recorrer(raiz, raiz, &mut ficheros);
        empaquetado::huella(&ficheros)
    }

    #[test]
    fn el_paquete_es_el_motor_y_su_huella_es_la_compilada() {
        let ficheros = empaquetado::desempaquetar(PAQUETE).expect("paquete legible");
        assert!(ficheros.iter().any(|(r, _)| r == "core/orchestration/sidecar_server.py"));
        assert!(ficheros.iter().any(|(r, _)| r == "scripts/migrate.py"));
        assert!(ficheros.iter().all(|(r, _)| !r.contains("__pycache__") && !r.starts_with("tests/")));
        assert_eq!(empaquetado::huella(&ficheros), HUELLA);
    }

    #[test]
    fn preparar_deja_la_copia_versionada_con_la_huella_compilada() {
        let base = base_temporal("preparar");
        let dir = preparar(&base).expect("preparar");
        assert_eq!(dir, base.join("motor").join(HUELLA));
        assert!(dir.join(MARCADOR).is_file());
        assert!(dir.join("core").join("rutas.py").is_file());
        assert_eq!(huella_de_carpeta(&dir), HUELLA);
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn una_copia_completa_no_se_reescribe_y_una_a_medias_se_rehace() {
        let base = base_temporal("rehacer");
        let dir = preparar(&base).unwrap();
        let rutas_py = dir.join("core").join("rutas.py");
        std::fs::write(&rutas_py, "tocado").unwrap();
        preparar(&base).unwrap();
        assert_eq!(std::fs::read_to_string(&rutas_py).unwrap(), "tocado", "completa: no se toca");
        std::fs::remove_file(dir.join(MARCADOR)).unwrap();
        preparar(&base).unwrap();
        assert_ne!(std::fs::read_to_string(&rutas_py).unwrap(), "tocado", "a medias: se rehace");
        assert_eq!(huella_de_carpeta(&dir), HUELLA);
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn las_versiones_antiguas_se_borran() {
        let base = base_temporal("antiguas");
        let vieja = base.join("motor").join("0000000000000000");
        std::fs::create_dir_all(&vieja).unwrap();
        std::fs::write(vieja.join("x.py"), "viejo").unwrap();
        preparar(&base).unwrap();
        assert!(!vieja.exists());
        let _ = std::fs::remove_dir_all(&base);
    }

    fn f(ruta: &str, contenido: &[u8]) -> (String, Vec<u8>) {
        (ruta.to_string(), contenido.to_vec())
    }

    #[test]
    fn vectores_publicados_de_fnv1a_64() {
        // Los mismos que comprueba tests/test_huella_motor.py.
        assert_eq!(empaquetado::fnv1a64(b""), "cbf29ce484222325");
        assert_eq!(empaquetado::fnv1a64(b"a"), "af63dc4c8601ec8c");
        assert_eq!(empaquetado::fnv1a64(b"foobar"), "85944171f73967e8");
    }

    #[test]
    fn la_huella_se_compone_igual_que_en_python() {
        let esperada = empaquetado::fnv1a64(b"a.py\x001\x00xb/c.sql\x002\x00yz");
        assert_eq!(empaquetado::huella(&[f("b/c.sql", b"yz"), f("a.py", b"x")]), esperada);
    }

    #[test]
    fn empaquetar_y_desempaquetar_devuelve_lo_mismo() {
        let ficheros = vec![f("core/m.py", b"x = 1\r\n"), f("sql/migrations/001.sql", b""), f("scripts/migrate.py", &[0, 255])];
        let paquete = empaquetado::empaquetar(&ficheros);
        assert_eq!(empaquetado::desempaquetar(&paquete), Some(ficheros));
        assert_eq!(empaquetado::desempaquetar(&paquete[..paquete.len() - 1]), None, "truncado");
    }

    #[test]
    fn los_ficheros_del_motor_son_core_migraciones_y_migrate() {
        let raiz = std::env::temp_dir().join(format!("sentra_motor_sel_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&raiz);
        for (ruta, contenido) in [
            ("core/a.py", "a"), ("core/sub/b.py", "b"), ("core/documents/fonts/V.ttf", "t"),
            ("core/__pycache__/a.cpython-312.pyc", "no"), ("core/.oculto", "no"),
            ("sql/migrations/001.sql", "s"), ("sql/otro.sql", "no"),
            ("scripts/migrate.py", "m"), ("scripts/__init__.py", ""), ("scripts/otro.py", "no"),
            ("tests/test_x.py", "no"), ("ui/x.ts", "no"),
        ] {
            let p = raiz.join(ruta);
            std::fs::create_dir_all(p.parent().unwrap()).unwrap();
            std::fs::write(p, contenido).unwrap();
        }
        let rutas: Vec<String> = empaquetado::ficheros_del_motor(&raiz).unwrap().into_iter().map(|(r, _)| r).collect();
        let _ = std::fs::remove_dir_all(&raiz);
        assert_eq!(rutas, vec![
            "core/a.py", "core/documents/fonts/V.ttf", "core/sub/b.py",
            "scripts/__init__.py", "scripts/migrate.py", "sql/migrations/001.sql",
        ]);
    }
}
