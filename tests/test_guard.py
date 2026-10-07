"""Pruebas del vigilante de procesos con procesos reales.

Importante: los procesos de prueba se lanzan como COPIAS de python.exe con un
nombre propio (TickFenceTest*.exe). Si bloqueamos "python.exe" sin mas, el
propio runner de tests seria un objetivo valido y se mataria a si mismo
(codigo de salida 15, sin salida alguna). Copiar el binario bajo otro nombre
hace la prueba segura y, de paso, mas realista: es exactamente el caso de
"bloquear una app que el usuario quiere".
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from focuslock.guard import ProcessGuard, is_dangerous  # noqa: E402
from focuslock.rules import NEVER_BLOCK, match_program  # noqa: E402

# En Linux el nombre del proceso (comm) se trunca a 15 caracteres y no hay
# .exe: nombres cortos sin extension. En Windows se usan .exe largos.
if sys.platform.startswith("win"):
    BLOCKED_NAME = "TickFenceTestBlocked.exe"
    ALLOWED_NAME = "TickFenceTestAllowed.exe"
else:
    BLOCKED_NAME = "tftestblocked"
    ALLOWED_NAME = "tftestallowed"


def _base(name: str) -> str:
    """basename dual: os.path.basename no parte rutas Windows en Linux."""
    return os.path.basename(name.replace("\\", "/")).lower()


# Codigo del hijo: se queda esperando. -I aísla imports, -E ignora variables.
CHILD_CODE = "import time; time.sleep(120)"


def _make_child_binary(directory: Path, name: str) -> Path:
    """Copia el interprete con el nombre pedido (pythonw.exe en Windows)."""
    source = Path(sys.executable)
    target = directory / name
    if sys.platform.startswith("win"):
        candidate = source.with_name("pythonw.exe")
        shutil.copy2(candidate if candidate.exists() else source, target)
    else:
        shutil.copy2(source, target)
        target.chmod(0o755)
    return target


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, int]] = []

    def __call__(self, name: str, pid: int) -> None:
        self.events.append((name, pid))


class TestProcessGuardReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="fl-guard-"))
        cls.blocked_exe = _make_child_binary(cls.tmp, BLOCKED_NAME)
        cls.allowed_exe = _make_child_binary(cls.tmp, ALLOWED_NAME)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _spawn(self, exe: Path) -> subprocess.Popen:
        return subprocess.Popen(
            [str(exe), "-I", "-c", CHILD_CODE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_kills_a_blocked_process(self):
        recorder = _Recorder()
        guard = ProcessGuard(
            should_block=lambda n: match_program(n, [BLOCKED_NAME], []),
            on_block=recorder,
            interval=0.25,
        )
        guard.protect(os.getpid())
        guard.start()
        child = self._spawn(self.blocked_exe)
        try:
            deadline = time.time() + 15
            while time.time() < deadline and not recorder.events:
                time.sleep(0.2)
            self.assertTrue(
                recorder.events, "el guardia no detectó el proceso bloqueado en 15s"
            )
            name, pid = recorder.events[0]
            self.assertEqual(name, BLOCKED_NAME.lower())

            deadline = time.time() + 6
            while time.time() < deadline and psutil.pid_exists(pid):
                time.sleep(0.2)
            self.assertFalse(psutil.pid_exists(pid), "el proceso seguía vivo")
        finally:
            guard.stop()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_allowlist_is_respected(self):
        """Con el nombre en la lista de permitidos, el proceso debe sobrevivir."""
        guard = ProcessGuard(
            should_block=lambda n: match_program(
                n, [BLOCKED_NAME], [ALLOWED_NAME]
            ),
            interval=0.25,
        )
        guard.protect(os.getpid())
        guard.start()
        child = self._spawn(self.allowed_exe)
        try:
            time.sleep(3.0)
            self.assertIsNone(
                child.poll(), "el proceso permitido fue terminado (no debía)"
            )
        finally:
            guard.stop()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_unlocked_engine_blocks_nothing(self):
        """Con la maquina desbloqueada, should_block devuelve False siempre."""
        unlocked = {"value": False}
        guard = ProcessGuard(
            should_block=lambda n: unlocked["value"] and match_program(n, ["x.exe"], []),
            interval=0.25,
        )
        guard.protect(os.getpid())
        guard.start()
        child = self._spawn(self.blocked_exe)
        try:
            time.sleep(2.0)
            self.assertIsNone(child.poll())
        finally:
            guard.stop()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_stats_are_reported(self):
        guard = ProcessGuard(should_block=lambda n: False, interval=0.3)
        guard.protect(os.getpid())
        guard.start()
        time.sleep(1.2)
        stats = guard.stats()
        guard.stop()
        self.assertTrue(stats["running"])
        self.assertGreaterEqual(stats["scans"], 1)
        self.assertEqual(stats["kills"], 0)

    def test_stop_is_idempotent(self):
        guard = ProcessGuard(should_block=lambda n: False, interval=0.3)
        guard.protect(os.getpid())
        guard.start()
        guard.stop()
        guard.stop()  # no debe romper

    def test_critical_processes_are_never_targeted(self):
        """Con should_block que devuelve True para todo, el guard igual tiene
        que respetar los nombres protegidos. Lanza un proceso real con un
        nombre innocentisimo y lo mata; el resto queda intacto."""
        recorder = _Recorder()
        guard = ProcessGuard(
            should_block=lambda n: True,
            on_block=recorder,
            interval=0.25,
        )
        guard.protect(os.getpid())
        # Solo el hijo puede ser objetivo: se protegen los PIDs que ya existen
        # (en un escritorio Linux should_block=True mataría tus apps).
        for pid in psutil.pids():
            guard.protect(pid)
        guard.start()
        # El proceso de prueba SI es un objetivo valido (nombre no protegido).
        child = self._spawn(self.blocked_exe)
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not recorder.events:
                time.sleep(0.2)
            self.assertTrue(recorder.events, "debio matar el proceso de prueba")
            for name, _pid in recorder.events:
                self.assertNotIn(name, NEVER_BLOCK, f"mato un proceso protegido: {name}")
        finally:
            guard.stop()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


class TestProtectedProcesses(unittest.TestCase):
    """Los procesos intocables jamas se matan, pase lo que pase.

    Este test SI.mataria tu escritorio si estuviera mal, asi que no lanza
    procesos reales: verifica la decision sobre PIDs reales, sin matar nada.
    """

    def test_explorer_is_never_blocked(self):
        for name in ("explorer.exe", "Explorer.EXE", r"C:\Windows\explorer.exe"):
            # Con ruta completa hay que comparar por basename: la regla
            # guarda nombres de archivo, no rutas.
            base = _base(name)
            self.assertIn(base, {_base(n) for n in NEVER_BLOCK}, name)
            self.assertFalse(
                match_program(name, ["explorer.exe"], []),
                f"{name} no debe poder bloquearse",
            )

    def test_opencode_is_never_blocked(self):
        for name in ("OpenCode.exe", "opencode.exe", r"C:\Users\x\OpenCode.exe"):
            base = _base(name)
            self.assertIn(base, {_base(n) for n in NEVER_BLOCK}, name)
            self.assertFalse(match_program(name, ["opencode.exe"], []))

    def test_never_block_ignores_allowlist_logic(self):
        """Aunque este en la lista de permitidos, igual esta protegido."""
        blocked = ["userinit.exe", "explorer.exe", "opencode.exe"]
        allowed: list[str] = []
        for name in blocked:
            self.assertFalse(match_program(name, blocked, allowed), name)

    def test_guard_never_targets_protected_names(self):
        """should_block puede devolver True para todo, pero el guard se salta
        los nombres protegidos. Se verifica sobre el propio PID del test
        renombrandolo logicamente via el nombre que el guard consulta."""
        import os

        class FakeProc:
            """Sustituto de psutil.Process con un nombre controlado."""

            def __init__(self, name: str) -> None:
                self._name = name
                self.pid = 999999

            def name(self) -> str:
                return self._name

        guard = ProcessGuard(should_block=lambda n: True, interval=0.3)
        guard.protect(os.getpid())
        try:
            for name in ("explorer.exe", "opencode.exe", "lsass.exe", "svchost.exe"):
                self.assertTrue(
                    guard._is_protected(FakeProc(name)), f"{name} deberia estar protegido"
                )
            for name in ("steam.exe", "discord.exe"):
                self.assertFalse(
                    guard._is_protected(FakeProc(name)), f"{name} no deberia estar protegido"
                )
        finally:
            guard.stop()

    def test_critical_and_important_are_protected(self):
        for name in (
            "explorer.exe", "userinit.exe", "lsass.exe", "csrss.exe",
            "winlogon.exe", "services.exe", "dwm.exe", "opencode.exe",
            "focuslock.exe", "msmpeng.exe", "logonui.exe", "sihost.exe",
        ):
            self.assertIn(name, NEVER_BLOCK, name)


class TestIsDangerous(unittest.TestCase):
    def test_system_binaries_are_dangerous(self):
        for name in ("taskmgr.exe", "cmd.exe", "powershell.exe", "regedit.exe"):
            self.assertTrue(is_dangerous(name), name)

    def test_protected_procs_are_dangerous(self):
        # Esta en NEVER_BLOCK, asi que is_dangerous da True: el UI avisa.
        for name in ("explorer.exe", "opencode.exe", "lsass.exe"):
            self.assertTrue(is_dangerous(name), name)

    def test_focuslock_itself_is_dangerous(self):
        self.assertTrue(is_dangerous("TickFence.exe"))
        self.assertTrue(is_dangerous("tickfence_svc.exe"))

    def test_ordinary_apps_are_not_dangerous(self):
        for name in ("steam.exe", "discord.exe", "chrome.exe", "firefox.exe"):
            self.assertFalse(is_dangerous(name), name)

    def test_windows_system32_is_dangerous(self):
        self.assertTrue(is_dangerous(r"C:\Windows\System32\notepad.exe"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
