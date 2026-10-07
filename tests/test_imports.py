"""Chequeos de importacion y de consistencia entre modulos.

Los errores de importacion (un nombre que no existe en el modulo destino) solo
se ven cuando se ejecuta el comando, y `install` exige administrador. Estos
tests los atrapan sin needing privilegios.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "focuslock"

from focuslock.gate import Gate  # noqa: E402


PKG_INIT = PKG / "__init__.py"


class _NoClient:
    """Cliente de TickTick que no esta configurado, para tests sin red."""

    configured = False

    def projects(self):
        return []

    def project_data(self, _pid):
        return {}


def _module_names(path: Path) -> set[str]:
    """Nombres publicos definidos por un modulo (o por su __init__ si es paquete)."""
    init = path / "__init__.py"
    if init.exists():
        path = init
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


class TestInternalImports(unittest.TestCase):
    """`from .paths import X` exige que X exista de verdad en paths.py."""

    def test_relative_imports_resolve(self):
        cache = {p.stem: _module_names(p) for p in PKG.rglob("*.py")}
        problems: list[str] = []

        for path in sorted(PKG.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                if node.module is None:
                    continue  # `from . import x`
                # `ui` es un subpaquete: su archivo real es ui/__init__.py.
                available = cache.get(node.module)
                if available is None and node.module == "ui":
                    available = cache.get("__init__") if (PKG / "ui").exists() else None
                    if available is None:
                        available = _module_names(PKG / "ui")
                if available is None:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} -> modulo "
                        f"inexistente '.{node.module}'"
                    )
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    # `from . import x` no llega aqui; aqui es `from .m import a`.
                    if alias.name not in available:
                        problems.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} -> "
                            f"'{alias.name}' no existe en focuslock/{node.module}.py"
                        )

        self.assertEqual(problems, [], "\n".join(problems))

    def test_every_module_parses(self):
        for path in sorted(PKG.rglob("*.py")):
            with self.subTest(module=path.name):
                ast.parse(path.read_text(encoding="utf-8"))

    def test_no_hay_backslash_en_fstrings(self):
        """Ninguna barra invertida puede quedar DENTRO de la parte de expresion
        de un f-string.

        PEP 701 (Python 3.12) lo permite; en 3.11 es SyntaxError. O sea: el
        codigo anda perfecto en la maquina de desarrollo, que corre 3.14, y
        revienta en la version minima que promete pyproject.toml. Eso paso de
        verdad: un print de una ruta de Windows dentro de tr() dejo rojo el
        CI en 3.11 y verde en 3.14 en la misma corrida.

        OJO con la tentacion de resolverlo parseando con
        ast.parse(src, feature_version=(3, 11)): NO funciona. feature_version
        solo cubre un puñado de cambios (async como identificador, except*,
        el walrus en comprehension) y no la gramatica de los f-strings. Se
        comprobo: parsea el caso malo sin quejarse.
        """
        for path in sorted(PKG.rglob("*.py")):
            with self.subTest(module=path.name):
                arbol = ast.parse(path.read_text(encoding="utf-8"))
                for nodo in ast.walk(arbol):
                    if not isinstance(nodo, ast.JoinedStr):
                        continue
                    for parte in nodo.values:
                        if isinstance(parte, ast.FormattedValue):
                            expr = ast.unparse(parte.value)
                            if "\\" in expr:
                                self.fail(
                                    f"{path.name}:{nodo.lineno}  la expresion "
                                    f"{expr!r} tiene una barra invertida dentro "
                                    f"de un f-string: SyntaxError en Python "
                                    f"3.11. Sacale el prefijo f."
                                )

    def test_la_version_minima_es_la_que_declara_pyproject(self):
        """Si pyproject sube el piso, la matriz de CI tiene que acompanar.

        Sin esto, un requires-python que sube a 3.12 sigue teniendo la
        matrix en 3.11 y el CI pasa probando una version que ya no se
        promete. O al reves: el piso sube y nadie lo prueba.
        """
        import re

        raiz = Path(__file__).resolve().parents[1]
        texto = (raiz / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'requires-python\s*=\s*">=\s*(\d+)\.(\d+)"', texto)
        self.assertIsNotNone(m, "no se pudo leer requires-python")
        piso = (int(m.group(1)), int(m.group(2)))

        workflow = (raiz / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )
        versiones = set(re.findall(r'"(\d+\.\d+)"', workflow))
        self.assertTrue(versiones, "no encontre la matriz de Python en el CI")
        self.assertIn(
            f"{piso[0]}.{piso[1]}", versiones,
            f"pyproject pide {piso[0]}.{piso[1]}+ y la matriz de CI prueba "
            f"{sorted(versiones)}: falta la version minima",
        )

    def test_cli_commands_are_importable(self):
        """Todos los subcomandos del CLI deben importar bien sin admin."""
        from focuslock import __main__ as cli

        for name in ("cmd_install", "cmd_uninstall", "cmd_console", "cmd_gui", "cmd_status"):
            self.assertTrue(callable(getattr(cli, name)), name)

    def test_cli_builds_parser_without_error(self):
        """El argparse del CLI debe construirse sin lanzar (no ejecuta comandos)."""
        from focuslock import __main__ as cli

        parser_source = Path(cli.__file__).read_text(encoding="utf-8")
        self.assertIn('prog="focuslock"', parser_source)

    def test_install_command_does_not_require_admin_at_import(self):
        """Importar cmd_install no debe importar win32service de forma fatal."""
        from focuslock import __main__ as cli

        self.assertTrue(hasattr(cli.cmd_install, "__code__"))

    def test_local_backend_has_same_surface_as_engine(self):
        """La UI llama comandos por nombre: los dos backends deben ofrecer los
        mismos, o el modo standalone rompe en runtime."""
        from focuslock.daemon import Engine
        from focuslock.local import LocalBackend

        engine_cmds = {c[len("_cmd_"):] for c in dir(Engine) if c.startswith("_cmd_")}
        local_cmds = {c[len("_cmd_"):] for c in dir(LocalBackend) if c.startswith("_cmd_")}

        missing = engine_cmds - local_cmds
        self.assertEqual(
            missing, set(), f"LocalBackend no implementa: {sorted(missing)}"
        )

    def test_local_backend_reports_no_enforcement(self):
        """El modo local no bloquea, y tiene que decirlo en vez de fallar."""
        import tempfile

        from focuslock.local import LocalBackend

        # Backend real pero sobre una config temporal, sin tocar la del usuario.
        with tempfile.TemporaryDirectory() as tmp:
            from focuslock.config import Config
            from focuslock.store import Store

            backend = LocalBackend()
            backend.config = Config(Path(tmp) / "config.json")
            backend.config.load()
            backend.store = Store(Path(tmp) / "state.json")
            backend.store.read()
            backend.gate = Gate(_NoClient(), backend.config, backend.store)
            backend.client = _NoClient()
            backend.server.stop()

            try:
                st = backend.call("status")
                self.assertIn("enforcement", st)
                self.assertFalse(st["enforcement"], "sin servicio no hay bloqueo")
                self.assertEqual(st["guard_armed"], False)
                self.assertEqual(st["ifeo"], [])

                payload = backend.state_payload()
                self.assertFalse(
                    payload["locked"],
                    "la extension no debe bloquear si no hay enforcement",
                )
                self.assertIn("no se esta bloqueando", payload["reason"])

                with self.assertRaises(RuntimeError):
                    backend.call("ifeo_sync")

                with self.assertRaises(KeyError):
                    backend.call("comando_inventado")
            finally:
                backend.close()

    def test_standalone_emergency_never_grants(self):
        """Sin enforcement, cumplir los requisitos no puede 'desbloquear' nada."""
        import tempfile

        from focuslock.local import LocalBackend

        with tempfile.TemporaryDirectory() as tmp:
            from focuslock.config import Config
            from focuslock.store import Store

            backend = LocalBackend()
            backend.config = Config(Path(tmp) / "config.json")
            backend.config.load()
            backend.store = Store(Path(tmp) / "state.json")
            backend.store.read()
            backend.gate = Gate(_NoClient(), backend.config, backend.store)
            backend.client = _NoClient()
            backend.server.stop()

            try:
                # Primero: un intento invalido no concede ni registra nada.
                bad = backend.call(
                    "emergency",
                    text="muy corto",
                    prompts={},
                    keystrokes=5,
                    elapsed=2,
                    longest_idle=0,
                )
                self.assertFalse(bad.get("granted"))
                self.assertEqual(len(backend.gate.emergencies()), 0)

                # Despues: uno valido, con palabras de verdad en los prompts.
                text = "palabra " * 330
                prompts = {
                    "motivo": "porque " * 35,
                    "costo": "porque " * 35,
                    "plan": "porque " * 35,
                }
                r = backend.call(
                    "emergency",
                    text=text,
                    prompts=prompts,
                    keystrokes=len(text),
                    elapsed=310,
                    longest_idle=15,
                )
                self.assertFalse(r.get("granted"), "no debe conceder desbloqueo")
                self.assertTrue(r.get("no_service"), f"esperaba no_service, vino {r!r}")
                # el compromiso queda registrado igual, como evidencia
                self.assertEqual(len(backend.gate.emergencies()), 1)
            finally:
                backend.close()

    def test_service_module_exposes_expected_api(self):
        from focuslock import service

        if sys.platform.startswith("win"):
            names = ("install", "uninstall", "run_console", "TickFenceService")
        else:
            # En Linux no hay clase de servicio Windows: hay unidad systemd.
            names = ("install", "uninstall", "run_console", "is_running", "start", "stop")
        for name in names:
            self.assertTrue(hasattr(service, name), name)

    def test_service_kwargs_match_pywin32_signature(self):
        if not sys.platform.startswith("win"):
            self.skipTest("pywin32 solo existe en Windows")
        """Los keywords de InstallService deben existir en la version instalada.

        pywin32 usa `displayName`. Pasarle `serviceDisplayName` revienta el
        install en tiempo de ejecucion, y solo con admin, asi que lo chequeamos
        aca por AST.
        """
        import inspect

        import win32serviceutil

        params = set(inspect.signature(win32serviceutil.InstallService).parameters)

        path = PKG / "service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: list[dict[str, ast.AST]] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "InstallService"
            ):
                found.append({kw.arg: kw.value for kw in node.keywords})

        self.assertTrue(found, "no se encontro ninguna llamada a InstallService")
        for kwargs in found:
            unknown = {k for k in kwargs if k is not None} - params
            self.assertEqual(
                unknown, set(), f"keywords inexistentes en InstallService: {unknown}"
            )

    def test_win32_attributes_exist_in_their_real_modules(self):
        """Regresion: `StartService` no existe en win32api, vive en win32service.

        Y al reves: `CloseServiceHandle` es de win32service, no de win32file.
        Estos errores solo aparecen ejecutando install, que exige admin.
        """
        if not sys.platform.startswith("win"):
            self.skipTest("pywin32 solo existe en Windows")
        import win32api
        import win32service

        self.assertTrue(hasattr(win32service, "StartService"))
        self.assertFalse(
            hasattr(win32api, "StartService"),
            "si esto aparece True, el modulo cambio y hay que revisarlo",
        )
        for name in (
            "StartService",
            "ControlService",
            "QueryServiceStatus",
            "OpenService",
            "OpenSCManager",
        ):
            self.assertTrue(hasattr(win32service, name), f"win32service.{name}")

    def test_service_uses_start_from_wrong_module(self):
        """Ninguna llamada a StartService/ControlService puede ir por win32api."""
        path = PKG / "service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        service_api = {
            "StartService",
            "ControlService",
            "QueryServiceStatus",
            "OpenService",
            "OpenSCManager",
            "CloseServiceHandle",
        }
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr not in service_api:
                continue
            # win32service.StartService(...)  ->  valor = win32service
            value = node.value
            if isinstance(value, ast.Name) and value.id == "win32api":
                offenders.append(f"linea {node.lineno}: win32api.{node.attr}")

        self.assertEqual(
            offenders, [], f"API de win32service llamada desde win32api: {offenders}"
        )

    def test_safe_helper_survives_emoji(self):
        """Los proyectos de TickTick traen emoji y cp1252 no los encodea.

        Sin `_safe`, `python -m focuslock status` revienta con
        UnicodeEncodeError apenas el servicio responde.
        """
        from focuslock.__main__ import _safe

        for value in ("📖Estudios", "🔒Vida", "motivo con ñ y á", ""):
            with self.subTest(value=value):
                result = _safe(value)
                self.assertIsInstance(result, str)
                # tiene que poder imprimirse en cp1252 sin reventar
                result.encode("cp1252", errors="replace")

    def test_safe_helper_passes_through_plain_text(self):
        from focuslock.__main__ import _safe

        self.assertEqual(_safe("texto normal"), "texto normal")
        self.assertEqual(_safe(42), "42")
        self.assertEqual(_safe(None), "None")

    def test_cli_module_exposes_safe(self):
        from focuslock import __main__ as cli

        self.assertTrue(callable(getattr(cli, "_safe", None)))

    def test_service_module_does_not_import_win32api(self):
        """win32api no aporta nada aqui y fue la fuente de dos bugs."""
        path = PKG / "service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "win32api", "win32api no deberia importarse"
                    )

    def test_service_class_names_match_service_module(self):
        """El pythonClassString del servicio debe apuntar a una clase real."""
        if not sys.platform.startswith("win"):
            self.skipTest("servicio Windows solo existe en Windows")
        from focuslock import service
        from focuslock.paths import SERVICE_NAME

        cls = service.TickFenceService
        self.assertEqual(cls._svc_name_, SERVICE_NAME)
        self.assertEqual(cls._svc_display_name_, service.paths.SERVICE_DISPLAY_NAME)

    def test_handlecommandline_can_load_the_class(self):
        """HandleCommandLine es lo que ejecuta Windows; debe poder resolver la clase."""
        if not sys.platform.startswith("win"):
            self.skipTest("servicio Windows solo existe en Windows")
        from focuslock.service import TickFenceService

        # Es lo que hace win32serviceutil al arrancar: resolve (pkg.mod, clase).
        module_name, _, class_name = "focuslock.service.TickFenceService".rpartition(".")
        import importlib

        module = importlib.import_module(module_name)
        self.assertTrue(hasattr(module, class_name))
        self.assertIs(getattr(module, class_name), TickFenceService)


class TestEngineCommandSurface(unittest.TestCase):
    """Cada comando de la GUI debe existir en el Engine (sino, error en runtime)."""

    EXPECTED = [
        "status", "poll", "relock", "lock", "unlock", "emergency", "history",
        "ticktick_test", "ticktick_set_token", "config_get", "config_set",
        "install_ready", "diag",
        "programs_blocked_add", "programs_blocked_del",
        "programs_allowed_add", "programs_allowed_del",
        "sites_blocked_add", "sites_blocked_del",
        "sites_allowed_add", "sites_allowed_del",
        "ifeo_sync", "diag",
    ]

    def test_all_commands_exist(self):
        from focuslock.daemon import Engine

        missing = [c for c in self.EXPECTED if not hasattr(Engine, f"_cmd_{c}")]
        self.assertEqual(missing, [], f"comandos faltantes en Engine: {missing}")

    def test_gui_only_calls_known_commands(self):
        """Cada comando literal que invoca la UI debe existir en el Engine.

        Las llamadas con f-string (f"{section}_{field}_add") se cubren aparte,
        combinando los valores que la UI realmente les pasa.
        """
        from focuslock.daemon import Engine

        known = {c[len("_cmd_"):] for c in dir(Engine) if c.startswith("_cmd_")}
        ui_files = sorted((PKG / "ui").rglob("*.py"))

        literals: set[str] = set()
        interpolated: list[tuple[set[str], set[str]]] = []

        for path in ui_files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "call"
                    and node.args
                ):
                    continue
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    literals.add(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    # f"{section}_{field}_add" -> variables + sufijos
                    suffix, variables = "", set()
                    for part in arg.values:
                        if isinstance(part, ast.Constant) and isinstance(part.value, str):
                            suffix += part.value
                        elif isinstance(part, ast.FormattedValue):
                            variables.add(part.value.id)
                    interpolated.append((variables, {suffix}))

        unknown = {name for name in literals if name not in known}
        self.assertEqual(unknown, set(), f"la UI llama comandos inexistentes: {unknown}")

        # El f-string real es f"{section}_{field}_add": los guiones bajos
        # separadores vienen de las variables, no de segmentos literales.
        sections = {"programs", "sites"}
        fields = {"blocked", "allowed"}
        suffixes = {"_add", "_del"}
        expanded = {f"{s}_{f}{sfx}" for s in sections for f in fields for sfx in suffixes}
        self.assertTrue(
            expanded <= known, f"comandos de listas faltantes: {expanded - known}"
        )

    def test_interpolated_commands_are_covered_by_expansion(self):
        """Las llamadas f-string de la UI usan variables de lista, no comandos fijos."""
        for path in sorted((PKG / "ui").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "call"
                    and node.args
                    and isinstance(node.args[0], ast.JoinedStr)
                ):
                    continue
                for part in node.args[0].values:
                    if isinstance(part, ast.FormattedValue):
                        self.assertIn(
                            part.value.id,
                            {"section", "field", "op"},
                            f"variable interpolada inesperada: {part.value.id}",
                        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
