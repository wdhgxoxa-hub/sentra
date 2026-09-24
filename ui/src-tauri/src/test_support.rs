//! Ayudas de los tests: carpetas temporales que se borran solas.
//!
//! Las bases de PostgreSQL desechables se retiraron con los comandos de la
//! pipeline antigua que las usaban (C2); los comandos que quedan delegan en
//! el sidecar y sus tests no tocan la base.

use std::path::{Path, PathBuf};

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
}
