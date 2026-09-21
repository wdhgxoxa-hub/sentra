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

pub mod engine;
pub mod health;
pub mod mutations;
pub mod radar;
pub mod settings;
