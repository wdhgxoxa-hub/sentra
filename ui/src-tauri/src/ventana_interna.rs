//! El cierre que llega a la ventana interna de tao cierra la aplicacion (AUD2-027).
//!
//! tao crea en Windows una ventana de nivel superior, «Tao Thread Event
//! Target», que es VISIBLE a proposito (la necesita para recibir WM_PAINT; la
//! oculta un estilo transparente). Un WM_CLOSE dirigido a ella (taskkill sin
//! /F cuando la elige como principal, el Restart Manager de Windows, un gestor
//! de ventanas) la destruia con DefWindowProc: la app seguia abierta y, al
//! cerrarla despues, el proceso quedaba vivo sin ventana. Aqui se subclasifica
//! esa ventana: su WM_CLOSE pide la salida ordenada de la app, como la X. El
//! resto de mensajes sigue yendo a tao.

use std::sync::OnceLock;

use tauri::AppHandle;

/// WM_CLOSE de Win32.
pub const WM_CLOSE: u32 = 0x0010;
/// Clase de la ventana interna del bucle de eventos de tao.
pub const CLASE: &str = "Tao Thread Event Target";

/// Que hacer con un mensaje que llega a la ventana interna.
#[derive(Debug, PartialEq, Eq)]
pub enum Accion {
    /// Cerrar la aplicacion de forma ordenada (motor incluido).
    CerrarApp,
    /// Dejarlo pasar a tao.
    DeTao,
}

pub fn accion(mensaje: u32) -> Accion {
    if mensaje == WM_CLOSE {
        Accion::CerrarApp
    } else {
        Accion::DeTao
    }
}

pub fn es_la_ventana_interna(clase: &[u16]) -> bool {
    String::from_utf16_lossy(clase) == CLASE
}

static APP: OnceLock<AppHandle> = OnceLock::new();

/// Protege la ventana interna del hilo actual (el principal, desde `setup`).
/// Devuelve si la encontro y la subclasifico.
pub fn proteger(app: &AppHandle) -> bool {
    let _ = APP.set(app.clone());
    #[cfg(windows)]
    {
        win::proteger()
    }
    #[cfg(not(windows))]
    {
        false
    }
}

#[cfg(windows)]
mod win {
    use super::{accion, es_la_ventana_interna, Accion, APP};

    type Hwnd = isize;
    type Subclase = unsafe extern "system" fn(Hwnd, u32, usize, isize, usize, usize) -> isize;
    type Enumerar = unsafe extern "system" fn(Hwnd, isize) -> i32;

    const ID_SUBCLASE: usize = 0x5E27_0027;

    #[link(name = "user32")]
    extern "system" {
        fn EnumThreadWindows(hilo: u32, cada: Enumerar, dato: isize) -> i32;
        fn GetClassNameW(ventana: Hwnd, clase: *mut u16, max: i32) -> i32;
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentThreadId() -> u32;
    }

    #[link(name = "comctl32")]
    extern "system" {
        fn SetWindowSubclass(ventana: Hwnd, proc_: Subclase, id: usize, dato: usize) -> i32;
        fn DefSubclassProc(ventana: Hwnd, mensaje: u32, wparam: usize, lparam: isize) -> isize;
    }

    unsafe extern "system" fn subclase(
        ventana: Hwnd,
        mensaje: u32,
        wparam: usize,
        lparam: isize,
        _id: usize,
        _dato: usize,
    ) -> isize {
        if accion(mensaje) == Accion::CerrarApp {
            log::info!("WM_CLOSE en la ventana interna de tao: se cierra la aplicación");
            if let Some(app) = APP.get() {
                app.exit(0);
            }
            return 0;
        }
        DefSubclassProc(ventana, mensaje, wparam, lparam)
    }

    unsafe extern "system" fn cada(ventana: Hwnd, encontrada: isize) -> i32 {
        let mut clase = [0u16; 64];
        let largo = GetClassNameW(ventana, clase.as_mut_ptr(), clase.len() as i32);
        if largo > 0 && es_la_ventana_interna(&clase[..largo as usize]) {
            *(encontrada as *mut Hwnd) = ventana;
            return 0; // basta con la primera
        }
        1
    }

    pub fn proteger() -> bool {
        let mut encontrada: Hwnd = 0;
        // SAFETY: EnumThreadWindows llama a `cada` en este mismo hilo antes de
        // volver, y `encontrada` vive hasta entonces; la subclase solo lee
        // estado global inmutable (APP) y delega el resto en DefSubclassProc.
        unsafe {
            EnumThreadWindows(GetCurrentThreadId(), cada, &mut encontrada as *mut Hwnd as isize);
            encontrada != 0 && SetWindowSubclass(encontrada, subclase, ID_SUBCLASE, 0) != 0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn un_wm_close_a_la_ventana_interna_cierra_la_aplicacion() {
        assert_eq!(accion(WM_CLOSE), Accion::CerrarApp);
    }

    #[test]
    fn el_resto_de_mensajes_siguen_siendo_de_tao() {
        for mensaje in [0x000F_u32, 0x0002, 0x0400, 0x0113] {
            assert_eq!(accion(mensaje), Accion::DeTao, "mensaje {mensaje:#x}");
        }
    }

    #[test]
    fn reconoce_la_clase_de_la_ventana_interna() {
        let clase: Vec<u16> = "Tao Thread Event Target".encode_utf16().collect();
        assert!(es_la_ventana_interna(&clase));
        let otra: Vec<u16> = "Tauri Window".encode_utf16().collect();
        assert!(!es_la_ventana_interna(&otra));
    }
}
