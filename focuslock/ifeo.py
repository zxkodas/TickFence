"""Capa dura de bloqueo: Image File Execution Options (HKLM) en Windows.

En Linux no hay IFEO: este módulo existe para que los imports no revienten,
pero no escribe nada (la capa dura ahí es el guard de procesos + el servicio
systemd). `sync()` devuelve el mismo dict para no romper a los llamadores.
"""
from __future__ import annotations

import sys

try:
    import winreg
    import winreg as _winreg  # noqa: F401  (alias explicito para el chequeo de tests)
    import win32con
    _WIN = sys.platform.startswith("win")
except ImportError:
    winreg = None  # type: ignore
    _winreg = None  # type: ignore
    win32con = None  # type: ignore
    _WIN = False

from . import paths
from .rules import norm_program

_VALUES = ("Debugger",)


def _subkey(exe: str) -> str:
    return f"{paths.IFEO_KEY}\\{exe}"


def _open_write(exe: str):
    return winreg.CreateKeyEx(
        winreg.HKEY_LOCAL_MACHINE,
        _subkey(exe),
        0,
        winreg.KEY_ALL_ACCESS,
    )


def _open_read(exe: str):
    return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _subkey(exe), 0, winreg.KEY_READ)


def _debugger_value(stub_command: str) -> str:
    r"""Construye el valor `Debugger` de IFEO.

    El valor es una linea de comandos: `"<stub>" <args>`. Windows le agrega
    detras la linea del programa original.

    OJO: si `stub_command` ya viene entrecomillado (que es lo normal, porque
    la ruta puede tener espacios), envolverlo otra vez produce

        ""C:\...\pythonw.exe" ...\stub.py"" --ifeo-stub

    que Windows no puede parsear. El programa no arranca y sale un error de
    "parametro no es correcto" en vez de nuestro aviso. Tiene que quedar
    entrecomillado una sola vez.
    """
    command = (stub_command or "").strip()
    if not command:
        raise ValueError("El comando del stub esta vacio.")
    if command.startswith('"'):
        return f"{command} --ifeo-stub"
    return f'"{command}" --ifeo-stub'


def set_blocker(exe: str, stub_command: str) -> None:
    """Marca `exe` como bloqueado apuntando a `stub_command`."""
    exe = norm_program(exe)
    if not exe:
        raise ValueError("Ejecutable invalido")
    value = _debugger_value(stub_command)
    if not _WIN:
        return  # sin IFEO en Linux: el guard es la capa dura
    with _open_write(exe) as key:
        for name in _VALUES:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def clear(exe: str) -> None:
    """Quita el bloqueo de `exe`. Silencioso si no existía."""
    exe = norm_program(exe)
    if not exe:
        return
    if not _WIN:
        return
    try:
        with _open_write(exe) as key:
            for value in _VALUES:
                try:
                    winreg.DeleteValue(key, value)
                except FileNotFoundError:
                    pass
        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, _subkey(exe))
        except OSError:
            pass
    except OSError:
        pass


def is_blocked(exe: str) -> bool:
    exe = norm_program(exe)
    if not exe or not _WIN:
        return False
    try:
        with _open_read(exe) as key:
            value, _ = winreg.QueryValueEx(key, "Debugger")
            return bool(value)
    except OSError:
        return False


def list_blocked() -> list[str]:
    """Todos los .exe que tienen una clave IFEO con Debugger apuntando a TickFence."""
    found: list[str] = []
    if not _WIN:
        return found
    try:
        root = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, paths.IFEO_KEY, 0, winreg.KEY_READ
        )
    except OSError:
        return found
    with root:
        index = 0
        while True:
            try:
                name = winreg.EnumKey(root, index)
                index += 1
            except OSError:
                break
            if not name.lower().endswith(".exe"):
                continue
            try:
                with winreg.OpenKey(root, name) as key:
                    value, _ = winreg.QueryValueEx(key, "Debugger")
                    if value and "focuslock" in str(value).lower() or "tickfence" in str(value).lower():
                        found.append(name)
            except OSError:
                continue
    return found


def sync(blocked: list[str], allowed: list[str], stub_command: str) -> dict:
    """Reconcilia IFEO con la configuración. Devuelve un resumen.

    `stub_command` vacio significa "solo limpiar": borra lo que sobre sin
    escribir nada nuevo. Es lo que usa el comando de emergencia.
    """
    want = {norm_program(p) for p in blocked} - {norm_program(p) for p in allowed}
    want.discard("")

    applied, removed, failed = [], [], []

    if stub_command:
        for exe in sorted(want):
            try:
                set_blocker(exe, stub_command)
                applied.append(exe)
            except OSError as exc:
                failed.append(f"{exe}: {exc}")

    for exe in list_blocked():
        if exe not in want:
            clear(exe)
            removed.append(exe)

    return {"applied": applied, "removed": removed, "failed": failed}
