//! Salud agregada de la aplicacion.
//!
//! El radar son tres procesos que pueden fallar por separado: la ventana
//! puede estar viva con PostgreSQL caido, o con la base bien y el sidecar
//! sin arrancar. Un unico indicador "ok/ko" ocultaria justo lo que hace
//! falta saber para arreglarlo, asi que se informa de cada pieza.

use serde::Serialize;
use tauri::State;

use crate::commands::engine::{sidecar_health, sidecar_url};
use crate::db::{AppState, RadarResult};

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
}

/// Estado de Rust, PostgreSQL y el sidecar Python.
#[tauri::command]
pub async fn get_app_health(state: State<'_, AppState>) -> RadarResult<AppHealth> {
    let app = ComponentHealth {
        ok: true,
        detail: format!("Tauri {}", env!("CARGO_PKG_VERSION")),
    };

    let postgres = match sqlx::query_scalar::<_, i32>("SELECT 1")
        .fetch_one(&state.pool)
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
    };

    let info = sidecar_health(&state.http).await;
    let sidecar = match &info {
        Some(body) => {
            // Se destaca el motor de clasificacion: mientras el NLI corra en
            // modo heuristico, quien mire el panel debe poder saberlo.
            let engine = body
                .get("nli")
                .and_then(|n| n.get("engine"))
                .and_then(|e| e.as_str())
                .unwrap_or("desconocido");
            let embedder = body
                .get("embedder")
                .and_then(|e| e.get("name"))
                .and_then(|n| n.as_str())
                .unwrap_or("desconocido");
            ComponentHealth {
                ok: true,
                detail: format!("activo (embedder: {embedder}, NLI: {engine})"),
            }
        }
        None => ComponentHealth {
            ok: false,
            detail: format!(
                "sin respuesta en {}. Arrancalo con: \
                 python -m core.orchestration.sidecar_server",
                sidecar_url()
            ),
        },
    };

    Ok(AppHealth {
        ok: app.ok && postgres.ok && sidecar.ok,
        version: env!("CARGO_PKG_VERSION").to_string(),
        app,
        postgres,
        sidecar,
        sidecar_info: info,
    })
}
