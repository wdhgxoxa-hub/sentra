//! Motor de arquitectura (Gemini).
//!
//! Rust hace de puente, igual que con el blueprint: lee el cluster de
//! PostgreSQL y se lo pasa al sidecar, que es quien habla con Google.
//!
//! La diferencia esta en la respuesta. El plan lo escribe un modelo de
//! razonamiento y tarda, asi que el sidecar lo sirve por trozos y aqui se
//! reemiten al WebView segun llegan. Quien mira la pantalla ve el documento
//! escribirse en lugar de un reloj de arena.
//!
//! La clave de API nunca pasa por aqui: vive en el `.env` del sidecar y solo
//! se envia cuando se guarda.

use std::time::Duration;

use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

use crate::commands::engine::{sidecar_url, with_token_pub};
use crate::commands::radar::cluster_por_clave;
use crate::commands::settings::GeminiSummary;
use crate::db::{AppState, RadarError, RadarResult};

/// Canal por el que viaja el documento mientras se escribe.
pub const ARCHITECT_EVENT_CHANNEL: &str = "sentra:architect";

/// Un plan completo con codigo puede tardar varios minutos con un modelo de
/// razonamiento profundo. El limite esta para que un cuelgue no deje la
/// peticion abierta para siempre, no para cortar una respuesta normal.
const GENERATE_TIMEOUT: Duration = Duration::from_secs(600);
const SHORT_TIMEOUT: Duration = Duration::from_secs(60);

/// Llega anidado (`{ params: { apiKey, model } }`): Tauri solo traduce los
/// nombres de primer nivel, asi que el camelCase de los campos lo pone serde.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GeminiKeyParams {
    pub api_key: String,
    pub model: String,
}

#[derive(Debug, Serialize)]
struct GeminiBody {
    #[serde(rename = "apiKey")]
    api_key: String,
    model: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProbeResult {
    pub ok: bool,
    pub detail: String,
}

#[derive(Debug, Serialize)]
struct ArchitectBody {
    cluster: serde_json::Value,
    language: String,
}

/// Un trozo del documento segun llega.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ArchitectChunk {
    cluster_key: String,
    text: String,
    done: bool,
}

fn transport_error(err: reqwest::Error) -> RadarError {
    if err.is_connect() {
        RadarError::Sidecar(format!(
            "El sidecar Python no responde en {}. El motor de arquitectura \
             habla con Google desde ahi.",
            sidecar_url()
        ))
    } else if err.is_timeout() {
        RadarError::Sidecar(
            "El modelo tardo demasiado en responder. Prueba con gemini-2.5-flash \
             si no necesitas el razonamiento profundo."
                .into(),
        )
    } else {
        RadarError::Sidecar(format!("Fallo hablando con el sidecar: {err}"))
    }
}

/// Guarda la clave de Gemini en el `.env` del proyecto.
#[tauri::command]
pub async fn save_gemini_key(
    state: State<'_, AppState>,
    params: GeminiKeyParams,
) -> RadarResult<GeminiSummary> {
    if params.api_key.trim().is_empty() {
        return Err(RadarError::Invalid("La clave no puede estar vacia".into()));
    }

    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/gemini", sidecar_url()))
            .timeout(SHORT_TIMEOUT)
            .json(&GeminiBody {
                api_key: params.api_key,
                model: params.model,
            }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    if !response.status().is_success() {
        let detail = response.text().await.unwrap_or_default();
        return Err(RadarError::Sidecar(format!(
            "No se pudo guardar la clave: {detail}"
        )));
    }

    #[derive(Deserialize)]
    struct Envelope {
        gemini: GeminiSummary,
    }

    let envelope: Envelope = response.json().await.map_err(transport_error)?;
    Ok(envelope.gemini)
}

/// Comprueba contra Google que la clave guardada sirve.
#[tauri::command]
pub async fn test_gemini_key(state: State<'_, AppState>) -> RadarResult<ProbeResult> {
    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/gemini/test", sidecar_url()))
            .timeout(SHORT_TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;

    response.json().await.map_err(transport_error)
}

/// Genera el plan de arquitectura y lo emite por trozos.
///
/// Devuelve tambien el documento entero: quien invoca puede quedarse con el
/// resultado sin escuchar el canal, y la vista no depende de haber recibido
/// todos los eventos.
#[tauri::command]
pub async fn generate_architecture(
    app: AppHandle,
    state: State<'_, AppState>,
    cluster_key: String,
    language: String,
) -> RadarResult<String> {
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
            .post(format!("{}/api/architect/generate", sidecar_url()))
            .timeout(GENERATE_TIMEOUT)
            .json(&ArchitectBody {
                cluster: cluster_json,
                language,
            }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    let status = response.status();
    if !status.is_success() {
        let detail = response.text().await.unwrap_or_default();
        // 412 es el caso esperable: no hay clave guardada todavia.
        return Err(RadarError::Sidecar(if status.as_u16() == 412 {
            "No hay clave de Gemini guardada. Se configura en Ajustes.".into()
        } else {
            format!("El motor de arquitectura fallo ({status}): {detail}")
        }));
    }

    let mut stream = response.bytes_stream();
    let mut completo = String::new();
    // Un trozo de red puede cortar un caracter multibyte por la mitad. Los
    // bytes sueltos se guardan hasta que llegue el resto: convertirlos sin
    // esperar los pintaria como rombos, y el documento lleva acentos y
    // cajas de codigo.
    let mut pendiente: Vec<u8> = Vec::new();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(transport_error)?;
        pendiente.extend_from_slice(&chunk);

        let texto = match std::str::from_utf8(&pendiente) {
            Ok(completo) => {
                let s = completo.to_string();
                pendiente.clear();
                s
            }
            Err(err) => {
                let hasta = err.valid_up_to();
                let s = String::from_utf8_lossy(&pendiente[..hasta]).to_string();
                pendiente.drain(..hasta);
                s
            }
        };

        if texto.is_empty() {
            continue;
        }
        completo.push_str(&texto);

        let _ = app.emit(
            ARCHITECT_EVENT_CHANNEL,
            ArchitectChunk {
                cluster_key: cluster_key.clone(),
                text: texto,
                done: false,
            },
        );
    }

    let _ = app.emit(
        ARCHITECT_EVENT_CHANNEL,
        ArchitectChunk {
            cluster_key: cluster_key.clone(),
            text: String::new(),
            done: true,
        },
    );

    Ok(completo)
}
