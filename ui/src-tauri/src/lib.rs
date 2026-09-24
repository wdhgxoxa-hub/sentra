//! SENTRA: aplicacion de escritorio.
//!
//! Reparto de responsabilidades entre los tres procesos:
//!
//! ```text
//!   WebView (React)  --invoke-->  Rust  --sqlx-->     PostgreSQL
//!                    <--events--        --reqwest-->  sidecar Python
//! ```
//!
//! Rust resuelve las lecturas del panel directamente contra PostgreSQL, y
//! delega en el sidecar solo lo que unicamente Python sabe hacer: ejecutar
//! el grafo LangGraph y buscar sobre LanceDB. Ademas se encarga del ciclo
//! de vida de ese proceso hijo: lo arranca al abrir y lo recoge al cerrar.

pub mod commands;
pub mod db;
pub mod sidecar;
pub mod sidecar_log;

#[cfg(test)]
mod test_support;

use std::sync::Arc;

use tauri::{Manager, RunEvent};

use db::{AppState, Database};
use sidecar::SidecarManager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let runtime = tokio::runtime::Runtime::new().expect("no se pudo crear el runtime");

    // La base se abre antes de arrancar la ventana, pero su fallo ya no
    // cierra la aplicacion (D-F): queda como estado, la interfaz enseña por
    // que y deja reintentar.
    let db = runtime.block_on(Database::conectar(db::connect_options()));

    // Un unico cliente HTTP para todo el proceso: reqwest mantiene su
    // propio pool de conexiones hacia el sidecar.
    let http = reqwest::Client::builder()
        .user_agent(concat!("sentra-desktop/", env!("CARGO_PKG_VERSION")))
        .build()
        .expect("no se pudo crear el cliente HTTP");

    let manager = Arc::new(SidecarManager::new());

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_log::Builder::new().build())
        .manage(AppState {
            db,
            http: http.clone(),
        })
        .manage(manager.clone())
        .setup({
            let manager = manager.clone();
            move |app| {
                // La salida del sidecar va al directorio de logs de la app (D-E).
                let log_dir = app.path().app_log_dir().ok();
                // El arranque del sidecar no bloquea la ventana: cargar el
                // modelo de embeddings tarda, y mas vale ensenar la interfaz
                // con el indicador en rojo que una pantalla congelada.
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let status = manager.ensure_running(&http, log_dir.as_deref()).await;
                    log::info!("Estado del sidecar: {status:?}");
                    let _ = tauri::Emitter::emit(&handle, sidecar::SIDECAR_EVENT_CHANNEL, status);
                });
                Ok(())
            }
        })
        .invoke_handler(tauri::generate_handler![
            // Motor Python
            commands::engine::search_hybrid,
            // Escrituras
            commands::mutations::cancel_scan,
            // Configuracion
            commands::settings::get_settings,
            // Fuentes (F2)
            commands::sources::list_sources,
            commands::sources::save_source_credentials,
            commands::sources::probe_source,
            commands::sources::set_source_enabled,
            commands::sources::set_commercial_mode,
            commands::sources::trigger_multiscan,
            // Juez de nichos (F3)
            commands::judge::get_judge_top,
            commands::judge::get_evidence_feed,
            // Documentos de un veredicto (Fase E)
            commands::documents::export_document,
            // Clave y modelos de Gemini
            commands::gemini::save_gemini_key,
            commands::gemini::test_gemini_key,
            commands::gemini::list_gemini_models,
            // Estado agregado
            commands::health::get_app_health,
            commands::health::get_database_status,
            commands::health::retry_database,
            commands::health::retry_sidecar,
        ])
        .build(tauri::generate_context!())
        .expect("fallo al construir la aplicacion")
        .run(move |app_handle, event| {
            // Cerrar la ventana no debe dejar un proceso de Python huerfano
            // consumiendo memoria hasta el siguiente reinicio.
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                if let Some(manager) = app_handle.try_state::<Arc<SidecarManager>>() {
                    manager.shutdown();
                }
            }
        });
}
