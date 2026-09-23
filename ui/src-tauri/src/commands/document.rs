//! Exportación del documento a PDF (AUD-008).
//!
//! El reparto es el de siempre: Rust lee la oportunidad de PostgreSQL, el
//! sidecar redacta el PDF (ReportLab) y devuelve sus bytes, y Rust pregunta
//! dónde guardarlo con el diálogo nativo y escribe el archivo. La interfaz
//! solo dispara la acción y muestra el resultado.

use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, State};
use tauri_plugin_dialog::DialogExt;

use crate::commands::engine::{sidecar_url, transport_error, with_token_pub};
use crate::commands::radar::cluster_por_clave;
use crate::db::{AppState, RadarError, RadarResult};

/// Un documento largo con el plan de arquitectura tarda algo más que el
/// blueprint, pero sigue siendo cuestión de segundos.
const TIMEOUT: Duration = Duration::from_secs(60);

/// Cuerpo de `POST /api/document/pdf` (`DocumentRequest` en el sidecar).
#[derive(Debug, Serialize)]
pub struct DocumentBody {
    pub cluster: serde_json::Value,
    pub language: String,
    pub architecture: Option<String>,
}

/// Un PDF empieza siempre por `%PDF`. Guardar otra cosa con extensión .pdf
/// dejaría en disco un archivo roto con apariencia de documento.
pub fn comprobar_pdf(bytes: &[u8]) -> RadarResult<()> {
    if bytes.starts_with(b"%PDF") {
        Ok(())
    } else {
        Err(RadarError::Sidecar(
            "El motor no devolvió un PDF válido".into(),
        ))
    }
}

/// Nombre propuesto en el diálogo: la etiqueta de la oportunidad sin los
/// caracteres que Windows no admite en un nombre de archivo.
pub fn nombre_sugerido(etiqueta: &str) -> String {
    const PROHIBIDOS: [char; 9] = ['<', '>', ':', '"', '/', '\\', '|', '?', '*'];
    let limpio: String = etiqueta
        .chars()
        .filter(|c| !PROHIBIDOS.contains(c) && !c.is_control())
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if limpio.is_empty() {
        return "SENTRA.pdf".into();
    }
    let corto: String = limpio.chars().take(76).collect();
    format!("SENTRA - {}.pdf", corto.trim_end())
}

/// Genera el PDF de una oportunidad y lo guarda donde elija quien exporta.
///
/// Devuelve la ruta guardada, o `None` si se canceló el diálogo: cancelar no
/// es un error.
#[tauri::command]
pub async fn export_pdf(
    app: AppHandle,
    state: State<'_, AppState>,
    cluster_key: String,
    language: String,
    architecture: Option<String>,
) -> RadarResult<Option<String>> {
    let cluster = cluster_por_clave(&state.db.pool()?, &cluster_key)
        .await?
        .ok_or_else(|| {
            RadarError::Invalid(format!(
                "No hay ninguna oportunidad con la clave '{cluster_key}'"
            ))
        })?;
    let nombre = nombre_sugerido(&cluster.label);
    let cluster_json = serde_json::to_value(&cluster).map_err(|err| {
        RadarError::Invalid(format!("No se pudo serializar la oportunidad: {err}"))
    })?;

    let response = with_token_pub(
        state
            .http
            .post(format!("{}/api/document/pdf", sidecar_url()))
            .timeout(TIMEOUT)
            .json(&DocumentBody {
                cluster: cluster_json,
                language,
                architecture,
            }),
    )
    .send()
    .await
    .map_err(transport_error)?;

    let status = response.status();
    if !status.is_success() {
        return Err(RadarError::Sidecar(format!(
            "El motor no pudo generar el PDF ({status})"
        )));
    }
    let bytes = response
        .bytes()
        .await
        .map_err(|err| RadarError::Sidecar(format!("Respuesta ilegible del sidecar: {err}")))?;
    comprobar_pdf(&bytes)?;

    // El diálogo es bloqueante: se abre fuera del hilo del runtime.
    let ruta = tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .add_filter("PDF", &["pdf"])
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
        .map_err(|err| RadarError::Archivo(format!("No se pudo escribir el PDF: {err}")))?;
    Ok(Some(ruta.display().to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn solo_se_guarda_lo_que_es_un_pdf() {
        assert!(comprobar_pdf(b"%PDF-1.4\n...").is_ok());
        assert!(comprobar_pdf(b"<html>error</html>").is_err());
        assert!(comprobar_pdf(b"").is_err());
    }

    #[test]
    fn el_nombre_sugerido_es_valido_en_windows() {
        let nombre = nombre_sugerido("Facturación: ¿manual? <rota>|\"x\"/y\\z*");
        assert!(nombre.ends_with(".pdf"));
        assert!(!nombre.contains(['<', '>', ':', '"', '/', '\\', '|', '?', '*']));
        assert!(nombre.contains("Facturación"));
    }

    #[test]
    fn un_nombre_vacio_o_enorme_no_rompe_el_dialogo() {
        assert_eq!(nombre_sugerido("   "), "SENTRA.pdf");
        assert!(nombre_sugerido(&"a".repeat(500)).chars().count() <= 90);
    }

    #[test]
    fn el_cuerpo_para_el_sidecar_tiene_la_forma_del_modelo_pydantic() {
        let cuerpo = serde_json::to_value(DocumentBody {
            cluster: serde_json::json!({"clusterKey": "k"}),
            language: "es".into(),
            architecture: None,
        })
        .unwrap();
        assert_eq!(cuerpo["language"], "es");
        assert!(cuerpo["architecture"].is_null());
        assert_eq!(cuerpo["cluster"]["clusterKey"], "k");
    }
}
