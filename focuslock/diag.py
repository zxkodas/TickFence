"""Diagnóstico del servicio TickFence.

Windows: estado del servicio + log de eventos (powershell/sc.exe).
Linux: estado de la unidad systemd de usuario + journal.
"""
from __future__ import annotations

import subprocess
import sys
import time


def run_ps(script: str) -> str:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception as exc:  # noqa: BLE001
        return f"no se pudo ejecutar: {exc}"


def run_cmd(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return result.stdout.strip() or result.stderr.strip() or "(sin salida)"
    except Exception as exc:  # noqa: BLE001
        return f"no se pudo ejecutar: {exc}"


def main() -> int:
    from .paths import SERVICE_DISPLAY_NAME, SERVICE_NAME

    if not sys.platform.startswith("win"):
        print("=== unidad systemd ===")
        print(run_cmd(["systemctl", "--user", "status", "tickfence", "--no-pager"]))
        print()
        print("=== journal (últimas 30 líneas) ===")
        print(run_cmd(["journalctl", "--user", "-u", "tickfence", "--no-pager", "-n", "30"]))
        print()
        print("=== socket ===")
        from .paths import socket_path

        print(str(socket_path()), "existe:" , socket_path().exists())
        return 0

    print("=== estado ===")
    print(run_ps(f"sc.exe query {SERVICE_NAME}"))

    print()
    print("=== configuracion ===")
    print(run_ps(f"sc.exe qc {SERVICE_NAME}"))

    print()
    print("=== eventos del servicio (Application y System) ===")
    for log in ("Application", "System"):
        print(f"--- {log} ---")
        print(
            run_ps(
                f"Get-WinEvent -FilterHashtable "
                f"@{{LogName='{log}'; StartTime=(Get-Date).AddMinutes(-20)}} "
                f"-ErrorAction SilentlyContinue | "
                f"Where-Object {{ $_.Message -like '*{SERVICE_DISPLAY_NAME}*' -or "
                f"$_.Message -like '*{SERVICE_NAME}*' -or "
                f"$_.ProviderName -like '*Service*Control*' }} | "
                f"Select-Object -First 12 | "
                f"Format-List TimeCreated, Id, ProviderName, Message"
            )
        )
        print()

    print("=== errores recientes de Python en el log de aplicacion ===")
    print(
        run_ps(
            "Get-WinEvent -FilterHashtable "
            "@{LogName='Application'; Id=1000; StartTime=(Get-Date).AddMinutes(-20)} "
            "-ErrorAction SilentlyContinue | Select-Object -First 5 | "
            "Format-List TimeCreated, Message"
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
