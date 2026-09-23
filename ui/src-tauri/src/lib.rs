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
        .user_agent(concat!("radar-desktop/", env!("CARGO_PKG_VERSION")))
        .build()
        .expect("no se pudo crear el cliente HTTP");

    let manager = Arc::new(SidecarManager::new());

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
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
                    let _ = tauri::Emitter::emit(&handle, "radar:sidecar", status);
                });
                Ok(())
            }
        })
        .invoke_handler(tauri::generate_handler![
            // Lecturas contra PostgreSQL
            commands::radar::get_radar_feed,
            commands::radar::get_opportunity_board,
            commands::radar::get_opportunity_detail,
            commands::radar::get_cluster_history,
            commands::radar::get_subreddits,
            commands::radar::get_pipeline_runs,
            commands::radar::get_top_opportunities,
            // Motor Python
            commands::engine::search_hybrid,
            commands::engine::trigger_scan,
            commands::engine::translate_quotes,
            // Escrituras
            commands::mutations::update_opportunity_status,
            commands::mutations::upsert_subreddit,
            commands::mutations::cancel_scan,
            // Configuracion
            commands::settings::get_settings,
            commands::settings::set_fetcher_mode,
            commands::settings::save_reddit_credentials,
            commands::settings::test_reddit_connection,
            // Fuentes (F2)
            commands::sources::list_sources,
            commands::sources::save_source_credentials,
            commands::sources::probe_source,
            commands::sources::set_source_enabled,
            commands::sources::set_commercial_mode,
            commands::sources::trigger_multiscan,
            // Juez de nichos (F3)
            commands::judge::get_judge_top,
            // Especificacion de proyecto
            commands::blueprint::generate_blueprint,
            // Documento entregable (AUD-008)
            commands::document::export_pdf,
            // Motor de arquitectura (Gemini)
            commands::architect::save_gemini_key,
            commands::architect::test_gemini_key,
            commands::architect::list_gemini_models,
            commands::architect::generate_architecture,
            // Estado agregado
            commands::health::get_app_health,
            commands::health::get_database_status,
            commands::health::retry_database,
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
