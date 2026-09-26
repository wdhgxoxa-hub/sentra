//! La ventana principal: visible y con foco, salvo en modo discreto.
//!
//! La prueba de humo abre y cierra la app en cada commit; con la ventana a la
//! vista le robaba el foco a quien usa el ordenador (Walter, Fase 3). Windows
//! ignora el modo de arranque que pide quien lanza el exe (medido: SW_HIDE y
//! SW_SHOWMINNOACTIVE dejan la ventana visible y en primer plano), asi que lo
//! decide la app: la ventana nace oculta (tauri.conf.json) y `setup` la
//! muestra y la enfoca, salvo con `SENTRA_VENTANA_DISCRETA=1`, que solo pone
//! el humo.

/// Variable de entorno del modo discreto.
pub const DISCRETA_ENV_VAR: &str = "SENTRA_VENTANA_DISCRETA";

/// ¿Modo discreto? Solo con el valor exacto «1».
pub fn es_discreta(valor: Option<&str>) -> bool {
    valor == Some("1")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn solo_el_uno_exacto_es_discreto() {
        assert!(es_discreta(Some("1")));
        assert!(!es_discreta(None));
        assert!(!es_discreta(Some("0")));
        assert!(!es_discreta(Some("")));
        assert!(!es_discreta(Some("true")));
    }
}
