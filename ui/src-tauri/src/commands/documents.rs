//! Dossier y plan de construcción de un veredicto (Fase E).
//!
//! El sidecar compone el documento (`POST /api/documents/{kind}`) y devuelve
//! sus bytes en PDF o Markdown; Rust pregunta dónde guardarlo con el diálogo
//! nativo y escribe el archivo. La interfaz solo dispara la acción y muestra
//! el resultado, con las llamadas al modelo que costó.

use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, State};
use tauri_plugin_dialog::DialogExt;

use crate::commands::engine::{como_json, rechazo, sidecar_url, transport_error, with_token_pub};
use crate::db::{AppState, RadarError, RadarResult};

/// Una llamada al modelo de documentos puede tardar hasta 240 s
/// (DOC_TIMEOUT_MS) y, si la respuesta se corta, se parte en dos mitades:
/// hasta tres llamadas seguidas, más la composición del PDF.
const TIMEOUT: Duration = Duration::from_secs(15 * 60);

/// El estado solo mira el disco del motor.
const ESTADO_TIMEOUT: Duration = Duration::from_secs(30);

const TIPOS: [&str; 2] = ["dossier", "plan"];
const FORMATOS: [&str; 2] = ["pdf", "md"];

/// Lo que pide la interfaz: `ipc.exportDocument(params)`.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportDocumentParams {
    pub verdict_id: String,
    pub kind: String,
    pub format: String,
    pub language: String,
    #[serde(default)]
    pub force: bool,
}

/// Cuerpo de `POST /api/documents/{kind}` (`DocumentRequest` en el sidecar).
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct DocumentBody {
    verdict_id: String,
    format: String,
    language: String,
    force: bool,
}

/// Documento guardado: dónde y cuántas llamadas al modelo costó (0 si se
/// reutilizó lo ya generado; `None` si el motor no lo dijo).
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportedDocument {
    pub path: String,
    pub llm_calls: Option<u32>,
}

/// El tipo va en la URL y el formato decide el filtro del diálogo: solo los
/// que existen.
pub(crate) fn validar(params: &ExportDocumentParams) -> RadarResult<()> {
    if !TIPOS.contains(&params.kind.as_str()) {
        return Err(RadarError::Invalid(format!("Tipo de documento desconocido: {}", params.kind)));
    }
    if !FORMATOS.contains(&params.format.as_str()) {
        return Err(RadarError::Invalid(format!("Formato desconocido: {}", params.format)));
    }
    Ok(())
}

/// Lo que se guarda tiene que ser lo que dice su extensión: un PDF empieza
/// por `%PDF` y un Markdown es texto UTF-8 no vacío.
pub(crate) fn comprobar_contenido(formato: &str, bytes: &[u8]) -> RadarResult<()> {
    let valido = if formato == "pdf" {
        bytes.starts_with(b"%PDF")
    } else {
        !bytes.is_empty() && std::str::from_utf8(bytes).is_ok()
    };
    if valido {
        Ok(())
    } else {
        Err(RadarError::Sidecar(format!("El motor no devolvió un {formato} válido")))
    }
}

/// `%XX` → byte. `None` si la secuencia está rota o el resultado no es UTF-8.
fn decodificar_porcentaje(texto: &str) -> Option<String> {
    let entrada = texto.as_bytes();
    let mut salida = Vec::with_capacity(entrada.len());
    let mut i = 0;
    while i < entrada.len() {
        if entrada[i] == b'%' {
            let hex = std::str::from_utf8(entrada.get(i + 1..i + 3)?).ok()?;
            salida.push(u8::from_str_radix(hex, 16).ok()?);
            i += 3;
        } else {
            salida.push(entrada[i]);
            i += 1;
        }
    }
    String::from_utf8(salida).ok()
}

/// Nombre propuesto en el diálogo: el que sugiere el motor (codificado en
/// porcentaje), sin los caracteres que Windows no admite ni separadores de
/// ruta, y siempre con la extensión del formato.
pub(crate) fn nombre_sugerido(cabecera: Option<&str>, formato: &str) -> String {
    const PROHIBIDOS: [char; 9] = ['<', '>', ':', '"', '/', '\\', '|', '?', '*'];
    let limpio: String = cabecera
        .and_then(decodificar_porcentaje)
        .unwrap_or_default()
        .chars()
        .filter(|c| !PROHIBIDOS.contains(c) && !c.is_control())
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let limpio = limpio.trim_start_matches('.').trim_end();
    let extension = format!(".{formato}");
    if limpio.is_empty() || limpio == extension {
        return format!("SENTRA{extension}");
    }
    let corto: String = limpio.chars().take(120).collect();
    if corto.ends_with(&extension) {
        corto
    } else {
        format!("{corto}{extension}")
    }
}

/// Llamadas al modelo que dice la cabecera del motor.
pub(crate) fn llamadas(cabecera: Option<&str>) -> Option<u32> {
    cabecera?.trim().parse().ok()
}

/// Genera el documento de un veredicto y lo guarda donde elija quien exporta.
///
/// Devuelve `None` si se canceló el diálogo: cancelar no es un error.
#[tauri::command]
pub async fn export_document(
    app: AppHandle,
    state: State<'_, AppState>,
    params: ExportDocumentParams,
) -> RadarResult<Option<ExportedDocument>> {
    validar(&params)?;
    let url = format!("{}/api/documents/{}", sidecar_url(), params.kind);
    let formato = params.format.clone();
    let response = with_token_pub(state.http.post(url).timeout(TIMEOUT).json(&DocumentBody {
        verdict_id: params.verdict_id,
        format: params.format,
        language: params.language,
        force: params.force,
    }))
    .send()
    .await
    .map_err(transport_error)?;

    let status = response.status();
    if !status.is_success() {
        let cuerpo = response.text().await.unwrap_or_default();
        return Err(rechazo("No se pudo generar el documento", &status.to_string(), &cuerpo));
    }
    let cabecera = |nombre: &str| {
        response.headers().get(nombre).and_then(|v| v.to_str().ok()).map(str::to_string)
    };
    let nombre = nombre_sugerido(cabecera("x-sentra-file-name").as_deref(), &formato);
    let llamadas_al_modelo = llamadas(cabecera("x-sentra-llm-calls").as_deref());
    let bytes = response
        .bytes()
        .await
        .map_err(|err| RadarError::Sidecar(format!("Respuesta ilegible del sidecar: {err}")))?;
    comprobar_contenido(&formato, &bytes)?;

    let (filtro, extension) = if formato == "pdf" { ("PDF", "pdf") } else { ("Markdown", "md") };
    // El diálogo es bloqueante: se abre fuera del hilo del runtime.
    let ruta = tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .add_filter(filtro, &[extension])
            .set_file_name(nombre)
            .blocking_save_file()
    })
    .await
    .map_err(|err| RadarError::Archivo(format!("El diálogo de guardado falló: {err}")))?;

    let Some(ruta) = ruta else {
        return Ok(None);
    };
    let ruta = ruta
        .into_path()
        .map_err(|err| RadarError::Archivo(format!("Ruta de guardado no válida: {err}")))?;
    std::fs::write(&ruta, &bytes)
        .map_err(|err| RadarError::Archivo(format!("No se pudo escribir el documento: {err}")))?;
    Ok(Some(ExportedDocument {
        path: ruta.display().to_string(),
        llm_calls: llamadas_al_modelo,
    }))
}

/// URL del estado de los documentos de un veredicto, con el id codificado.
fn url_del_estado(base: &str, verdict_id: &str) -> String {
    let ruta = format!("{base}/api/documents/status");
    match reqwest::Url::parse(&ruta) {
        Ok(mut url) => {
            url.query_pairs_mut().append_pair("verdictId", verdict_id);
            url.to_string()
        }
        Err(_) => ruta,
    }
}

/// Qué documentos de un veredicto ya están guardados (Fase 2): se abren sin
/// gastar. El motor no llama a nadie para contestarlo.
#[tauri::command]
pub async fn get_documents_status(
    state: State<'_, AppState>,
    verdict_id: String,
) -> RadarResult<serde_json::Value> {
    let response = with_token_pub(
        state.http.get(url_del_estado(&sidecar_url(), &verdict_id)).timeout(ESTADO_TIMEOUT),
    )
    .send()
    .await
    .map_err(transport_error)?;
    como_json(response, "No se pudo leer el estado de los documentos").await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_estado_pide_el_veredicto_codificado() {
        assert_eq!(
            url_del_estado("http://x", "11111111-1111-1111-1111-111111111111"),
            "http://x/api/documents/status?verdictId=11111111-1111-1111-1111-111111111111"
        );
        assert_eq!(url_del_estado("http://x", "a b&c"), "http://x/api/documents/status?verdictId=a+b%26c");
    }

    fn params(kind: &str, format: &str) -> ExportDocumentParams {
        ExportDocumentParams {
            verdict_id: "v".into(),
            kind: kind.into(),
            format: format.into(),
            language: "es".into(),
            force: false,
        }
    }

    #[test]
    fn solo_tipos_y_formatos_que_existen() {
        assert!(validar(&params("dossier", "pdf")).is_ok());
        assert!(validar(&params("plan", "md")).is_ok());
        for (kind, format) in [("informe", "pdf"), ("../health", "pdf"), ("dossier", "docx")] {
            let error = validar(&params(kind, format)).unwrap_err();
            assert_eq!(error.code(), "invalid_input", "{kind}/{format}");
        }
    }

    #[test]
    fn solo_se_guarda_lo_que_dice_la_extension() {
        assert!(comprobar_contenido("pdf", b"%PDF-1.4\n...").is_ok());
        assert!(comprobar_contenido("pdf", b"# Dossier").is_err());
        assert!(comprobar_contenido("md", "# Dossier — ñ".as_bytes()).is_ok());
        assert!(comprobar_contenido("md", b"").is_err());
        assert!(comprobar_contenido("md", &[0xff, 0xfe]).is_err());
    }

    #[test]
    fn el_nombre_del_motor_se_decodifica_y_se_limpia() {
        let nombre = nombre_sugerido(Some("SENTRA%20-%20Dossier%20%C2%B7%20facturaci%C3%B3n.pdf"), "pdf");
        assert_eq!(nombre, "SENTRA - Dossier · facturación.pdf");
        let hostil = nombre_sugerido(Some("..%5C..%2Fwin%3A%2A.md"), "md");
        assert!(!hostil.contains(['<', '>', ':', '"', '/', '\\', '|', '?', '*']), "{hostil}");
        assert!(hostil.ends_with(".md"));
    }

    #[test]
    fn sin_nombre_valido_se_propone_uno_propio_con_su_extension() {
        assert_eq!(nombre_sugerido(None, "pdf"), "SENTRA.pdf");
        assert_eq!(nombre_sugerido(Some("%ZZroto"), "md"), "SENTRA.md");
        assert_eq!(nombre_sugerido(Some("%FF"), "md"), "SENTRA.md");
        assert_eq!(nombre_sugerido(Some("Dossier.pdf"), "md"), "Dossier.pdf.md");
    }

    #[test]
    fn las_llamadas_son_las_que_dice_el_motor_o_ninguna_cifra() {
        assert_eq!(llamadas(Some("1")), Some(1));
        assert_eq!(llamadas(Some("0")), Some(0));
        assert_eq!(llamadas(Some("x")), None);
        assert_eq!(llamadas(None), None);
    }

    #[test]
    fn el_cuerpo_para_el_sidecar_tiene_la_forma_del_modelo_pydantic() {
        let cuerpo = serde_json::to_value(DocumentBody {
            verdict_id: "v".into(),
            format: "pdf".into(),
            language: "en".into(),
            force: true,
        })
        .unwrap();
        assert_eq!(
            cuerpo,
            serde_json::json!({"verdictId": "v", "format": "pdf", "language": "en", "force": true})
        );
    }
}
