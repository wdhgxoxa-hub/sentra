//! Salud agregada de la aplicacion.
//!
//! El radar son tres procesos que pueden fallar por separado: la ventana
//! puede estar viva con PostgreSQL caido, o con la base bien y el sidecar
//! sin arrancar. Un unico indicador "ok/ko" ocultaria justo lo que hace
//! falta saber para arreglarlo, asi que se informa de cada pieza.

use std::sync::Arc;

use serde::Serialize;
use tauri::State;

use crate::commands::engine::{sidecar_health, sidecar_url};
use crate::db::{connect_options, AppState, DatabaseStatus, RadarResult};
use crate::sidecar::{LaunchFailure, SidecarManager, SidecarStatus, SIDECAR_EVENT_CHANNEL};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ComponentHealth {
    pub ok: bool,
    pub detail: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppHealth {
    /// true solo si las tres piezas responden.
    pub ok: bool,
    pub version: String,
    pub app: ComponentHealth,
    pub postgres: ComponentHealth,
    pub sidecar: ComponentHealth,
    /// Cuerpo de /api/health del sidecar, si respondio.
    pub sidecar_info: Option<serde_json::Value>,
    /// Por qué no se pudo arrancar el sidecar (D-D), con código traducible.
    pub sidecar_launch: Option<LaunchFailure>,
    /// Huella del código del motor con el que se compiló esta interfaz; el
    /// motor devuelve la suya en `sidecarInfo.build` (AUD2-003).
    pub motor_build: String,
}

/// Lo que se dice del motor cuando no responde. Lo lee el usuario: nada de
/// comandos de terminal (AUD-065); la interfaz ofrece «Reintentar motor».
pub(crate) fn detalle_sin_respuesta(url: &str) -> String {
    format!("sin respuesta en {url}")
}

/// Vuelve a arrancar el motor si no responde (AUD-056).
///
/// El arranque de la ventana lo intenta una vez; si el motor tardó más de lo
/// esperado (la primera carga del modelo) o murió, antes solo quedaba cerrar
/// la app. Si ya responde no hace nada. El resultado viaja también por el
/// canal del arranque, que la interfaz escucha para refrescar la salud.
#[tauri::command]
pub async fn retry_sidecar(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    manager: State<'_, Arc<SidecarManager>>,
) -> RadarResult<SidecarStatus> {
    use tauri::Manager;

    let log_dir = app.path().app_log_dir().ok();
    let status = manager.ensure_running(&state.http, log_dir.as_deref()).await;
    let _ = tauri::Emitter::emit(&app, SIDECAR_EVENT_CHANNEL, status);
    Ok(status)
}

/// Lo que se dice del motor cuando responde: si persiste en PostgreSQL. El
/// embedder, el NLI y el estado del escaner de Reddit eran de la pipeline
/// antigua y se retiraron con ella (C2).
fn detalle_del_motor(cuerpo: &serde_json::Value) -> String {
    let persiste = cuerpo
        .get("persistence")
        .and_then(|p| p.get("enabled"))
        .and_then(serde_json::Value::as_bool);
    match persiste {
        Some(true) => "activo (persiste en PostgreSQL)".into(),
        Some(false) => "activo (sin persistencia)".into(),
        None => "activo".into(),
    }
}

/// Estado de Rust, PostgreSQL y el sidecar Python.
#[tauri::command]
pub async fn get_app_health(
    state: State<'_, AppState>,
    manager: State<'_, Arc<SidecarManager>>,
) -> RadarResult<AppHealth> {
    let app = ComponentHealth {
        ok: true,
        detail: format!("Tauri {}", env!("CARGO_PKG_VERSION")),
    };

    let postgres = match state.db.pool() {
        Ok(pool) => match sqlx::query_scalar::<_, i32>("SELECT 1")
            .fetch_one(&pool)
            .await
        {
            Ok(_) => ComponentHealth {
                ok: true,
                detail: "conectado".into(),
            },
            Err(err) => ComponentHealth {
                ok: false,
                detail: format!("sin conexion: {err}"),
            },
        },
        Err(err) => ComponentHealth {
            ok: false,
            detail: format!("sin conexion: {err}"),
        },
    };

    let info = sidecar_health(&state.http).await;
    let sidecar = match &info {
        Some(body) => ComponentHealth {
            ok: true,
            detail: detalle_del_motor(body),
        },
        None => ComponentHealth {
            ok: false,
            detail: detalle_sin_respuesta(&sidecar_url()),
        },
    };

    Ok(AppHealth {
        ok: app.ok && postgres.ok && sidecar.ok,
        version: env!("CARGO_PKG_VERSION").to_string(),
        app,
        postgres,
        sidecar,
        sidecar_info: info,
        sidecar_launch: manager.ultimo_fallo(),
        motor_build: crate::motor::HUELLA.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn sin_motor_no_se_le_pide_al_usuario_un_comando_de_terminal() {
        // AUD-065: el detalle lo ve el usuario, no quien desarrolla.
        let detalle = detalle_sin_respuesta("http://127.0.0.1:8765");
        assert!(detalle.contains("127.0.0.1:8765"));
        assert!(!detalle.contains("python"), "{detalle}");
        assert!(!detalle.to_lowercase().contains("arrancalo"), "{detalle}");
    }

    #[test]
    fn el_detalle_dice_si_el_motor_persiste() {
        assert_eq!(
            detalle_del_motor(&json!({ "persistence": { "enabled": true } })),
            "activo (persiste en PostgreSQL)"
        );
        assert_eq!(
            detalle_del_motor(&json!({ "persistence": { "enabled": false } })),
            "activo (sin persistencia)"
        );
        assert_eq!(detalle_del_motor(&json!({ "status": "ok" })), "activo");
    }
}

/// Si hay conexion con PostgreSQL y, si no, por que (D-F).
#[tauri::command]
pub fn get_database_status(state: State<'_, AppState>) -> DatabaseStatus {
    state.db.status()
}

/// Vuelve a intentar la conexion con PostgreSQL (boton «Reintentar»).
#[tauri::command]
pub async fn retry_database(state: State<'_, AppState>) -> RadarResult<DatabaseStatus> {
    Ok(state.db.reintentar(connect_options()).await)
}
