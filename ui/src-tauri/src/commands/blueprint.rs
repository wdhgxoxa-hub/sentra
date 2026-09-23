//! Generador de especificaciones de proyecto (PRD).
//!
//! Rust hace de puente: lee el cluster de PostgreSQL, que es la fuente de
//! verdad, y se lo pasa al sidecar para que lo sintetice. El documento no se
//! guarda: se regenera a partir de la evidencia cada vez que se pide, asi que
//! nunca puede quedar desfasado respecto al cluster que describe.

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::commands::engine::{sidecar_url, with_token_pub};
use crate::commands::radar::cluster_por_clave;
use crate::db::{AppState, RadarError, RadarResult};

const TIMEOUT: std::time::Duration = std::time::Duration::from_secs(30);

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BlueprintPhase {
    pub name: String,
    pub items: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BlueprintQuote {
    pub quote: String,
    pub subreddit: String,
    pub author: String,
    pub url: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BlueprintDoc {
    pub product_name: String,
    pub one_liner: String,
    pub executive_summary: String,
    pub problem: String,
    pub solution: String,
    pub mvp: Vec<BlueprintPhase>,
    pub why_existing_fail: String,
    pub monetisation: String,
    pub evidence: Vec<BlueprintQuote>,
    /// Cuantas citas distintas sostienen el caso, que no es lo mismo que
    /// cuantas menciones hubo.
    pub distinct_quotes: i64,
    pub markdown: String,
    /// Fuente de los datos, en su propio campo para que la interfaz la
    /// muestre arriba del documento (AUD-009).
    pub source_notice: String,
    /// "demo", "reddit" o `None` si la ejecución no lo registró.
    pub data_source: Option<String>,
}

#[derive(Debug, Serialize)]
struct BlueprintBody {
    cluster: serde_json::Value,
    language: String,
}

/// Sintetiza la especificacion de un cluster.
#[tauri::command]
pub async fn generate_blueprint(
    state: State<'_, AppState>,
    cluster_key: String,
    language: String,
) -> RadarResult<BlueprintDoc> {
    let cluster = cluster_por_clave(&state.pool, &cluster_key)
        .await?
        .ok_or_else(|| {
            RadarError::Invalid(format!(
                "No hay ninguna oportunidad con la clave '{cluster_key}'"
            ))
        })?;

    let cluster_json = serde_json::to_value(&cluster).map_err(|err| {
        RadarError::Invalid(format!("No se pudo serializar la oportunidad: {err}"))
    })?;

    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/blueprint", sidecar_url()))
            .timeout(TIMEOUT)
            .json(&BlueprintBody {
                cluster: cluster_json,
                language,
            }),
    )
    .send()
    .await
    .map_err(|err| {
        if err.is_connect() {
            RadarError::Sidecar(format!(
                "El sidecar Python no responde en {}. La especificacion la \
                 redacta el motor, asi que sin el no se puede generar.",
                sidecar_url()
            ))
        } else {
            RadarError::Sidecar(format!("Fallo hablando con el sidecar: {err}"))
        }
    })?;

    if !response.status().is_success() {
        return Err(RadarError::Sidecar(format!(
            "El sidecar no pudo redactar la especificacion ({})",
            response.status()
        )));
    }

    response
        .json()
        .await
        .map_err(|err| RadarError::Sidecar(format!("Respuesta ilegible del sidecar: {err}")))
}
