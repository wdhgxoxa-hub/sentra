//! Reddit Intelligence Radar: aplicacion de escritorio.
//!
//! Reparto de responsabilidades entre los tres procesos:
//!
//! ```text
//!   WebView (React)  --invoke-->  Rust  --sqlx-->     PostgreSQL
//!                                      --HTTP-->      sidecar Python
//! ```

pub mod commands;
pub mod db;

use db::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // El pool se abre antes de arrancar la ventana: si la base no responde,
    // conviene enterarse ahora y no en la primera consulta del usuario.
    let runtime = tokio::runtime::Runtime::new().expect("no se pudo crear el runtime");
    let pool = runtime
        .block_on(db::create_pool())
        .expect("no se pudo conectar a PostgreSQL: revisa RIR_PG_URL");

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState { pool })
        .invoke_handler(tauri::generate_handler![
            commands::radar::get_radar_feed,
            commands::radar::get_opportunity_board,
            commands::engine::search_hybrid,
            commands::engine::trigger_scan,
        ])
        .run(tauri::generate_context!())
        .expect("fallo al arrancar la aplicacion");
}
