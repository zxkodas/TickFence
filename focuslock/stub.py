"""Stub de IFEO. Deliberadamente autonomo: lo ejecuta Windows fuera del paquete
y tiene que arrancar aunque focuslock no sea importable.

Cuando Windows encuentra un .exe bloqueado, lanza este stub con la linea de
comandos original pegada atras. Mostramos el aviso y salimos: el programa
nunca arranca.

El stub lee el estado solo para saber cuantas Lecturas faltan y en que idioma
escribir. Si no puede leerlo, muestra un texto generico en ingles en vez de
fallar.

POR QUE LAS TABLAS ESTAN DUPLICADAS: no se importa focuslock.i18n porque este
archivo tiene que arrancar sin el paquete. Las dos copias se comparan en
tests/test_i18n.py, asi que no pueden separarse sin que el test avise.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

MB_OK = 0x00000000
MB_ICONWARNING = 0x00000030
MB_TOPMOST = 0x00040000

EN = {
    "title": "TickFence - lock active",
    "header": "This program is blocked by TickFence.",
    "left_one": "1 Reading left in TickTick and it unlocks by itself.",
    "left_many": "{n} Readings left in TickTick and it unlocks by itself.",
    "done": (
        "You finished the Readings. Open TickFence so it picks up the change "
        "(it can take up to half a minute)."
    ),
    "unknown": "Finish the pending Readings in TickTick to unlock.",
    "blocked": "Blocked program: {name}",
    "emergency": (
        "To unlock without finishing the Readings: open TickFence from the "
        "Desktop shortcut, or run:\n"
        "    python -m focuslock gui\n"
        "and write your commitment (300 words, 5 minutes of real writing)."
    ),
}

ES = {
    "title": "TickFence - bloqueo activo",
    "header": "Este programa está bloqueado por TickFence.",
    "left_one": "Te falta 1 Lectura en TickTick y se desbloquea solo.",
    "left_many": "Te faltan {n} Lecturas en TickTick y se desbloquea solo.",
    "done": (
        "Ya completaste las Lecturas. Abrí TickFence para que tome el cambio "
        "(tarda hasta medio minuto)."
    ),
    "unknown": "Terminá las Lecturas pendientes en TickTick para desbloquear.",
    "blocked": "Programa bloqueado: {name}",
    "emergency": (
        "Para desbloquear sin completar las Lecturas: abrí TickFence desde el "
        "acceso directo del Escritorio, o con:\n"
        "    python -m focuslock gui\n"
        "y escribí tu compromiso (300 palabras, 5 minutos de escritura real)."
    ),
}


def _target(argv: list[str]) -> str:
    for arg in reversed(argv):
        if arg.startswith("--") or not arg:
            continue
        return os.path.basename(arg)
    return ""


def _state() -> dict:
    """Lee state.json para required/credits y el idioma. Nunca toca el token.

    La UI no siempre esta abierta, asi que leerlo desde el stub es la unica
    forma de que el aviso diga algo util.
    """
    # Sin imports del paquete: Windows ejecuta este archivo suelto. ProgramData
    # manda primero (los tests lo usan para redirigir el estado en Linux tb).
    base = os.environ.get("ProgramData")
    if base:
        path = Path(base) / "TickFence" / "state.json"
    elif sys.platform.startswith("win"):
        path = Path(r"C:\ProgramData") / "TickFence" / "state.json"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(
            Path.home() / ".local" / "share"
        )
        path = Path(base) / "TickFence" / "state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def build_message(name: str, language: str = "en") -> str:
    # Idioma desconocido cae en ingles: el aviso se muestra justo cuando algo
    # ya va mal, no es el momento de que falle por una config rare.
    t = ES if language == "es" else EN

    data = _state()
    required = data.get("required")
    credits = data.get("credits")

    try:
        required = int(required)
    except (TypeError, ValueError):
        required = 0
    try:
        credits = int(credits)
    except (TypeError, ValueError):
        credits = 0

    lines = [t["header"], ""]

    if required > 0:
        faltan = max(0, required - credits)
        if faltan == 1:
            lines.append(t["left_one"])
        elif faltan > 1:
            lines.append(t["left_many"].format(n=faltan))
        else:
            lines.append(t["done"])
    else:
        lines.append(t["unknown"])

    lines.append("")
    if name:
        lines.append(t["blocked"].format(name=name))
        lines.append("")

    lines.append(t["emergency"])
    return "\n".join(lines)


def main() -> int:
    argv = sys.argv[1:]
    if "--ifeo-stub" not in argv:
        return 0
    name = _target([a for a in argv if a != "--ifeo-stub"])
    idioma = _state().get("language", "en")
    titulo = ES["title"] if idioma == "es" else EN["title"]
    texto = build_message(name, idioma if isinstance(idioma, str) else "en")
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                texto,
                titulo,
                MB_OK | MB_ICONWARNING | MB_TOPMOST,
            )
        except Exception:
            pass
    else:
        _notify_linux(titulo, texto)
    return 0


def _notify_linux(title: str, text: str) -> None:
    """Aviso en Linux: notify-send, si no zenity, si no stderr. Nunca falla."""
    import shutil
    import subprocess

    try:
        if shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", "-u", "critical", title, text[:2000]],
                timeout=5,
                check=False,
            )
            return
        if shutil.which("zenity"):
            subprocess.run(
                ["zenity", "--warning", f"--title={title}", f"--text={text[:4000]}"],
                timeout=30,
                check=False,
            )
            return
    except Exception:
        pass
    try:
        sys.stderr.write(f"[{title}] {text}\n")
        sys.stderr.flush()
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
