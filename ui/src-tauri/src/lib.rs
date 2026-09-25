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
pub mod empaquetado;
pub mod motor;
pub mod registro;
pub mod ventana_interna;

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
        .plugin(
            // AUD2-013: sin esto, 40 KB en un solo fichero y todo en TRACE.
            registro::RUIDOSOS
                .iter()
                .fold(
                    tauri_plugin_log::Builder::new()
                        .level(registro::nivel())
                        .max_file_size(registro::MAX_BYTES)
                        .rotation_strategy(tauri_plugin_log::RotationStrategy::KeepSome(registro::COPIAS)),
                    |b, m| b.level_for(*m, log::LevelFilter::Warn),
                )
                .build(),
        )
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
                // El motor corre desde la copia de su código que lleva esta
                // interfaz, no desde el repositorio (AUD2-003, DP1 B).
                manager.usar_motor(match app.path().app_local_data_dir() {
                    Ok(base) => match motor::preparar(&base) {
                        Ok(dir) => {
                            log::info!("Motor {} en {}", motor::HUELLA, dir.display());
                            sidecar::Motor::Versionado { dir, huella: motor::HUELLA.into() }
                        }
                        Err(err) => sidecar::Motor::Fallo(format!("{}: {err}", base.display())),
                    },
                    Err(err) => sidecar::Motor::Fallo(err.to_string()),
                });
                // AUD2-027: un WM_CLOSE a la ventana interna de tao cierra la app
                // en orden en lugar de dejar el proceso colgado.
                if !ventana_interna::proteger(app.handle()) {
                    log::warn!("No se encontró la ventana interna de tao para protegerla");
                }
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
            commands::sources::estimate_scan,
            commands::sources::trigger_multiscan,
            commands::palabras::propose_keywords,
            // Juez de nichos (F3)
            commands::judge::get_judge_top,
            commands::judge::get_evidence_feed,
            // Documentos de un veredicto (Fase E)
            commands::documents::export_document,
            commands::documents::get_documents_status,
            // Clave y modelos de Gemini
            commands::gemini::save_gemini_key,
            commands::gemini::test_gemini_key,
            commands::gemini::list_gemini_models,
            commands::gemini::get_gemini_budget,
            commands::gemini::save_gemini_budget,
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
