//! Comandos expuestos al WebView.
//!
//! Se reparten en tres grupos segun a quien preguntan:
//!
//! - `radar`: lecturas resueltas por Rust contra PostgreSQL.
//! - `engine`: operaciones que necesitan el motor Python (grafo, LanceDB).
//! - `health`: estado agregado de las tres piezas.

pub mod engine;
pub mod health;
pub mod radar;
