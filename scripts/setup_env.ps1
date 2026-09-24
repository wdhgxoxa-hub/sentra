<#
.SYNOPSIS
    Crea el entorno de Python del motor de SENTRA e instala sus dependencias.

.DESCRIPTION
    La aplicación de escritorio lanza el sidecar con RIR_PYTHON o, si no está
    definida, con el intérprete de la .venv del proyecto (D-D). Nunca usa el
    python global: con él el motor arrancaba con otras versiones de las
    dependencias, o sin ellas. Este script deja esa .venv lista:

      1. Localiza Python 3.12 con el lanzador «py» (o el que se indique).
      2. Crea la venv (por defecto <proyecto>\.venv).
      3. Instala requirements.txt y, si se pide, requirements-dev.txt.
      4. Comprueba que el motor se importa con ese intérprete.

    Sale con código distinto de 0 en cuanto un paso falla.

.PARAMETER VenvPath
    Dónde crear la venv. Por defecto, .venv en la raíz del proyecto.

.PARAMETER Python
    Intérprete con el que crear la venv. Por defecto, «py -3.12».

.PARAMETER Dev
    Instala también requirements-dev.txt (tests, ruff, mypy).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1 -Dev
#>
[CmdletBinding()]
param(
    [string]$VenvPath,
    [string]$Python,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$Proyecto = Split-Path -Parent $PSScriptRoot
if (-not $VenvPath) { $VenvPath = Join-Path $Proyecto ".venv" }

function Paso([string]$Texto) { Write-Host "==> $Texto" -ForegroundColor Cyan }

function Ejecutar([string]$Programa, [string[]]$Argumentos) {
    & $Programa @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw "Falló: $Programa $($Argumentos -join ' ') (código $LASTEXITCODE)"
    }
}

try {
    Paso "Proyecto: $Proyecto"

    # 1. Intérprete base
    if ($Python) {
        $Base = @($Python)
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $Base = @("py", "-3.12")
    } else {
        throw "No se encontró el lanzador «py». Instala Python 3.12 o indica -Python <ruta a python.exe>."
    }
    $Version = & $Base[0] @($Base | Select-Object -Skip 1) -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if ($LASTEXITCODE -ne 0) { throw "El intérprete base no responde: $($Base -join ' ')" }
    if ($Version -ne "3.12") {
        throw "Se necesita Python 3.12 (el verificado); $($Base -join ' ') es $Version."
    }
    Paso "Python base: $($Base -join ' ') ($Version)"

    # 2. Venv
    $Interprete = Join-Path $VenvPath "Scripts\python.exe"
    if (Test-Path $Interprete) {
        Paso "Venv existente: $VenvPath"
    } else {
        Paso "Creando venv en $VenvPath"
        Ejecutar $Base[0] (@($Base | Select-Object -Skip 1) + @("-m", "venv", $VenvPath))
    }

    # 3. Dependencias
    $Archivos = @("requirements.txt")
    if ($Dev) { $Archivos += "requirements-dev.txt" }
    foreach ($Archivo in $Archivos) {
        Paso "Instalando $Archivo"
        Ejecutar $Interprete @("-m", "pip", "install", "--disable-pip-version-check",
                              "-r", (Join-Path $Proyecto $Archivo))
    }

    # 4. Comprobación: el motor se importa con este intérprete
    Paso "Comprobando que el motor se importa"
    Push-Location $Proyecto
    try {
        Ejecutar $Interprete @("-c", "import core.orchestration.sidecar_server; print('motor importable')")
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "Entorno listo: $Interprete" -ForegroundColor Green
    if ($VenvPath -ne (Join-Path $Proyecto ".venv")) {
        Write-Host "No es la .venv del proyecto: para que la aplicación lo use, define RIR_PYTHON=$Interprete"
    }
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
