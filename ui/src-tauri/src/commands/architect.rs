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

use crate::commands::engine::{sidecar_url, transport_error, with_token_pub};
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
///
/// `done` solo es `true` cuando el motor confirma el plan completo; si algo
/// falla, el ultimo evento lleva `done: false` y el `error` tipado (AUD-020).
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ArchitectChunk {
    pub(crate) cluster_key: String,
    pub(crate) text: String,
    pub(crate) done: bool,
    pub(crate) error: Option<ArchitectFailure>,
}

/// Por que el plan no se dio por terminado. `code` es estable y lo traduce
/// la interfaz; `missing`, las secciones exigidas que no llegaron.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ArchitectFailure {
    pub(crate) code: String,
    pub(crate) detail: String,
    pub(crate) missing: Vec<String>,
}

/// Lo que manda el sidecar: una linea JSON por evento.
#[derive(Debug, PartialEq, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
enum EventoDelMotor {
    Chunk {
        text: String,
    },
    Done,
    Error {
        code: String,
        detail: String,
        #[serde(default)]
        missing: Vec<String>,
    },
}

/// El sidecar mando algo que no es una linea JSON del protocolo.
const CODIGO_PROTOCOLO: &str = "architect_protocol";

/// La conexion termino sin `done` ni `error`.
const CODIGO_INTERRUMPIDO: &str = "architect_interrupted";

/// No hay clave de Gemini guardada (el sidecar responde 412).
const CODIGO_SIN_CLAVE: &str = "gemini_not_configured";

/// Añade `nuevo` al buffer y devuelve los eventos de las lineas completas.
///
/// Se corta por `\n`, que en UTF-8 nunca forma parte de un caracter
/// multibyte: una linea completa es siempre texto valido, y lo que queda en
/// `pendiente` espera al siguiente trozo.
fn eventos_completos(
    pendiente: &mut Vec<u8>,
    nuevo: &[u8],
) -> Result<Vec<EventoDelMotor>, ArchitectFailure> {
    pendiente.extend_from_slice(nuevo);
    let mut eventos = Vec::new();
    while let Some(fin) = pendiente.iter().position(|&b| b == b'\n') {
        let linea: Vec<u8> = pendiente.drain(..=fin).collect();
        let linea = &linea[..fin];
        if linea.iter().all(u8::is_ascii_whitespace) {
            continue;
        }
        let evento = serde_json::from_slice(linea).map_err(|err| ArchitectFailure {
            code: CODIGO_PROTOCOLO.into(),
            detail: format!("Respuesta del motor ilegible: {err}"),
            missing: vec![],
        })?;
        eventos.push(evento);
    }
    Ok(eventos)
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
    let cluster = cluster_por_clave(&state.db.pool()?, &cluster_key)
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
        return Err(if status.as_u16() == 412 {
            RadarError::Motor {
                code: CODIGO_SIN_CLAVE.into(),
                detail,
            }
        } else {
            RadarError::Sidecar(format!("El motor de arquitectura fallo ({status}): {detail}"))
        });
    }

    let mut stream = response.bytes_stream();
    let mut completo = String::new();
    // Bytes de una linea que todavia no ha terminado de llegar: un trozo de
    // red puede cortarla, e incluso cortar un caracter multibyte por la mitad.
    let mut pendiente: Vec<u8> = Vec::new();
    let mut desenlace: Option<Result<(), ArchitectFailure>> = None;

    'lectura: while let Some(trozo) = stream.next().await {
        let trozo = trozo.map_err(transport_error)?;
        let eventos = match eventos_completos(&mut pendiente, &trozo) {
            Ok(eventos) => eventos,
            Err(fallo) => {
                desenlace = Some(Err(fallo));
                break;
            }
        };
        for evento in eventos {
            match evento {
                EventoDelMotor::Chunk { text } => {
                    completo.push_str(&text);
                    let _ = app.emit(
                        ARCHITECT_EVENT_CHANNEL,
                        ArchitectChunk {
                            cluster_key: cluster_key.clone(),
                            text,
                            done: false,
                            error: None,
                        },
                    );
                }
                EventoDelMotor::Done => {
                    desenlace = Some(Ok(()));
                    break 'lectura;
                }
                EventoDelMotor::Error {
                    code,
                    detail,
                    missing,
                } => {
                    desenlace = Some(Err(ArchitectFailure {
                        code,
                        detail,
                        missing,
                    }));
                    break 'lectura;
                }
            }
        }
    }

    // Sin `done` ni `error` la conexion se corto a medias: el documento no
    // esta completo aunque tenga texto.
    let desenlace = desenlace.unwrap_or_else(|| {
        Err(ArchitectFailure {
            code: CODIGO_INTERRUMPIDO.into(),
            detail: "La respuesta del motor se corto antes de terminar.".into(),
            missing: vec![],
        })
    });

    match desenlace {
        Ok(()) => {
            let _ = app.emit(
                ARCHITECT_EVENT_CHANNEL,
                ArchitectChunk {
                    cluster_key: cluster_key.clone(),
                    text: String::new(),
                    done: true,
                    error: None,
                },
            );
            Ok(completo)
        }
        Err(fallo) => {
            let error = RadarError::Motor {
                code: fallo.code.clone(),
                detail: fallo.detail.clone(),
            };
            let _ = app.emit(
                ARCHITECT_EVENT_CHANNEL,
                ArchitectChunk {
                    cluster_key: cluster_key.clone(),
                    text: String::new(),
                    done: false,
                    error: Some(fallo),
                },
            );
            Err(error)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fallo(code: &str) -> ArchitectFailure {
        ArchitectFailure {
            code: code.into(),
            detail: String::new(),
            missing: vec![],
        }
    }

    #[test]
    fn una_linea_partida_entre_trozos_solo_sale_al_completarse() {
        let mut pendiente = Vec::new();
        let linea = "{\"type\":\"chunk\",\"text\":\"Lógica\"}\n".as_bytes();
        // Corte en mitad de la «ó», que ocupa dos bytes.
        let corte = linea.iter().position(|&b| b == 0xC3).unwrap() + 1;
        assert_eq!(eventos_completos(&mut pendiente, &linea[..corte]), Ok(vec![]));
        assert_eq!(
            eventos_completos(&mut pendiente, &linea[corte..]),
            Ok(vec![EventoDelMotor::Chunk { text: "Lógica".into() }])
        );
        assert!(pendiente.is_empty());
    }

    #[test]
    fn varias_lineas_en_un_trozo_salen_en_orden() {
        let mut pendiente = Vec::new();
        let trozo = b"{\"type\":\"chunk\",\"text\":\"a\"}\n{\"type\":\"done\"}\n";
        assert_eq!(
            eventos_completos(&mut pendiente, trozo),
            Ok(vec![
                EventoDelMotor::Chunk { text: "a".into() },
                EventoDelMotor::Done
            ])
        );
    }

    #[test]
    fn el_error_trae_codigo_detalle_y_secciones_ausentes() {
        let mut pendiente = Vec::new();
        let trozo = "{\"type\":\"error\",\"code\":\"gemini_incomplete\",\"detail\":\"Faltan\",\"missing\":[\"Hoja de ruta\"]}\n";
        assert_eq!(
            eventos_completos(&mut pendiente, trozo.as_bytes()),
            Ok(vec![EventoDelMotor::Error {
                code: "gemini_incomplete".into(),
                detail: "Faltan".into(),
                missing: vec!["Hoja de ruta".into()],
            }])
        );
    }

    #[test]
    fn una_linea_ilegible_es_un_fallo_de_protocolo() {
        let mut pendiente = Vec::new();
        let resultado = eventos_completos(&mut pendiente, b"# FASE 1 en texto plano\n");
        assert_eq!(
            resultado.map_err(|f| f.code),
            Err(fallo(CODIGO_PROTOCOLO).code)
        );
    }
}
