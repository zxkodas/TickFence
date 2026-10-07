"""Vigilante de procesos.

Complementa al IFEO: si algo logra arrancar igual (o si el IFEO fue
desactivado), este hilo lo detecta en menos de un segundo y lo termina.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

import psutil

from .rules import DEFAULT_DANGEROUS, NEVER_BLOCK, _stem, in_never_block, norm_program


class ProcessGuard:
    def __init__(
        self,
        should_block: Callable[[str], bool],
        on_block: Callable[[str, int], None] | None = None,
        interval: float = 0.8,
    ) -> None:
        self._should_block = should_block
        self._on_block = on_block
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._protected_pids = {os.getpid(), os.getppid()}
        self._self_names: set[str] = set()
        self._scans = 0
        self._kills = 0

    # -- ciclo de vida -----------------------------------------------------
    def protect(self, pid: int) -> None:
        """Marca un PID como intocable (instalador, stub, etc.)."""
        self._protected_pids.add(int(pid))

    def protect_name(self, name: str) -> None:
        """Marca un nombre de proceso como intocable.

        Necesario cuando el ejecutable bloqueado puede ser una copia de
        TickFence con otro nombre, o cuando queremos Cubrir el stub de IFEO
        que Windows lanza con el nombre original del programa.
        """
        normalized = norm_program(name)
        if normalized:
            self._self_names.add(normalized)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="process-guard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def stats(self) -> dict:
        return {"scans": self._scans, "kills": self._kills, "running": bool(self._thread and self._thread.is_alive())}

    # -- lógica ------------------------------------------------------------
    def _is_protected(self, proc: psutil.Process) -> bool:
        """Un proceso no se toca si:

        - su PID esta en la lista protegida (nosotros, el instalador, el stub)
        - su nombre es un proceso critico de Windows
        - no se puede inspeccionar (AccessDenied): preferimos no matar

        OJO: no se protect por "tener un ancestro protegido". El motor corre
        como servicio y casi todo lo que se abre en la sesion del usuario
        cuelga de explorer.exe; con esa regla ningun programa se bloquearia
        nunca. La proteccion es por PID explicito, no por linaje.
        """
        try:
            if proc.pid in self._protected_pids:
                return True
            name = (proc.name() or "").lower()
            if in_never_block(name) or _stem(name) in {_stem(n) for n in self._self_names}:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return True
        return False

    def _kill_tree(self, proc: psutil.Process) -> None:
        """Termina el proceso y sus hijos, respetando los PIDs protegidos.

        Importante: los hijos se filtrationan ANTES de matar. Una app bloqueada
        puede haber lanzado algo que si queremos proteger.
        """
        try:
            children = proc.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            children = []

        victims = [
            p
            for p in children
            if p.pid not in self._protected_pids
            and (p.name() or "").lower() not in self._self_names
        ]
        if proc.pid not in self._protected_pids:
            victims.append(proc)

        for victim in victims:
            try:
                victim.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if not victims:
            return
        _, alive = psutil.wait_procs(victims, timeout=1.5)
        for victim in alive:
            try:
                victim.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _scan(self) -> None:
        self._scans += 1
        blocked_now: dict[str, int] = {}
        try:
            procs = list(psutil.process_iter(["pid", "name"]))
        except psutil.Error:
            return

        for info in procs:
            name = (info.info.get("name") or "").lower()
            if not name or in_never_block(name):
                continue
            if _stem(name) in {_stem(n) for n in self._self_names}:
                continue
            if info.pid in self._protected_pids:
                continue
            # Filtro barato por nombre antes de hacer trabajo de psutil caro.
            if not self._should_block(name):
                continue
            try:
                proc = psutil.Process(info.pid)
                if self._is_protected(proc):
                    continue
                pid = proc.pid
                self._kill_tree(proc)
                self._kills += 1
                blocked_now[name] = pid
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, psutil.Error):
                continue

        if blocked_now and self._on_block:
            stamp = time.time()
            for name, pid in blocked_now.items():
                try:
                    self._on_block(name, pid)
                except Exception:
                    pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan()
            except Exception:
                pass
            self._stop.wait(self._interval)


def system_executables() -> set[str]:
    """Rutas de ejecutables del sistema, para la UI de advertencia."""
    import sys

    if not sys.platform.startswith("win"):
        # ponytail: en Linux no hay equiv. a System32 (en distros usrmerge
        # /sbin es symlink a /usr/bin: escanearlo marcaría steam/firefox como
        # "peligrosos"). Lo peligroso ya está en NEVER_BLOCK/DEFAULT_DANGEROUS.
        return set()
    roots = [os.environ.get("SystemRoot", r"C:\Windows")]
    found = set()
    for root in roots:
        for sub in ("System32", "SysWOW64"):
            base = os.path.join(root, sub)
            if not os.path.isdir(base):
                continue
            try:
                for name in os.listdir(base):
                    if name.lower().endswith(".exe"):
                        found.add(os.path.join(base, name).lower())
            except OSError:
                continue
    return found


def is_dangerous(exe: str) -> bool:
    """True si bloquear este ejecutable puede romper el sistema o la app."""
    raw = (exe or "").lower().replace("/", "\\")
    # Ruta de sistema Windows: peligrosa en ambos SO (el test la construye
    # en Linux y la regla puede viajar entre máquinas).
    if "system32\\" in raw or "syswow64\\" in raw:
        return True
    exe = norm_program(exe)
    if not exe:
        return True
    stem = _stem(exe)
    if any(_stem(n) == stem for n in NEVER_BLOCK):
        return True
    if any(_stem(n) == stem for n in DEFAULT_DANGEROUS):
        return True
    if exe.startswith("focuslock") or exe.startswith("tickfence"):
        return True
    return stem in {_stem(norm_program(p)) for p in system_executables()}
