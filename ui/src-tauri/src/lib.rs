//! Reddit Intelligence Radar: aplicacion de escritorio.
//!
//! Reparto de responsabilidades entre los tres procesos:
//!
//! ```text
//!   WebView (React)  --invoke-->  Rust  --sqlx-->     PostgreSQL
//!                                      --reqwest-->   sidecar Python
//! ```
//!
//! Rust resuelve las lecturas del panel directamente contra PostgreSQL, y
//! delega en el sidecar solo lo que unicamente Python sabe hacer: ejecutar
//! el grafo LangGraph y buscar sobre LanceDB.

pub mod commands;
pub mod db;

use db::AppState;

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

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState { pool, http })
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
            // Estado agregado
            commands::health::get_app_health,
        ])
        .run(tauri::generate_context!())
        .expect("fallo al arrancar la aplicacion");
}
