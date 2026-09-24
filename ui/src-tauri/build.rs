// Empaqueta el código del motor Python dentro del ejecutable (AUD2-003, DP1 B)
// y exporta su huella en SENTRA_HUELLA_MOTOR. La interfaz lo desempaqueta en
// una carpeta versionada y lanza el motor desde allí: la release deja de
// depender de la rama que haya en el repositorio.

include!("src/empaquetado.rs");

fn main() {
    let raiz = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..");
    let raiz = raiz.canonicalize().expect("raíz del proyecto");
    let ficheros = ficheros_del_motor(&raiz).expect("no se pudo leer el código del motor");
    let salida = std::path::PathBuf::from(std::env::var("OUT_DIR").expect("OUT_DIR"));
    std::fs::write(salida.join("motor.bin"), empaquetar(&ficheros)).expect("escribir motor.bin");
    println!("cargo:rustc-env=SENTRA_HUELLA_MOTOR={}", huella(&ficheros));
    for vigilado in ["core", "sql/migrations", "scripts/__init__.py", "scripts/migrate.py"] {
        println!("cargo:rerun-if-changed={}", raiz.join(vigilado).display());
    }
    tauri_build::build()
}
