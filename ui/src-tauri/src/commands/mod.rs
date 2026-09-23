//! Comandos expuestos al WebView.
//!
//! Se reparten en tres grupos segun a quien preguntan:
//!
//! - `radar`: lecturas resueltas por Rust contra PostgreSQL.
//! - `engine`: operaciones que necesitan el motor Python (grafo, LanceDB).
//! - `health`: estado agregado de las tres piezas.
//! - `mutations`: las escrituras, juntas para que la superficie con la
//!   que se cambia el estado del sistema sea facil de revisar.
//! - `settings`: configuracion y credenciales, delegadas al sidecar.
//! - `blueprint`: especificacion de proyecto, redactada por el motor.
//! - `architect`: plan de construccion, redactado por Gemini.

pub mod architect;
pub mod blueprint;
pub mod document;
pub mod engine;
pub mod health;
pub mod mutations;
pub mod radar;
pub mod settings;

#[cfg(test)]
mod contract_tests;
