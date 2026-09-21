//! Reddit Intelligence Radar: aplicacion de escritorio.
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

use std::sync::Arc;

use tauri::{Manager, RunEvent};

use db::AppState;
use sidecar::SidecarManager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let runtime = tokio::runtime::Runtime::new().expect("no se pudo crear el runtime");

    // El pool se abre antes de arrancar la ventana: si la base no responde,
    // conviene enterarse ahora y no en la primera consulta del usuario.
    let pool = runtime
        .block_on(db::create_pool())
        .expect("no se pudo conectar a PostgreSQL: revisa RIR_PG_URL");

    // Un unico cliente HTTP para todo el proceso: reqwest mantiene su
    // propio pool de conexiones hacia el sidecar.
    let http = reqwest::Client::builder()
        .user_agent(concat!("radar-desktop/", env!("CARGO_PKG_VERSION")))
        .build()
        .expect("no se pudo crear el cliente HTTP");

    let manager = Arc::new(SidecarManager::new());

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_log::Builder::new().build())
        .manage(AppState {
            pool,
            http: http.clone(),
        })
        .manage(manager.clone())
        .setup({
            let manager = manager.clone();
            move |app| {
                // El arranque del sidecar no bloquea la ventana: cargar el
                // modelo de embeddings tarda, y mas vale ensenar la interfaz
                // con el indicador en rojo que una pantalla congelada.
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let status = manager.ensure_running(&http).await;
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
            // Motor Python
            commands::engine::search_hybrid,
            commands::engine::trigger_scan,
            // Escrituras
            commands::mutations::update_opportunity_status,
            commands::mutations::upsert_subreddit,
            commands::mutations::cancel_scan,
            // Estado agregado
            commands::health::get_app_health,
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
