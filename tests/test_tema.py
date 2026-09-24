"""
Tests del sistema de color
==========================

El diseño es código: si una combinación deja de leerse, esto falla igual que
fallaría una función rota. Los umbrales son los de WCAG 2.1 para texto normal
(4.5:1) y para elementos grandes o de adorno (3:1).

El conversor OKLCH -> sRGB va aquí y no en la aplicación a propósito: en la
interfaz lo resuelve el navegador, y una segunda implementación en producción
sería una copia que se desincroniza.
"""

import math
import re
import unittest
from pathlib import Path
from typing import ClassVar

CSS = Path(__file__).resolve().parents[1] / "ui" / "src" / "styles.css"

AA_TEXTO = 4.5
AA_GRANDE = 3.0


# --- Color -------------------------------------------------------------------


def oklch_a_srgb(L, C, h_deg, alpha=1.0, fondo=(1.0, 1.0, 1.0)):
    h = math.radians(h_deg)
    a, b = C * math.cos(h), C * math.sin(h)

    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3

    lineal = (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )

    def gamma(u):
        u = max(0.0, min(1.0, u))
        return 12.92 * u if u <= 0.0031308 else 1.055 * (u ** (1 / 2.4)) - 0.055

    rgb = tuple(gamma(u) for u in lineal)
    if alpha < 1.0:
        rgb = tuple(alpha * c + (1 - alpha) * f for c, f in zip(rgb, fondo))
    return rgb


def contraste(rgb1, rgb2):
    def lum(rgb):
        def lin(u):
            return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

        r, g, b = (lin(c) for c in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    a, b = lum(rgb1), lum(rgb2)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# --- Lectura del CSS ---------------------------------------------------------

OKLCH = re.compile(
    r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:/\s*([\d.]+)\s*)?\)"
)


def _variables(bloque: str) -> dict:
    """Variables `--color-*` de un bloque, como (L, C, h, alpha)."""
    salida = {}
    for nombre, valor in re.findall(r"(--color-[\w-]+):\s*([^;]+);", bloque):
        encaje = OKLCH.search(valor)
        if not encaje:
            continue
        L, C, h, alpha = encaje.groups()
        salida[nombre] = (float(L), float(C), float(h), float(alpha or 1.0))
    return salida


def _bloque(texto: str, inicio: str) -> str:
    desde = texto.index(inicio)
    profundidad, i = 0, texto.index("{", desde)
    for fin in range(i, len(texto)):
        if texto[fin] == "{":
            profundidad += 1
        elif texto[fin] == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[i : fin + 1]
    raise AssertionError(f"bloque sin cerrar: {inicio}")


class BaseTema(unittest.TestCase):
    css: ClassVar[str]
    claro: ClassVar[dict[str, tuple[float, float, float, float]]]
    oscuro: ClassVar[dict[str, tuple[float, float, float, float]]]

    @classmethod
    def setUpClass(cls):
        cls.css = CSS.read_text(encoding="utf-8")
        cls.claro = _variables(_bloque(cls.css, "@theme"))
        cls.oscuro = dict(cls.claro)
        cls.oscuro.update(_variables(_bloque(cls.css, ':root[data-theme="dark"]')))

    def color(self, paleta, nombre, fondo=(1.0, 1.0, 1.0)):
        self.assertIn(nombre, paleta, f"falta {nombre} en la paleta")
        L, C, h, alpha = paleta[nombre]
        return oklch_a_srgb(L, C, h, alpha, fondo)

    def comprobar(self, paleta, tema, texto, superficie, minimo=AA_TEXTO):
        fondo = self.color(paleta, superficie)
        delante = self.color(paleta, texto, fondo=fondo)
        ratio = contraste(delante, fondo)
        self.assertGreaterEqual(
            ratio,
            minimo,
            f"[{tema}] {texto} sobre {superficie}: {ratio:.2f}:1 (minimo {minimo})",
        )


class TestLosDosBloquesOscurosCoinciden(BaseTema):
    """CSS no deja agrupar el interruptor y la preferencia del sistema.

    Son dos bloques con las mismas declaraciones, y tocar uno y olvidar el
    otro deja la aplicacion con dos temas oscuros distintos segun como se
    haya llegado a el.
    """

    def test_declaran_exactamente_lo_mismo(self):
        por_atributo = _bloque(self.css, ':root[data-theme="dark"]')
        por_preferencia = _bloque(self.css, ":root:not([data-theme=\"light\"])")

        def declaraciones(bloque):
            return sorted(
                (nombre.strip(), " ".join(valor.split()))
                for nombre, valor in re.findall(r"(--[\w-]+):\s*([^;]+);", bloque)
            )

        self.assertEqual(declaraciones(por_atributo), declaraciones(por_preferencia))


class TestTextoLegible(BaseTema):
    SUPERFICIES = ("--color-bg", "--color-surface", "--color-surface-2")

    def test_tinta_principal_en_ambos_temas(self):
        for tema, paleta in (("claro", self.claro), ("oscuro", self.oscuro)):
            for superficie in self.SUPERFICIES:
                self.comprobar(paleta, tema, "--color-ink", superficie, 7.0)

    def test_tinta_secundaria_en_ambos_temas(self):
        for tema, paleta in (("claro", self.claro), ("oscuro", self.oscuro)):
            for superficie in self.SUPERFICIES:
                self.comprobar(paleta, tema, "--color-ink-soft", superficie)

    def test_la_tinta_tenue_sigue_siendo_legible(self):
        """Se usa en subtitulos de 11 px: es la que primero se pierde."""
        for tema, paleta in (("claro", self.claro), ("oscuro", self.oscuro)):
            for superficie in self.SUPERFICIES:
                self.comprobar(paleta, tema, "--color-ink-faint", superficie)

    def test_los_semanticos_se_leen_como_texto(self):
        for tema, paleta in (("claro", self.claro), ("oscuro", self.oscuro)):
            for nombre in ("--color-ok", "--color-warn", "--color-danger", "--color-accent"):
                self.comprobar(paleta, tema, nombre, "--color-surface", AA_GRANDE)


class TestControles(BaseTema):
    def test_el_texto_se_lee_sobre_el_boton_primario(self):
        """En oscuro el acento se aclara y el blanco encima ya no valdria."""
        for tema, paleta in (("claro", self.claro), ("oscuro", self.oscuro)):
            acento = self.color(paleta, "--color-accent")
            encima = self.color(paleta, "--color-on-accent", fondo=acento)
            ratio = contraste(encima, acento)
            self.assertGreaterEqual(
                ratio, AA_TEXTO, f"[{tema}] texto sobre acento: {ratio:.2f}:1"
            )

    def test_el_acento_se_oscurece_al_pasar_el_cursor_en_claro(self):
        self.assertLess(
            self.claro["--color-accent-hover"][0],
            self.claro["--color-accent"][0],
            "en tema claro el hover debe ser mas oscuro que el reposo",
        )


class TestInsignias(BaseTema):
    """El texto de la insignia sobre su propio fondo suave.

    Pintados del mismo color, «Media» quedaba en 1,8:1: se veia la mancha
    amarilla y no la palabra.
    """

    NIVELES = ("critical", "high", "medium", "low")

    def test_el_texto_se_lee_sobre_el_fondo_suave(self):
        for tema, paleta in (("claro", self.claro), ("oscuro", self.oscuro)):
            base = self.color(paleta, "--color-surface")
            for nivel in self.NIVELES:
                suave = self.color(paleta, f"--color-{nivel}-soft", fondo=base)
                tinta = self.color(paleta, f"--color-{nivel}-ink", fondo=suave)
                ratio = contraste(tinta, suave)
                self.assertGreaterEqual(
                    ratio, AA_TEXTO, f"[{tema}] insignia {nivel}: {ratio:.2f}:1"
                )


class TestLienzo(BaseTema):
    def test_el_modo_claro_no_usa_blanco_puro(self):
        """El blanco clinico es lo que cansa en una sesion larga."""
        self.assertLess(self.claro["--color-bg"][0], 0.98)

    def test_la_tarjeta_se_separa_del_lienzo(self):
        claro = self.claro
        self.assertGreater(
            claro["--color-surface"][0],
            claro["--color-bg"][0],
            "en tema claro la tarjeta va por encima del lienzo",
        )

    def test_en_oscuro_la_tarjeta_tambien_se_separa(self):
        oscuro = self.oscuro
        self.assertGreater(oscuro["--color-surface"][0], oscuro["--color-bg"][0])


if __name__ == "__main__":
    unittest.main()
