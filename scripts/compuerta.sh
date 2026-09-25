#!/usr/bin/env bash
# Compuerta de SENTRA (R3, AUD2-022): falla si falla CUALQUIER paso.
#
# Cada paso guarda el código de salida real de su herramienta: sin tuberías
# que lo oculten. El hook .githooks/pre-commit la ejecuta completa en cada commit
# (activarlo una vez: `git config core.hooksPath .githooks`); a mano:
#
#   bash scripts/compuerta.sh                  # ruff, mypy, Python, tsc, node, cargo
#   CLIPPY=1 AUDIT=1 HUMO=1 bash scripts/compuerta.sh   # la completa: la del hook
#
# CLIPPY=1: clippy sin avisos. AUDIT=1: pip-audit y cargo audit (AUD2-021;
# consultan sus bases de vulnerabilidades en la red). HUMO=1: la prueba de humo
# del ejecutable real (AUD2-004; con SENTRA cerrada). PASOS="ruff mypy"
# limita los pasos por defecto (lo usan los tests de la compuerta).
set -u
cd "$(dirname "$0")/.." || exit 1
LOGS=$(mktemp -d)
fallo=0

paso() {
  local nombre=$1
  shift
  if "$@" > "$LOGS/$nombre.log" 2>&1; then
    echo "$nombre OK"
  else
    local rc=$?
    echo "$nombre FALLA (rc=$rc)"
    tail -n 25 "$LOGS/$nombre.log"
    fallo=1
  fi
}

quiere() { [ -z "${PASOS:-}" ] || [[ " $PASOS " == *" $1 "* ]]; }
opcional() { [ "${!1:-0}" = "1" ]; }

quiere ruff && paso ruff ruff check --no-cache -q
quiere mypy && paso mypy mypy
quiere python && paso python env PYTHONIOENCODING=utf-8 python -m unittest discover -s tests
quiere tsc && paso tsc bash -c 'cd ui && npx --no-install tsc --noEmit -p .'
quiere node && paso node bash -c 'cd ui && npm test --silent'
quiere cargo && paso cargo bash -c 'cd ui/src-tauri && cargo test'
opcional CLIPPY && paso clippy bash -c 'cd ui/src-tauri && cargo clippy --all-targets -q -- -D warnings'
opcional AUDIT && paso pip-audit pip-audit -r requirements.txt -r requirements-dev.txt
opcional AUDIT && paso cargo-audit bash -c 'cd ui/src-tauri && cargo audit'
opcional HUMO && paso humo env PYTHONIOENCODING=utf-8 python -m tests.humo_exe

rm -rf "$LOGS"
if [ "$fallo" = "0" ]; then echo "COMPUERTA OK"; else echo "COMPUERTA FALLA"; fi
exit "$fallo"
