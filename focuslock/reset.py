"""Devuelve TickFence al estado de fábrica.

Deja todo desbloqueado y limpio, para empezar de cero: sin créditos, sin
lectura base, sin ciclo de bloqueo activo y sin claves IFEO.     python -m focuslock reset

Si el servicio está corriendo hay que DETENERLO antes de escribir, porque sino
pisa el state.json con lo que tiene en memoria. Por eso el comando intenta
pararlo primero y, si no puede, verifica al final si lo que escribió llegó a
quedar: si no quedó, lo dice y sale con codigo de error en vez de decir "Listo".

Detener el servicio necesita Administrador (Windows) o ser el dueño de la
unidad systemd (Linux, sin sudo). Sin el, el reset se puede hacer
igual pero el estado no se sostiene: se avisa.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .config import DEFAULTS, Config
from .store import DEFAULT_STATE, Store


def reset(config_path: Path | None = None, state_path: Path | None = None) -> dict:
    from . import paths

    cfg_path = config_path or (paths.program_data() / "config.json")
    st_path = state_path or (paths.program_data() / "state.json")

    # --- config: lista de bloqueados vacía, arranque sin bloquear ---
    cfg = Config(cfg_path)
    cfg.load()
    backup_cfg = cfg_path.with_suffix(".json.bak")
    if cfg_path.exists():
        backup_cfg.write_text(
            cfg_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    cfg.set("programs", {"blocked": [], "allowed": list(DEFAULTS["programs"]["allowed"]),
                         "use_ifeo": DEFAULTS["programs"]["use_ifeo"]})
    cfg.set("general", {"start_locked": False})
    cfg.save()

    # --- estado: desbloqueado, contador en cero, línea base limpia ---
    st = Store(st_path)
    st.read()
    backup_st = st_path.with_suffix(".json.bak")
    if st_path.exists():
        backup_st.write_text(st_path.read_text(encoding="utf-8"), encoding="utf-8")

    st.update(
        locked=False,
        credits=0,
        required=2,
        lock_started=0.0,
        unlock_until=0.0,
        unlock_reason="",
        lectura_status={},
        lectura_seeded=False,
        last_poll=0.0,
        last_error="",
        # historial limpio: el registro de emergency no se borra al reset
        server_port=st.get("server_port", 0),
        ticktick_token=st.get("ticktick_token", ""),
        server_token=st.get("server_token", ""),
        emergencies=[],
        block_events=[],
    )
    st.write()

    return {
        "config": str(cfg_path),
        "config_backup": str(backup_cfg),
        "state": str(st_path),
        "state_backup": str(backup_st),
        "blocked": [],
        "locked": False,
        "credits": 0,
    }


def _detener_servicio(service) -> tuple[bool, str]:
    """Deja el servicio efectivamente parado. Devuelve (parado, motivo).

    service.stop() NO lanza excepcion cuando no puede parar el servicio: se
    limita a agotar el tiempo de espera y devuelve. Por eso no alcanza con
    llamarlo: hay que preguntar despues si quedo parado. Un reset con el
    servicio vivo escribe contra un archivo que alguien mas sobreescribe, y el
    estado perdi siempre.
    """
    if not service.is_running():
        return True, ""
    try:
        service.stop()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    # La pregunta que importa, no la excepcion.
    if service.is_running():
        return False, "el servicio sigue en RUNNING"
    return True, ""


def main() -> int:
    from . import ifeo, service
    from .paths import program_data

    cfg_path = program_data() / "config.json"
    st_path = program_data() / "state.json"

    # Limpiar el registro ANTES de reiniciar el servicio: si el servicio está
    # corriendo, vuelve a aplicar IFEO y reintroduce las claves.
    try:
        before = ifeo.list_blocked()
    except Exception:
        before = []
    for exe in before:
        ifeo.clear(exe)
    if before:
        print(f"  liberadas {len(before)} claves IFEO: {', '.join(before)}")

    parado, motivo = _detener_servicio(service)
    if not parado:
        print(f"  el servicio sigue corriendo: {motivo}")
        print()
        print("  Sin pararlo, el reset NO sirve: el servicio tiene el estado en")
        print("  memoria y sobreescribe el archivo enseguida. Se pierde siempre.")
        print()
        if sys.platform.startswith("win"):
            print("  Corré esto en PowerShell como Administrador:")
            print()
            print("      Stop-Service TickFenceSvc")
            print("      python -m focuslock reset")
            print("      Start-Service TickFenceSvc")
        else:
            print("  Corré esto (sin sudo):")
            print()
            print("      systemctl --user stop tickfence")
            print("      python -m focuslock reset")
            print("      systemctl --user start tickfence")
        print()
        print("  No se escribe nada ahora, para no dejar el archivo a medias.")
        return 2

    if service.is_running() is False and not service._is_installed():
        print("  el servicio no está instalado")

    result = reset(cfg_path, st_path)

    # Con el servicio parado el estado escrito ya no se pisa: no hace falta
    # adivinar con una carrera de lecturas.
    if service._is_installed():
        try:
            service.start()
            if service.is_running():
                print("  servicio reiniciado")
            else:
                print("  el servicio no quedo en RUNNING")
                print("  el estado esta escrito, pero la proteccion esta caida")
                print("  hasta que lo arranques vos.")
        except Exception as exc:  # noqa: BLE001
            print(f"  no se pudo arrancar el servicio de nuevo: {exc}")
            print("  el estado quedo escrito; el servicio no lo toma hasta")
            print("  que lo arranques vos.")

    print()
    print(f"  config    : {result['config']}  (respaldo: {result['config_backup']})")
    print(f"  estado    : {result['state']}  (respaldo: {result['state_backup']})")
    print("  bloqueados: (ninguno)")
    print("  bloqueado : False | créditos: 0")
    print()
    print("Listo. Abrí TickFence y usá 'Activar bloqueo' cuando quieras probar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
