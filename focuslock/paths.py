"""Rutas y constantes globales compartidas entre el servicio y la GUI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "TickFence"
APP_VERSION = "1.2.0"

SERVICE_NAME = "TickFenceSvc"
SERVICE_DISPLAY_NAME = "TickFence Enforcement Service"
PIPE_NAME = r"\\.\pipe\TickFence"

IFEO_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"

# Extensiones de navegador que sirve la app para instalar.
EXTENSION_IDS = {
    "chrome": "tickfence-blocker",
    "firefox": "tickfence-blocker",
}


def program_data() -> Path:
    if is_windows():
        base = os.environ.get("ProgramData") or r"C:\ProgramData"
        return Path(base) / APP_NAME
    # ponytail: XDG primero, ~/.local/share fallback. Sin root, sin HKLM.
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def runtime_dir() -> Path:
    """Donde vive el socket IPC en Linux (XDG_RUNTIME_DIR o /tmp)."""
    if is_windows():
        return program_data()
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(base) / APP_NAME.lower()


def socket_path() -> Path:
    if is_windows():
        return Path(PIPE_NAME)
    # ponytail: socket Unix en vez de named pipe. Mismo protocolo JSON.
    return runtime_dir() / "tickfence.sock"


def app_data() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_NAME


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_elevated() -> bool:
    """True si el proceso actual corre como Administrador/root."""
    if is_windows():
        import ctypes

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False
