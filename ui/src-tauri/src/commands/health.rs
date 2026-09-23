//! Salud agregada de la aplicacion.
//!
//! El radar son tres procesos que pueden fallar por separado: la ventana
//! puede estar viva con PostgreSQL caido, o con la base bien y el sidecar
//! sin arrancar. Un unico indicador "ok/ko" ocultaria justo lo que hace
//! falta saber para arreglarlo, asi que se informa de cada pieza.

use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::commands::engine::{sidecar_health, sidecar_url};
use crate::db::{connect_options, AppState, DatabaseStatus, RadarResult};
use crate::sidecar::{LaunchFailure, SidecarManager};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ComponentHealth {
    pub ok: bool,
    pub detail: String,
}

/// Capacidad real de leer datos (AUD-004), tal como la calcula el sidecar.
///
/// Solo `RedditVerificado` significa que Reddit respondió 200 de verdad; es
/// el único estado que la interfaz pinta en verde.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceState {
    Demo,
    RedditSinCredenciales,
    RedditSinVerificar,
    RedditVerificado,
    RedditError,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SourceStatus {
    pub state: SourceState,
    /// Último acceso real con éxito (ISO 8601), si lo hubo.
    pub last_success_at: Option<String>,
    /// Código estable del último fallo, en `RedditError`.
    pub error_code: Option<String>,
}

/// Extrae el estado de la fuente del cuerpo de `/api/health`.
///
/// Un estado desconocido no se convierte en uno conocido: devuelve `None`,
/// que la interfaz muestra como «sin información», nunca como verde.
pub fn source_from_sidecar(body: &serde_json::Value) -> Option<SourceStatus> {
    serde_json::from_value(body.get("source")?.clone()).ok()
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
    /// Estado real de la fuente de datos. `None` si el sidecar no respondió.
    pub source: Option<SourceStatus>,
    /// Por qué no se pudo arrancar el sidecar (D-D), con código traducible.
    pub sidecar_launch: Option<LaunchFailure>,
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

    let source = info.as_ref().and_then(source_from_sidecar);

    Ok(AppHealth {
        ok: app.ok && postgres.ok && sidecar.ok,
        version: env!("CARGO_PKG_VERSION").to_string(),
        app,
        postgres,
        sidecar,
        sidecar_info: info,
        source,
        sidecar_launch: manager.ultimo_fallo(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn cuerpo(source: serde_json::Value) -> serde_json::Value {
        json!({ "status": "ok", "source": source })
    }

    #[test]
    fn cada_estado_del_sidecar_llega_tipado() {
        let casos = [
            ("demo", SourceState::Demo),
            ("reddit_sin_credenciales", SourceState::RedditSinCredenciales),
            ("reddit_sin_verificar", SourceState::RedditSinVerificar),
            ("reddit_verificado", SourceState::RedditVerificado),
            ("reddit_error", SourceState::RedditError),
        ];
        for (texto, esperado) in casos {
            let fuente = source_from_sidecar(&cuerpo(json!({
                "state": texto, "lastSuccessAt": null, "errorCode": null
            })))
            .unwrap_or_else(|| panic!("'{texto}' no se reconocio"));
            assert_eq!(fuente.state, esperado);
        }
    }

    #[test]
    fn la_evidencia_viaja_con_el_estado() {
        let fuente = source_from_sidecar(&cuerpo(json!({
            "state": "reddit_error", "lastSuccessAt": "2026-09-23T10:00:00+00:00",
            "errorCode": "reddit_forbidden"
        })))
        .unwrap();
        assert_eq!(fuente.error_code.as_deref(), Some("reddit_forbidden"));
        assert_eq!(fuente.last_success_at.as_deref(), Some("2026-09-23T10:00:00+00:00"));
    }

    #[test]
    fn un_estado_desconocido_no_se_hace_pasar_por_valido() {
        assert!(source_from_sidecar(&cuerpo(json!({
            "state": "reddit_en_vivo", "lastSuccessAt": null, "errorCode": null
        })))
        .is_none());
    }

    #[test]
    fn sin_bloque_de_fuente_no_hay_estado() {
        assert!(source_from_sidecar(&json!({ "status": "ok" })).is_none());
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
