//! Comandos expuestos al WebView.
//!
//! Se reparten en dos grupos segun a quien preguntan:
//!
//! - `radar`: lecturas resueltas por Rust contra PostgreSQL.
//! - `engine`: operaciones que necesitan el motor Python (grafo, LanceDB).

pub mod engine;
pub mod radar;
