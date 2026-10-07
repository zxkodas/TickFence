"""Verifica que todo acceso a la API de pywin32 exista de verdad.

Cuatro bugs seguidos vinieron de asumir en que modulo vive cada cosa:

    win32api.StartService          -> en realidad win32service
    win32pipe.CreateFile           -> en realidad win32file
    win32pipe.ReadFile             -> en realidad win32file
    win32file.CloseServiceHandle   -> en realidad win32service

Todos reventan en runtime, y el de install solo con administrador. Este test
recorre el codigo y comprueba cada `win32X.attr` contra el modulo real, asi
que no hace falta acordarse de la lista.
"""
from __future__ import annotations

import ast
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "focuslock"

MODULES = (
    "win32api",
    "win32con",
    "win32event",
    "win32file",
    "win32pipe",
    "win32security",
    "win32service",
    "win32serviceutil",
    "psutil",
    "pywintypes",
)


def _load() -> dict:
    mods = {}
    for name in MODULES:
        try:
            mods[name] = importlib.import_module(name)
        except Exception:  # win32logging no viene en todas las instalaciones
            continue
    return mods


class TestWin32ApiUsage(unittest.TestCase):
    def setUp(self):
        if not sys.platform.startswith("win"):
            self.skipTest("pywin32 solo existe en Windows")
        self.mods = _load()
        self.assertGreater(len(self.mods), 5, "pywin32 no parece instalado")

    def test_every_win32_attribute_exists(self):
        """Cada `win32X.attr` escrito en el codigo debe existir en win32X."""
        problems: list[str] = []
        scanned = 0

        for path in sorted(PKG.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                value = node.value
                if not (isinstance(value, ast.Name) and value.id in self.mods):
                    continue
                scanned += 1
                module = self.mods[value.id]
                if not hasattr(module, node.attr):
                    where = [m for m, mod in self.mods.items() if hasattr(mod, node.attr)]
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}  "
                        f"{value.id}.{node.attr}  -> vive en: "
                        f"{', '.join(where) or 'NINGUN MODULO'}"
                    )

        self.assertGreater(scanned, 20, "el escaneo no encontró accesos, algo falló")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_known_regressions_stay_fixed(self):
        """Los cuatro bugs concretos, para que no vuelvan por refactor."""
        cases = [
            ("win32service", "StartService"),
            ("win32service", "ControlService"),
            ("win32service", "QueryServiceStatus"),
            ("win32service", "OpenService"),
            ("win32service", "OpenSCManager"),
            ("win32service", "CloseServiceHandle"),
            ("win32serviceutil", "InstallService"),
            ("win32serviceutil", "RemoveService"),
            ("win32serviceutil", "HandleCommandLine"),
            ("win32file", "CreateFile"),
            ("win32file", "ReadFile"),
            ("win32file", "WriteFile"),
            ("win32file", "FlushFileBuffers"),
            ("win32file", "FILE_FLAG_OVERLAPPED"),
            ("win32pipe", "CreateNamedPipe"),
            ("win32pipe", "ConnectNamedPipe"),
            ("win32pipe", "DisconnectNamedPipe"),
            ("win32pipe", "PIPE_ACCESS_DUPLEX"),
            ("win32pipe", "PIPE_TYPE_MESSAGE"),
            ("win32pipe", "PIPE_READMODE_MESSAGE"),
            ("win32pipe", "FILE_FLAG_FIRST_PIPE_INSTANCE"),
            ("win32pipe", "WaitNamedPipe"),
            ("win32security", "ConvertStringSecurityDescriptorToSecurityDescriptor"),
            ("win32security", "SDDL_REVISION_1"),
            ("win32security", "SECURITY_ATTRIBUTES"),
        ]
        for module, attr in cases:
            with self.subTest(api=f"{module}.{attr}"):
                self.assertIn(module, self.mods, f"{module} no instalado")
                self.assertTrue(
                    hasattr(self.mods[module], attr),
                    f"{module}.{attr} no existe en esta versión de pywin32",
                )

    def test_wrong_module_regressions(self):
        """Verifica que los atributos NO esten donde se equivocaron antes."""
        wrong = [
            ("win32api", "StartService"),
            ("win32api", "ControlService"),
            ("win32pipe", "CreateFile"),
            ("win32pipe", "ReadFile"),
            ("win32pipe", "WriteFile"),
            ("win32file", "CloseServiceHandle"),
            ("win32file", "CreateNamedPipe"),
        ]
        for module, attr in wrong:
            with self.subTest(api=f"{module}.{attr}"):
                if module not in self.mods:
                    continue
                self.assertFalse(
                    hasattr(self.mods[module], attr),
                    f"{module}.{attr} apareció: puede que la API haya cambiado de módulo",
                )

    def test_win32_positional_arity(self):
        """Descubre la cantidad de argumentos de cada API de pywin32.

        pywin32 no expone `inspect.signature` ni docstrings, asi que la unica
        forma fiable de conocer la firma es preguntar al interprete: se llama
        con N `None` hasta que TypeError dice cuantos positionales espera.

        Esto atrapa bugs como `StartService(handle, None, None)`, que existen
        como funcion pero con firma de 2 argumentos.
        """
        import re

        expected = {
            "StartService": 2,
            "ControlService": 2,
            "QueryServiceStatus": 1,
            "OpenService": 3,
            "CloseServiceHandle": 1,
        }
        found = {}
        for name in expected:
            fn = getattr(self.mods["win32service"], name, None)
            self.assertIsNotNone(fn, f"win32service.{name} no existe")
            arity = None
            for count in range(0, 6):
                try:
                    fn(*([None] * count))
                except TypeError as exc:
                    match = re.search(r"takes (?:exactly )?(\d+)", str(exc))
                    if match:
                        arity = int(match.group(1))
                    break
                except Exception:
                    # Llegó a ejecutarse: la llamada con `count` args es válida.
                    arity = count
                    break
            self.assertIsNotNone(arity, f"no se pudo deducir la firma de {name}")
            found[name] = arity

        for name, want in expected.items():
            with self.subTest(api=name):
                self.assertEqual(
                    found[name], want,
                    f"win32service.{name} ahora pide {found[name]} argumentos, "
                    f"el codigo asume {want}",
                )

    def test_service_calls_match_discovered_arity(self):
        """Las llamadas del servicio deben pasar los argumentos que la API pide."""
        import re

        path = PKG / "service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        arity = {}
        for name in ("StartService", "ControlService", "QueryServiceStatus",
                     "OpenService", "OpenSCManager", "CloseServiceHandle"):
            fn = getattr(self.mods["win32service"], name, None)
            if fn is None:
                continue
            for count in range(0, 6):
                try:
                    fn(*([None] * count))
                except TypeError as exc:
                    m = re.search(r"takes (?:exactly )?(\d+)", str(exc))
                    if m:
                        arity[name] = int(m.group(1))
                    break
                except Exception:
                    arity[name] = count
                    break

        problems = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if not (isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "win32service"):
                continue
            name = node.func.attr
            if name not in arity:
                continue
            given = len(node.args)
            if given != arity[name]:
                problems.append(
                    f"linea {node.lineno}: win32service.{name}() con {given} "
                    f"argumentos, la API pide {arity[name]}"
                )
        self.assertEqual(problems, [], "\n".join(problems))

    def test_service_module_does_not_import_win32api(self):
        """win32api fue la causa de dos bugs y no aporta nada al servicio."""
        path = PKG / "service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "win32api")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "win32api")

    def test_no_win32api_attribute_access_in_service(self):
        path = PKG / "service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders = [
            f"linea {n.lineno}: win32api.{n.attr}"
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "win32api"
        ]
        self.assertEqual(offenders, [], f"win32api usado en: {offenders}")


class TestServiceLifecycle(unittest.TestCase):
    """install/uninstall/start/stop existen y no dependen de admin para
    ser inspeccionados."""

    def test_lifecycle_api(self):
        from focuslock import service

        for name in ("install", "uninstall", "start", "stop", "_is_installed"):
            self.assertTrue(callable(getattr(service, name, None)), name)

    def test_service_framework_metadata(self):
        if not sys.platform.startswith("win"):
            self.skipTest("servicio Windows solo existe en Windows")
        from focuslock.paths import SERVICE_DISPLAY_NAME, SERVICE_NAME
        from focuslock.service import TickFenceService

        self.assertEqual(TickFenceService._svc_name_, SERVICE_NAME)
        self.assertEqual(TickFenceService._svc_display_name_, SERVICE_DISPLAY_NAME)
        self.assertTrue(TickFenceService._svc_description_)

    def test_uninstall_cleans_ifeo(self):
        """Los IFEO se limpian siempre, exista o no el servicio.

        Si quedaran, los programas bloqueados seguirian sin arrancar con
        TickFence desinstalado, sin forma de recuperarlos desde la app.
        """
        path = PKG / "service.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        uninstall_src = ast.get_source_segment(
            source,
            next(
                n
                for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "uninstall"
            ),
        )
        self.assertIn("ifeo", uninstall_src, "uninstall debe limpiar el IFEO")

    def test_install_reinstalls_cleanly(self):
        """install() debe desinstalar antes si el servicio ya existe."""
        path = PKG / "service.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        install_fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "install"
        )
        calls = {
            n.func.id
            if isinstance(n.func, ast.Name)
            else (n.func.attr if isinstance(n.func, ast.Attribute) else "")
            for n in ast.walk(install_fn)
            if isinstance(n, ast.Call)
        }
        self.assertIn("_is_installed", calls)
        self.assertIn("uninstall", calls)
        self.assertIn("InstallService", calls)

    def test_install_does_not_pass_exeargs(self):
        """La clase va en el registro, no en la linea de comandos.

        pythonservice.exe lee `Services\\<nombre>\\PythonClass`. Si se le pasan
        `exeArgs` con `-m` o flags, ignora el registro y el servicio muere con
        1066 (ERROR_INVALID_FUNCTION).
        """
        import inspect

        from focuslock import service

        self.assertIsNone(
            service._service_command(),
            "exeArgs debe ser None: la clase se resuelve por registro",
        )
        self.assertTrue(service._service_args_look_right())
        source = inspect.getsource(service.install)
        self.assertIn("pythonClassString", source)
        # La clase tiene que ser la completa: modulo.Clase
        self.assertIn("TickFenceService", source)

    def test_python_class_string_is_fully_qualified(self):
        if not sys.platform.startswith("win"):
            self.skipTest("servicio Windows solo existe en Windows")
        """`focuslock.service` solo no alcanza: pywin32 quiere modulo.Clase.

        Se importa de verdad lo que se registra: lo que importa es que el
        nombre exista, no que el fuente se parezca.
        """
        import importlib
        import re
        from pathlib import Path as _Path

        source = (_Path(PKG) / "service.py").read_text(encoding="utf-8")
        match = re.search(
            r'pythonClassString=f"\{__package__\}\.service\.(\w+)"', source
        )
        self.assertIsNotNone(match, f"no se encontro pythonClassString en:\n{source[:800]}")

        class_name = match.group(1)
        module = importlib.import_module("focuslock.service")
        self.assertTrue(
            hasattr(module, class_name),
            f"focuslock.service.{class_name} no existe",
        )
        self.assertEqual(class_name, "TickFenceService")

    def test_install_service_writes_python_class_to_registry(self):
        if not sys.platform.startswith("win"):
            self.skipTest("servicio Windows solo existe en Windows")
        """Verifica que pywin32 realmente escribe la clase donde dice."""
        import inspect

        import win32serviceutil

        source = inspect.getsource(win32serviceutil.InstallPythonClassString)
        self.assertIn("PythonClass", source)
        self.assertIn("Services", source)

    def test_service_module_has_main_block_for_pythonservice(self):
        """pythonservice.exe ejecuta el modulo: necesita HandleCommandLine."""
        path = PKG / "service.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn('if __name__ == "__main__":', source)
        self.assertIn("HandleCommandLine", source.split('if __name__ == "__main__":')[1])

    def test_start_waits_for_running(self):
        """StartService vuelve antes de que el servicio levante: hay que esperar."""
        path = PKG / "service.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("SERVICE_RUNNING", source)
        self.assertIn("QueryServiceStatus", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
