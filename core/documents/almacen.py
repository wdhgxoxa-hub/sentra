"""
Almacén de documentos generados (Fase 1, decisión de Walter)
============================================================

Un documento generado con Gemini cuesta una llamada y no puede perderse: el
25-09 un dossier se generó, se canceló el diálogo de guardar, se cerró la app
y el texto, que solo vivía en memoria, se perdió. El motor guarda cada
documento compuesto aquí (un JSON por veredicto, documento, idioma, modelo y
forzado) antes de responder, y lo vuelve a exportar desde aquí sin llamar al
modelo, aunque la app se haya cerrado. La carpeta es
%LOCALAPPDATA%\\SENTRA\\documentos (core.rutas.ruta_documentos).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .model import Block, DocumentModel, Section

logger = logging.getLogger(__name__)

Clave = tuple[str, str, str, str, bool]


def _a_documento(datos: dict[str, Any]) -> DocumentModel:
    secciones = tuple(
        Section(id=s["id"], title=s["title"], blocks=tuple(
            Block(kind=b["kind"], text=b["text"], items=tuple(b["items"]), signature=b["signature"],
                  rows=tuple((str(k), str(v)) for k, v in b["rows"]))
            for b in s["blocks"]))
        for s in datos["sections"])
    return DocumentModel(language=datos["language"], kind=datos["kind"], title=datos["title"],
                         data_source=datos["data_source"],
                         cover=tuple((str(k), str(v)) for k, v in datos["cover"]),
                         source_notice=datos["source_notice"], stripe=datos["stripe"], sections=secciones)


class AlmacenDeDocumentos:
    def __init__(self, carpeta: Path) -> None:
        self._carpeta = carpeta

    def _ruta(self, clave: Clave) -> Path:
        huella = hashlib.sha256(json.dumps(list(clave), ensure_ascii=False).encode("utf-8")).hexdigest()
        return self._carpeta / f"{huella}.json"

    def guardar(self, clave: Clave, documento: DocumentModel) -> Path:
        """Escritura atómica: o queda entero o no queda."""
        ruta = self._ruta(clave)
        self._carpeta.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps({"clave": list(clave), "documento": asdict(documento)}, ensure_ascii=False),
                            encoding="utf-8")
        os.replace(temporal, ruta)
        return ruta

    def leer(self, clave: Clave) -> DocumentModel | None:
        ruta = self._ruta(clave)
        if not ruta.is_file():
            return None
        try:
            return _a_documento(json.loads(ruta.read_text("utf-8"))["documento"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.error("Documento guardado ilegible en %s: %s", ruta, type(exc).__name__)
            return None

    def _guardados(self) -> list[tuple[float, Clave, Path]]:
        """(fecha, clave, ruta) de cada documento guardado; los ilegibles no cuentan."""
        if not self._carpeta.is_dir():
            return []
        encontrados = []
        for ruta in self._carpeta.glob("*.json"):
            try:
                clave = json.loads(ruta.read_text("utf-8"))["clave"]
                encontrados.append((ruta.stat().st_mtime, (str(clave[0]), str(clave[1]), str(clave[2]),
                                                           str(clave[3]), bool(clave[4])), ruta))
            except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                logger.error("Documento guardado ilegible en %s: %s", ruta, type(exc).__name__)
        return encontrados

    def buscar(self, verdict_id: str, kind: str, language: str, force: bool) -> DocumentModel | None:
        """El último guardado de ese veredicto, documento, idioma y forzado, con
        cualquier modelo (Fase 2): se reutiliza sin resolver el modelo, porque
        listar modelos puede llamar a Google."""
        candidatos = sorted((c for c in self._guardados()
                             if c[1][:3] == (verdict_id, kind, language) and c[1][4] == force),
                            key=lambda c: c[0], reverse=True)
        for _, clave, _ruta in candidatos:
            documento = self.leer(clave)
            if documento is not None:
                return documento
        return None

    def estado(self, verdict_id: str) -> set[tuple[str, str]]:
        """(documento, idioma) ya guardados de un veredicto."""
        return {(clave[1], clave[2]) for _, clave, _ in self._guardados() if clave[0] == verdict_id}
