//! Comandos expuestos al WebView, repartidos segun a quien preguntan:
//!
//! - `engine`: conexion con el motor Python (busqueda, sondas, SSE).
//! - `documents`: dossier y plan de un veredicto (PDF o Markdown).
//! - `health`: estado agregado de las tres piezas.
//! - `judge`: Top 6 del juez y feed de evidencia, delegados al sidecar.
//! - `mutations`: las escrituras (cancelar un escaneo), juntas para que la
//!   superficie con la que se cambia el estado sea facil de revisar.
//! - `palabras`: palabras clave propuestas para el asistente de escaneo.
//! - `settings`: configuracion, delegada al sidecar.
//! - `gemini`: clave y modelos de Gemini.
//! - `sources`: fuentes multifuente (estado, credenciales, escaneo), delegadas al sidecar.

pub mod documents;
pub mod engine;
pub mod gemini;
pub mod health;
pub mod judge;
pub mod mutations;
pub mod palabras;
pub mod settings;
pub mod sources;

#[cfg(test)]
mod contract_returns_tests;
#[cfg(test)]
mod contract_tests;
