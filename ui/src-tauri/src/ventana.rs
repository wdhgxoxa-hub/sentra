//! La ventana principal: visible y con foco, salvo en modo discreto.
//!
//! La prueba de humo abre y cierra la app en cada commit; con la ventana a la
//! vista le robaba el foco a quien usa el ordenador (Walter, Fase 3). Windows
//! ignora el modo de arranque que pide quien lanza el exe (medido: SW_HIDE y
//! SW_SHOWMINNOACTIVE dejan la ventana visible y en primer plano), asi que lo
//! decide la app: la ventana nace oculta (tauri.conf.json) y `setup` la
//! muestra y la enfoca, salvo con `SENTRA_VENTANA_DISCRETA=1`, que solo pone
//! el humo.
//!
//! El humo también aísla el perfil del WebView. En Windows lo hace con
//! WEBVIEW2_USER_DATA_FOLDER; WebKitGTK no tiene equivalente, así que la
//! ventana se construye en `setup` (tauri.conf.json no la crea) y, con
//! `SENTRA_PERFIL_WEBVIEW`, guarda su perfil en esa carpeta.

use std::path::PathBuf;

/// Variable de entorno del modo discreto.
pub const DISCRETA_ENV_VAR: &str = "SENTRA_VENTANA_DISCRETA";

/// ¿Modo discreto? Solo con el valor exacto «1».
pub fn es_discreta(valor: Option<&str>) -> bool {
    valor == Some("1")
}

/// Variable de entorno con la carpeta del perfil aislado del WebView.
pub const PERFIL_ENV_VAR: &str = "SENTRA_PERFIL_WEBVIEW";

/// Carpeta del perfil aislado: solo una ruta absoluta (una relativa
/// dependería de la carpeta desde la que se lanza la app).
pub fn perfil_webview(valor: Option<&str>) -> Option<PathBuf> {
    let ruta = PathBuf::from(valor?);
    ruta.is_absolute().then_some(ruta)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_perfil_del_humo_solo_vale_con_una_ruta_absoluta() {
        assert_eq!(perfil_webview(None), None);
        assert_eq!(perfil_webview(Some("")), None);
        assert_eq!(perfil_webview(Some("perfil")), None);
        let absoluta = std::env::temp_dir().join("sentra_humo_webview");
        assert_eq!(perfil_webview(absoluta.to_str()), Some(absoluta));
    }

    #[test]
    fn solo_el_uno_exacto_es_discreto() {
        assert!(es_discreta(Some("1")));
        assert!(!es_discreta(None));
        assert!(!es_discreta(Some("0")));
        assert!(!es_discreta(Some("")));
        assert!(!es_discreta(Some("true")));
    }
}
