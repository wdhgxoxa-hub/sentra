//! Log de la aplicación (AUD2-013).
//!
//! tauri-plugin-log por defecto guarda 40.000 bytes en un solo fichero
//! (KeepOne) y sin nivel explícito: con hyper, reqwest y sqlx en TRACE, en el
//! incidente de la pantalla negra el log solo cubría el último minuto. Aquí
//! se fija un tamaño y unas copias que guardan días de uso, INFO en la release
//! y los módulos ruidosos en WARN.

use log::LevelFilter;

/// Tamaño de cada fichero de log antes de rotar.
pub const MAX_BYTES: u128 = 2_000_000;
/// Ficheros que se conservan al rotar (el actual más los anteriores).
pub const COPIAS: usize = 5;

// Comprobado al compilar: un valor que vuelva a guardar un minuto no compila.
const _: () = assert!(MAX_BYTES >= 1_000_000, "un fichero tiene que caber más de un arranque");
const _: () = assert!(COPIAS >= 3, "rotar no puede borrar lo de ayer");

/// Nivel general: DEBUG en desarrollo, INFO en la release.
pub fn nivel() -> LevelFilter {
    if cfg!(debug_assertions) {
        LevelFilter::Debug
    } else {
        LevelFilter::Info
    }
}

/// Módulos de terceros que en TRACE/DEBUG llenan el log sin decir nada útil.
pub const RUIDOSOS: &[&str] = &["hyper", "hyper_util", "reqwest", "sqlx", "rustls", "tao", "wry"];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn la_release_registra_en_info() {
        if cfg!(debug_assertions) {
            assert_eq!(nivel(), LevelFilter::Debug);
        } else {
            assert_eq!(nivel(), LevelFilter::Info);
        }
    }

    #[test]
    fn los_modulos_ruidosos_estan_callados() {
        for modulo in ["hyper_util", "reqwest", "sqlx", "tao"] {
            assert!(RUIDOSOS.contains(&modulo), "{modulo}");
        }
    }
}
