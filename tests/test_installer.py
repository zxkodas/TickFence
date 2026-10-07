"""Verifica que el instalador y el README no se contradigan entre si.

Tres cosas se rompen en silencio y ninguna rompe la app:

  1. El .iss declara un Source: que ya no existe. Inno Setup SI falla al
     compilar, pero solo si alguien compila; el repo queda verde mientras tanto.
  2. La version del .iss se desalinea de pyproject.toml. El instalador
     announce una version y el paquete instala otra.
  3. El README apunta a una imagen que no esta. En un repo publico se ve
     roto y no hay ningun test que lo note.

La 3 la arrastro yo hoy: tres referencias a screenshots que ya no existian.
"""
from __future__ import annotations

import ast
import importlib
import os
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "installer" / "TickFence.iss"
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
TESTS = ROOT / "tests"

# Solo lo que aparece despues de Source:. Los flags y los DestDir se ruido.
SOURCE_RE = re.compile(r'^\s*Source:\s*"([^"]+)"', re.MULTILINE | re.IGNORECASE)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
BADGE_RE = re.compile(r"badge/tests-(\d+)%20passing")


class TestFuentesDelInstalador(unittest.TestCase):
    def test_el_iss_existe(self):
        self.assertTrue(ISS.is_file(), f"falta {ISS}")

    def test_todo_source_existe(self):
        """Cada Source: del .iss tiene que estar en el disco.

        Las rutas son relativas al .iss, que vive en installer/.
        """
        texto = ISS.read_text(encoding="utf-8")
        fuentes = SOURCE_RE.findall(texto)
        self.assertTrue(fuentes, "el .iss no declara ningun Source")

        faltantes = []
        for fuente in fuentes:
            # El .iss escribe rutas Windows (..\\focuslock\\*): en Linux la
            # barra invertida no separa, se normaliza antes de comparar.
            fuente = fuente.replace("\\", os.sep)
            # Los Source con comodin (focuslock/*) son carpeta completa: lo
            # que importa es que la carpeta exista.
            if fuente.endswith("*"):
                raiz = fuente.rstrip("*").rstrip("\\/")
                if not (ISS.parent / raiz).exists():
                    faltantes.append(fuente)
                continue
            if not (ISS.parent / fuente).exists():
                faltantes.append(fuente)

        self.assertEqual(
            [], faltantes,
            f"el .iss referencia archivos que no existen: {faltantes}")

    def test_la_version_del_instalador_es_la_del_paquete(self):
        """Si divergen, el .exe dice una version y pip instala otra."""
        datos = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        del_paquete = str(datos["project"]["version"])

        texto = ISS.read_text(encoding="utf-8")
        del_instalador = re.search(r'#define\s+AppVersion\s+"([^"]+)"', texto)
        self.assertIsNotNone(del_instalador, "el .iss no define AppVersion")

        self.assertEqual(
            del_paquete, del_instalador.group(1),
            "AppVersion en el .iss no coincide con la version de pyproject.toml")


class TestReadme(unittest.TestCase):
    def test_toda_imagen_existe(self):
        """Cero referencias rotas. Ni una."""
        texto = README.read_text(encoding="utf-8")
        rotas = []
        for ruta in IMAGE_RE.findall(texto):
            if ruta.startswith(("http://", "https://")):
                continue
            if not (ROOT / ruta).exists():
                rotas.append(ruta)
        self.assertEqual([], rotas, f"imagenes que no existen: {rotas}")

    def test_no_quedan_placeholders(self):
        """Los PNG que decian 'replace this file' no tienen que volver."""
        carpeta = ROOT / "docs" / "screenshots"
        self.assertTrue(carpeta.is_dir(), "falta docs/screenshots")
        for png in carpeta.glob("*.png"):
            # Un placeholder era plano y pesaba ~20 KB con texto de ayuda.
            # El limite es holgado a proposito: solo tiene que ser distinguible
            # de un render de verdad, que pesa bastante mas.
            self.assertGreater(
                png.stat().st_size, 20_000,
                f"{png.name} pesa {png.stat().st_size} B: parece un placeholder")

    def test_el_badge_de_tests_dice_la_verdad(self):
        """El badge del README tiene que decir cuantos tests hay.

        Se cuenta con unittest.TestLoader, NO con AST. El conteo por AST daba
        237 contra los 234 reales: cuenta metodos test_ de clases auxiliares
        que no son TestCase, y cuenta repetidos que Python descarta cuando
        redefine el metodo. El loader ya hace las dos cuentas bien.

        Importar las suites es seguro: ninguna crea QApplication al importarse
        (eso va en setUpClass) y test_guard solo mata procesos dentro de sus
        tests, no al importar.
        """
        total = 0
        for archivo in sorted(TESTS.glob("test_*.py")):
            modulo = importlib.import_module(f"tests.{archivo.stem}")
            total += unittest.TestLoader().loadTestsFromModule(modulo).countTestCases()

        texto = README.read_text(encoding="utf-8")
        badge = BADGE_RE.search(texto)
        self.assertIsNotNone(badge, "el README no tiene el badge de tests")
        self.assertEqual(
            total, int(badge.group(1)),
            f"el badge dice {badge.group(1)} pero hay {total} tests")


class TestRenderDeScreenshots(unittest.TestCase):
    """El script que genera los PNG tiene que seguir siendo ejecutable."""

    def test_el_script_existe(self):
        self.assertTrue((ROOT / "docs" / "render_screenshots.py").is_file())

    def test_no_usa_plataforma_offscreen(self):
        """offscreen en Windows no tiene fuentes: todo sale como cuadritos.

        Hay un render entero que salio asi. Si alguien lo vuelve a poner para
        'no molestar al escritorio', el test lo frena.

        Se busca con AST y no con una regex sobre el texto: el docstring del
        script menciona QT_QPA_PLATFORM justamente para explicar que NO se usa,
        y tanto assertNotIn como una regex se disparan con el comentario.
        """
        arbol = ast.parse((ROOT / "docs" / "render_screenshots.py").read_text(encoding="utf-8"))

        # Docstrings del modulo, las clases y las funciones.
        docstrings = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                cuerpo = getattr(nodo, "body", [])
                if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(
                    cuerpo[0].value, ast.Constant
                ) and isinstance(cuerpo[0].value.value, str):
                    docstrings.add(id(cuerpo[0].value))

        usos = [
            nodo.value
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Constant)
            and isinstance(nodo.value, str)
            and "QT_QPA_PLATFORM" in nodo.value
            and id(nodo) not in docstrings
        ]

        self.assertEqual(
            [], usos,
            "el render menciona QT_QPA_PLATFORM fuera de un comentario: en "
            "Windows offscreen no tiene fuentes y los textos salen como "
            "cuadritos. Renderizar con la plataforma real.")


if __name__ == "__main__":
    unittest.main()
