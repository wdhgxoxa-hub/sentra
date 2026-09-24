"""
Superficie IPC sin restos (C2, D-C2…D-C5)
=========================================

Cada comando registrado en `ui/src-tauri/src/lib.rs` lo invoca
`ui/src/lib/ipc.ts`, y cada invocación de ipc.ts está registrada. Además,
cada método de `ipc` lo usa alguna vista o componente: un comando sin nadie
que lo llame es código muerto que sigue expuesto. Los retirados con la
pipeline antigua no pueden volver sin quitarlos de aquí.
"""

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
UI = RAIZ / "ui" / "src"
LIB_RS = RAIZ / "ui" / "src-tauri" / "src" / "lib.rs"
IPC_TS = UI / "lib" / "ipc.ts"

#: Retirados con la pipeline antigua de Reddit (tablero, feed, ficha,
#: Blueprint/Arquitecto/PDF antiguos, Control del pipeline y Ajustes de Reddit).
RETIRADOS = {
    "get_radar_feed", "get_opportunity_board", "get_opportunity_detail", "get_cluster_history",
    "get_subreddits", "get_pipeline_runs", "get_top_opportunities", "trigger_scan",
    "translate_quotes", "update_opportunity_status", "upsert_subreddit", "set_fetcher_mode",
    "save_reddit_credentials", "test_reddit_connection", "generate_blueprint", "export_pdf",
    "generate_architecture",
}


def registrados() -> set[str]:
    bloque = LIB_RS.read_text("utf-8").split("generate_handler![", 1)[1].split("])", 1)[0]
    return set(re.findall(r"commands::\w+::(\w+)", bloque))


def invocados() -> set[str]:
    return set(re.findall(r'invoke<[^>]*>\(\s*"(\w+)"', IPC_TS.read_text("utf-8")))


def metodos_ipc() -> set[str]:
    cuerpo = IPC_TS.read_text("utf-8").split("export const ipc = {", 1)[1].split("} as const;", 1)[0]
    return set(re.findall(r"^  (\w+): ", cuerpo, flags=re.MULTILINE))


def fuentes_ui() -> str:
    return "\n".join(p.read_text("utf-8") for p in UI.rglob("*.ts*") if p != IPC_TS)


class TestSuperficieIpc(unittest.TestCase):
    def test_cada_comando_registrado_se_invoca_y_viceversa(self):
        self.assertEqual(registrados(), invocados())

    def test_cada_metodo_de_ipc_tiene_quien_lo_use(self):
        codigo = fuentes_ui()
        sin_uso = {m for m in metodos_ipc() if not re.search(rf"\bipc\.{m}\b", codigo)}
        self.assertEqual(sin_uso, set())

    def test_los_comandos_retirados_no_vuelven(self):
        self.assertEqual(RETIRADOS & (registrados() | invocados()), set())


if __name__ == "__main__":
    unittest.main()
