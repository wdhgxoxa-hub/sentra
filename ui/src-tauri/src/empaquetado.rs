// Empaquetado del código del motor (AUD2-003, DP1 B).
//
// Lo comparten build.rs (con `include!`) y la aplicación: build.rs elige los
// ficheros del motor, calcula su huella y los empaqueta dentro del
// ejecutable; la aplicación los desempaqueta en una carpeta versionada y
// lanza el motor desde allí. La huella es la misma función que
// `core.rutas.huella` en Python: FNV-1a de 64 bits sobre
// «ruta\0longitud\0contenido» por ruta ordenada.
//
// Solo biblioteca estándar: build.rs no puede depender de crates del proyecto.

/// FNV-1a de 64 bits en hexadecimal (16 caracteres).
pub fn fnv1a64(datos: &[u8]) -> String {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for byte in datos {
        h ^= u64::from(*byte);
        h = h.wrapping_mul(0x0000_0100_0000_01b3);
    }
    format!("{h:016x}")
}

/// Huella de un conjunto de ficheros (ruta relativa con `/`, contenido).
pub fn huella(ficheros: &[(String, Vec<u8>)]) -> String {
    let mut ordenados: Vec<&(String, Vec<u8>)> = ficheros.iter().collect();
    ordenados.sort();
    let mut partes = Vec::new();
    for (ruta, contenido) in ordenados {
        partes.extend_from_slice(ruta.as_bytes());
        partes.push(0);
        partes.extend_from_slice(contenido.len().to_string().as_bytes());
        partes.push(0);
        partes.extend_from_slice(contenido);
    }
    fnv1a64(&partes)
}

/// Paquete: por fichero, u32 LE longitud de la ruta, la ruta, u64 LE
/// longitud del contenido y el contenido.
pub fn empaquetar(ficheros: &[(String, Vec<u8>)]) -> Vec<u8> {
    let mut paquete = Vec::new();
    for (ruta, contenido) in ficheros {
        let largo_ruta = u32::try_from(ruta.len()).expect("ruta demasiado larga");
        paquete.extend_from_slice(&largo_ruta.to_le_bytes());
        paquete.extend_from_slice(ruta.as_bytes());
        paquete.extend_from_slice(&(contenido.len() as u64).to_le_bytes());
        paquete.extend_from_slice(contenido);
    }
    paquete
}

/// Lo contrario de `empaquetar`; `None` si el paquete está truncado.
pub fn desempaquetar(paquete: &[u8]) -> Option<Vec<(String, Vec<u8>)>> {
    fn tomar<'a>(datos: &'a [u8], i: &mut usize, n: usize) -> Option<&'a [u8]> {
        let trozo = datos.get(*i..i.checked_add(n)?)?;
        *i += n;
        Some(trozo)
    }
    let mut ficheros = Vec::new();
    let mut i = 0;
    while i < paquete.len() {
        let largo_ruta = u32::from_le_bytes(tomar(paquete, &mut i, 4)?.try_into().ok()?) as usize;
        let ruta = String::from_utf8(tomar(paquete, &mut i, largo_ruta)?.to_vec()).ok()?;
        let largo = usize::try_from(u64::from_le_bytes(tomar(paquete, &mut i, 8)?.try_into().ok()?)).ok()?;
        ficheros.push((ruta, tomar(paquete, &mut i, largo)?.to_vec()));
    }
    Some(ficheros)
}

/// Ficheros del motor bajo la raíz del proyecto: `core/**` (sin
/// `__pycache__` ni ficheros que empiezan por punto), `sql/migrations/*` y
/// `scripts/{__init__,migrate}.py`. Rutas relativas con `/`, ordenadas.
pub fn ficheros_del_motor(raiz: &std::path::Path) -> std::io::Result<Vec<(String, Vec<u8>)>> {
    fn recorrer(raiz: &std::path::Path, dir: &std::path::Path, salida: &mut Vec<(String, Vec<u8>)>, recursivo: bool)
        -> std::io::Result<()> {
        for entrada in std::fs::read_dir(dir)? {
            let ruta = entrada?.path();
            let nombre = ruta.file_name().and_then(|n| n.to_str()).unwrap_or_default();
            if nombre.starts_with('.') || nombre == "__pycache__" {
                continue;
            }
            if ruta.is_dir() {
                if recursivo {
                    recorrer(raiz, &ruta, salida, true)?;
                }
            } else {
                let relativa = ruta.strip_prefix(raiz).expect("dentro de la raíz")
                    .components().map(|c| c.as_os_str().to_string_lossy().into_owned())
                    .collect::<Vec<_>>().join("/");
                salida.push((relativa, std::fs::read(&ruta)?));
            }
        }
        Ok(())
    }
    let mut ficheros = Vec::new();
    recorrer(raiz, &raiz.join("core"), &mut ficheros, true)?;
    recorrer(raiz, &raiz.join("sql").join("migrations"), &mut ficheros, false)?;
    for script in ["__init__.py", "migrate.py"] {
        let ruta = raiz.join("scripts").join(script);
        ficheros.push((format!("scripts/{script}"), std::fs::read(ruta)?));
    }
    ficheros.sort();
    Ok(ficheros)
}
