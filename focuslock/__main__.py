"""Punto de entrada de la línea de comandos.

    python -m focuslock gui         abre la ventana (no necesita admin)
    python -m focuslock install     instala el servicio (Windows: admin, 1 vez)
    python -m focuslock console     motor en primer plano, para depurar
    python -m focuslock status      consulta el estado al servicio
    python -m focuslock uninstall   desinstala todo

El idioma sale de la config, igual que en la ventana. Ojo: leer la config
puede fallar si el servicio todavia no esta instalado (es justamente lo que
hace 'install'), asi que _set_lang_from_config nunca lanza.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from .i18n import set_lang, tr
from .paths import is_elevated, is_windows
from .rules import norm_program


def _set_lang_from_config() -> None:
    """Idioma del CLI. Si la config no esta, se queda en ingles."""
    try:
        from . import config as config_mod

        cfg = config_mod.instance()
        set_lang(cfg.get("general").get("language", "en"))
    except Exception:  # noqa: BLE001
        set_lang("en")


def _need_admin(action: str) -> None:
    if is_windows() and not is_elevated():
        print(tr("'{a}' needs administrator rights.").format(a=action), file=sys.stderr)
        print(tr("Close this and reopen it as administrator."), file=sys.stderr)
        sys.exit(3)
    # En Linux el servicio es systemd --user: no hace falta root ni sudo.


def _wait_for_service(seconds: float = 25.0) -> bool:
    from .ipc import IpcClient

    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            IpcClient(timeout=5).call("status")
            return True
        except Exception:
            time.sleep(1.0)
    return False


def cmd_install(args) -> int:
    _need_admin("install")
    from . import config as config_mod
    from . import ifeo
    from . import paths
    from .paths import APP_VERSION
    from .service import install as install_service

    print(f"TickFence {APP_VERSION} — {tr('install')}")
    print(f"  {tr('data in')}: {paths.program_data()}")

    paths.program_data().mkdir(parents=True, exist_ok=True)
    cfg = config_mod.instance()
    cfg.save()
    print(f"  config   : {cfg.path}")

    if getattr(sys, "frozen", False):
        print(f"  {tr('mode'):<8} : {tr('bundled executable')}")
    else:
        print(f"  {tr('mode'):<8} : {tr('source code')} ({sys.executable})")

    print(f"  {tr('installing the package for the service')}…")
    from .install_pkg import install as install_pkg

    if install_pkg() != 0:
        print(f"  ERROR: {tr('the service could not find the package')}.",
              file=sys.stderr)
        return 1

    print(f"  {tr('registering the service')}…")
    install_service()
    print(f"  {tr('starting the service')}…")

    if not _wait_for_service():
        print(f"  ERROR: {tr('the service did not respond')}.", file=sys.stderr)
        hint = ("journalctl --user -u tickfence --no-pager -n 30"
                if not is_windows()
                else f"{tr('Check the event viewer or try:')} python -m focuslock console")
        print(f"  {hint}", file=sys.stderr)
        return 1
    print(f"  {tr('service ready')}.")

    from .ipc import IpcClient

    client = IpcClient()
    if args.token:
        try:
            res = client.call("ticktick_set_token", token=args.token)
            if res.get("ok"):
                print(f"  token    : {tr('saved and encrypted')} "
                      f"({res.get('projects')} {tr('projects')})")
            else:
                print(f"  token    : ERROR {res.get('error')}", file=sys.stderr)
        except Exception as exc:
            print(f"  token    : ERROR {exc}", file=sys.stderr)

    from .daemon import stub_command
    if is_windows():
        print(f"  IFEO stub: {stub_command()}")
        blocked = ifeo.list_blocked()
        print(f"  IFEO     : {len(blocked)} {tr('executables blocked at the Windows level')}")
        if not blocked:
            print(f"  ({tr('none: with the machine unlocked the IFEO is clean')})")
    else:
        print(f"  guard    : proceso del servicio systemd (sin IFEO en Linux)")

    # Acceso desde Inicio/Escritorio e autoinicio: sin esto el ícono del área
    # de notificación no existe después de reiniciar y no hay forma de abrir
    # la app para desbloquear.
    print(f"  {tr('creating shortcuts')}…")
    try:
        from .shortcuts import install as install_shortcuts

        result = install_shortcuts()
        for path in result.get("shortcuts", []):
            print(f"    {tr('shortcut')}: {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {tr('WARNING')}: {tr('the shortcuts could not be created')}: {exc}")
        print(f"  {tr('The app still opens with:')} python -m focuslock gui")
    return 0


def cmd_uninstall(args) -> int:
    _need_admin("uninstall")
    from . import ifeo
    from . import paths as paths_mod
    from .service import uninstall as uninstall_service

    if is_windows():
        print(f"{tr('Removing IFEO blocks')}…")
        for exe in ifeo.list_blocked():
            ifeo.clear(exe)
            print(f"  {tr('cleared')}: {exe}")
    print(f"{tr('Stopping and removing the service')}…")
    uninstall_service()
    # Sin f-string: la barra invertida de la ruta va DENTRO de la expresion
    # tr(...), y eso es legal desde 3.12 (PEP 701) pero SyntaxError en 3.11.
    # El prefijo f tampoco hacia falta, tr() no interpola nada.
    if is_windows():
        print(tr("Done. You can delete C:\\ProgramData\\TickFence if you want to."))
    else:
        print(tr("Done. Data lives in {p}.").format(p=paths_mod.program_data()))
    return 0


def cmd_console(args) -> int:
    """Motor en primer plano, para depurar.

    Por seguridad el vigilante de procesos NO se levanta en este modo salvo que
    se pida explicitamente con --armar-guard. Levantar un killer de procesos
    contra la sesion interactiva del usuario desde una consola de desarrollo es
    exactamente como se te cae el escritorio.
    """
    from .service import run_console

    if is_windows() and not is_elevated():
        print("AVISO: sin permisos de administrador.")
        print("       Las claves IFEO no se pueden escribir y el bloqueo duro")
        print("       quedara desactivado. Usa 'install' desde una consola elevada.")
        print("")
    if not is_windows() and is_elevated():
        print("AVISO: corriendo como root con el guard armado matas procesos")
        print("       de TODOS los usuarios. Mejor sin sudo.")
        print("")

    if not getattr(args, "armar_guard", False):
        print("MODO SEGURO: el vigilante de procesos esta DESACTIVADO.")
        print("  Estaria matando programas de tu sesion de escritorio.")
        print("  Para probarlo a proposito:")
        print("     python -m focuslock console --armar-guard")
        print("")
    return run_console(arm_guard=bool(getattr(args, "armar_guard", False)))


def cmd_gui(args) -> int:
    from .ui import main

    return main()


def cmd_doctor(args) -> int:
    """Diagnostico: responde el servicio, hay IFEO, estaticktock conectado."""
    from .ipc import IpcClient

    client = IpcClient()
    try:
        info = client.call("install_ready")
    except Exception as exc:  # noqa: BLE001
        print(f"El servicio NO responde: {exc}")
        return 1

    print(f"{tr('Service responding')}.")
    print(f"  pid           {info.get('service_pid')}")
    print(f"  python        {info.get('python')}")
    print(f"  config        {info.get('config_path')}")
    print(f"  {tr('state'):<14} {info.get('state_path')}")
    print(f"  {tr('HTTP port')} {info.get('port')}")
    print(f"  IFEO {tr('applied')} {len(info.get('ifeo_applied') or [])} "
          f"{tr('executables')}")
    print(f"  {tr('guard'):<14} {info.get('guard')}")
    print(f"  {tr('IFEO stub'):<14} {info.get('stub')}")
    print(f"  ticktick      {tr('configured') if info.get('ticktick_ok') else tr('NO TOKEN')}")
    try:
        st = client.call("status")
    except Exception as exc:  # noqa: BLE001
        print(f"  {tr('status failed')}: {exc}")
        return 1
    print(f"  {tr('current state')} "
          f"{tr('LOCKED') if st.get('locked') else tr('UNLOCKED')} "
          f"{st.get('credits')}/{st.get('required')}")
    if st.get("error"):
        print(f"  {tr('error')}: {st['error']}")
    return 0


def cmd_ifeo_reconcile(args) -> int:
    """Reconcilia las claves IFEO con la config. Funciona con el servicio parado.

    Es el escape de emergencia: si el servicio dejo claves de programas que ya
    no queres bloquear y no podés abrir la app, esto las limpia.
    """
    from . import ifeo
    from .config import Config
    from .paths import program_data

    cfg = Config(program_data() / "config.json")
    cfg.load()
    blocked = [norm_program(v) for v in cfg.get("programs").get("blocked", [])]
    allowed = [norm_program(v) for v in cfg.get("programs").get("allowed", [])]

    before = ifeo.list_blocked()
    print(f"  configurado : {', '.join(blocked) or '(nada)'}")
    print(f"  IFEO actual : {', '.join(before) or '(nada)'}")

    # sync con stub vacio: solo importa que quite lo que sobra.
    from .daemon import stub_command

    result = ifeo.sync(blocked, allowed, stub_command())
    after = ifeo.list_blocked()
    print(f"  aplicado    : {', '.join(result.get('applied', [])) or '-'}")
    print(f"  liberados   : {', '.join(result.get('removed', [])) or '-'}")
    if result.get("failed"):
        print(f"  fallaron    : {'; '.join(result['failed'])}")
    print(f"  IFEO final  : {', '.join(after) or '(nada)'}")
    return 0


def _safe(text: object) -> str:
    """Convierte a texto que la consola de Windows pueda imprimir.

    Los proyectos de TickTick traen emoji (📖Estudios) y cp1252 no los
    encodea: sin esto, `status` revienta con UnicodeEncodeError apenas el
    servicio responde.
    """
    value = str(text)
    encoding = getattr(sys.stdout, "encoding", None) or "cp1252"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


def cmd_status(args) -> int:
    from .ipc import IpcClient

    try:
        data = IpcClient().call("status")
    except Exception as exc:  # noqa: BLE001
        print(f"{tr('No service')}: {_safe(exc)}")
        return 1
    estado = tr("LOCKED") if data.get("locked") else tr("UNLOCKED")
    print(f"{estado}  ·  {data.get('credits')}/{data.get('required')} "
          f"{tr('Readings')}")
    print(f"  {tr('reason'):<12} : {_safe(data.get('reason') or '-')}")
    print(f"  {tr('pending'):<12} : {sum((data.get('modules') or {}).values())}")
    print(f"  IFEO         : {len(data.get('ifeo', []))} {tr('executables')}")
    print(f"  {tr('server'):<12} : http://127.0.0.1:{data.get('port')}/state")
    if data.get("error"):
        print(f"  {tr('error'):<12} : {_safe(data['error'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="focuslock", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="instala el servicio (admin)")
    p_install.add_argument("--token", help="token de TickTick (tp_...) para configurarlo de una")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="desinstala (admin)")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_console = sub.add_parser(
        "console",
        help="motor en primer plano (vigilante apagado salvo --armar-guard)",
    )
    p_console.add_argument(
        "--armar-guard",
        action="store_true",
        help="activa el vigilante de procesos. MATA PROGRAMAS de tu sesion.",
    )
    p_console.set_defaults(func=cmd_console)

    p_daemon = sub.add_parser(
        "daemon",
        help="motor con guard armado (lo usa systemd, no lo corras a mano)",
    )
    p_daemon.set_defaults(func=lambda a: __import__(
        "focuslock.service", fromlist=["run_console"]).run_console(arm_guard=True))

    p_gui = sub.add_parser("gui", help="abre la ventana")
    p_gui.set_defaults(func=cmd_gui)

    p_status = sub.add_parser("status", help="estado actual")
    p_status.set_defaults(func=cmd_status)

    p_doctor = sub.add_parser("doctor", help="diagnostico completo del servicio")
    p_doctor.set_defaults(func=cmd_doctor)

    p_reconcile = sub.add_parser(
        "ifeo-reconcile",
        help="limpia claves IFEO huerfanas (funciona con el servicio parado)",
    )
    p_reconcile.set_defaults(func=cmd_ifeo_reconcile)

    p_reset = sub.add_parser(
        "reset",
        help="vuelve todo al estado de fabrica (desbloqueado, contadores en 0)",
    )
    p_reset.set_defaults(func=lambda a: __import__("focuslock.reset", fromlist=["main"]).main())

    if "--ifeo-stub" in (argv if argv is not None else sys.argv):
        from .stub import main as stub_main

        return stub_main()

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["gui"] if argv is None else argv)
    # Antes de correr el comando: el idioma sale de la config y los textos ya
    # estan armados con tr() para cuando se arme la ventana.
    _set_lang_from_config()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
