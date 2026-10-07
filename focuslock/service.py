"""Motor con enforcement: servicio de Windows o servicio systemd de usuario.

Windows: corre como LocalSystem (TickFenceService) y arranca solo.
Linux: corre como unidad systemd --user (tickfence.service) con el guard
armado; el IFEO no existe ahí y la capa dura es el guard de procesos.
La GUI habla con ambos por el mismo protocolo (pipe vs socket Unix).
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time

from . import paths

try:
    import win32event
    import win32service
    import win32serviceutil
    _WIN = sys.platform.startswith("win")
except ImportError:
    win32event = None  # type: ignore
    win32service = None  # type: ignore
    win32serviceutil = None  # type: ignore
    _WIN = False

from .daemon import Engine


if _WIN:

    class TickFenceService(win32serviceutil.ServiceFramework):
        _svc_name_ = paths.SERVICE_NAME
        _svc_display_name_ = paths.SERVICE_DISPLAY_NAME
        _svc_description_ = (
            "Aplica el bloqueo de programas y sitios de TickFence. "
            "No lo detengas: si lo hacés, el bloqueo queda sin vigilar."
        )

        def __init__(self, args) -> None:
            super().__init__(args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._engine: Engine | None = None

        # -- ciclo de vida del servicio ---------------------------------------
        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)
            if self._engine:
                self._engine.stop()

        def SvcDoRun(self) -> None:
            try:
                self._engine = Engine()
                self._engine.start()
            except Exception as exc:  # noqa: BLE001
                # NO usar win32logging aca sin proteccion: pywin32 311+ ya no lo
                # distribuye, y el import se caia DENTRO del except, tapando el
                # error real con un ModuleNotFoundError. Un modulo que sirve para
                # registrar errores no puede ser la unica forma de reportarlos.
                try:
                    import win32logging  # type: ignore

                    win32logging.LogError(
                        0xE001, "TickFence no pudo arrancar: %s", str(exc)
                    )
                except Exception:  # noqa: BLE001
                    try:
                        sys.stderr.write(f"[tickfence] no pudo arrancar: {exc}\n")
                        sys.stderr.flush()
                    except Exception:  # noqa: BLE001
                        pass
                return
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            try:
                win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)
            finally:
                if self._engine:
                    self._engine.stop()


def _service_command() -> str | None:
    """Argumentos del servicio: NINGUNO, a propósito.

    `InstallService(pythonClassString=...)` ya escribe la clase en
    `HKLM\\...\\Services\\TickFenceSvc\\PythonClass`, y pythonservice.exe la lee
    de ahi. Si se le pasan `exeArgs`, ignora el registro, intenta interpretar
    los argumentos y el servicio muere con 1066 (ERROR_INVALID_FUNCTION).

    Por eso el unico valor correcto es None.
    """
    return None


def install(display: bool = True) -> None:
    """Registra y arranca el servicio (Windows) o la unidad systemd (Linux)."""
    if not _WIN:
        _install_linux(display=display)
        return
    already = _is_installed()
    if already:
        print("  el servicio ya existia, se reinstala…")
        uninstall()

    win32serviceutil.InstallService(
        pythonClassString=f"{__package__}.service.TickFenceService",
        serviceName=paths.SERVICE_NAME,
        displayName=paths.SERVICE_DISPLAY_NAME,
        startType=win32service.SERVICE_AUTO_START,
        exeArgs=_service_command(),
        description=(
            "Aplica el bloqueo de programas y sitios de TickFence. "
            "No lo detengas: si lo hacés, el bloqueo queda sin vigilar."
        ),
    )
    if display:
        start()


def reconcile_ifeo() -> list[str]:
    """Limpia las claves IFEO que no correspondan a la configuracion actual.

    Se puede correr con el servicio PARADO. Es el escape de emergencia: si el
    servicio dejo claves puestas y no podés abrir la interfaz para limpiarlas,
    esto las reconcilia contra el archivo de configuracion.
    """
    from . import ifeo
    from .config import Config
    from .paths import program_data

    cfg = Config(program_data() / "config.json")
    cfg.load()  # fuerza la lectura del disco
    programs = cfg.get("programs")

    try:
        if not programs.get("use_ifeo", True):
            released = []
            for exe in ifeo.list_blocked():
                ifeo.clear(exe)
                released.append(exe)
            return released
        # sync() ya borra lo que no este en la lista.
        result = ifeo.sync(
            programs.get("blocked", []), programs.get("allowed", []), ""
        )
        return result.get("removed", [])
    finally:
        ifeo.list_blocked()


def _is_installed() -> bool:
    if not _WIN:
        return _unit_path().exists()
    try:
        win32service.OpenService(
            win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT),
            paths.SERVICE_NAME,
            win32service.SERVICE_QUERY_STATUS,
        )
        return True
    except Exception:
        return False


def is_running() -> bool:
    """El servicio esta arrancado ahora.

    Lo necesita reset: sin esto no se puede saber si el estado que se acaba de
    escribir va a sobrevivir o lo va a pisar el servicio con lo que tiene en
    memoria.
    """
    if not _WIN:
        return _systemctl("is-active", "--quiet", _UNIT) == 0
    if not _is_installed():
        return False
    try:
        handle = win32service.OpenService(
            win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT),
            paths.SERVICE_NAME,
            win32service.SERVICE_QUERY_STATUS,
        )
        return win32service.QueryServiceStatus(handle)[1] == win32service.SERVICE_RUNNING
    except Exception:
        return False


def start(timeout: float = 20.0) -> bool:
    """Arranca el servicio y espera a que quede en RUNNING.

    StartService es de win32service, no de win32api. Ademas hay que esperar:
    la llamada vuelve apenas se acepta el arranque, no cuando termino de
    levantar, y la app necesita el pipe listo para poder hablar con el.
    """
    if not _WIN:
        if _systemctl("start", _UNIT) != 0:
            raise RuntimeError("No se pudo arrancar tickfence.service")
        return _wait_active(timeout)
    handle = win32service.OpenService(
        win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT),
        paths.SERVICE_NAME,
        win32service.SERVICE_START | win32service.SERVICE_QUERY_STATUS,
    )
    try:
        if win32service.QueryServiceStatus(handle)[1] != win32service.SERVICE_STOPPED:
            return True
        try:
            # Firma real: StartService(handle, serviceStartArgs) -> 2 posicionales.
            win32service.StartService(handle, None)
        except Exception as exc:
            if getattr(exc, "winerror", None) != 1056:  # ya estaba arrancando
                raise

        deadline = time.time() + timeout
        while time.time() < deadline:
            state = win32service.QueryServiceStatus(handle)[1]
            if state == win32service.SERVICE_RUNNING:
                return True
            if state == win32service.SERVICE_STOPPED:
                raise RuntimeError("El servicio se detuvo apenas arrancó.")
            time.sleep(0.25)
        raise RuntimeError(f"El servicio no quedó en RUNNING en {timeout:.0f}s.")
    finally:
        win32service.CloseServiceHandle(handle)


def stop(timeout: float = 15.0) -> None:
    """Detiene el servicio si está corriendo. Silencioso si ya está parado."""
    if not _WIN:
        _systemctl("stop", _UNIT)
        return
    try:
        handle = win32service.OpenService(
            win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT),
            paths.SERVICE_NAME,
            win32service.SERVICE_STOP | win32service.SERVICE_QUERY_STATUS,
        )
    except Exception:
        return
    try:
        if win32service.QueryServiceStatus(handle)[1] == win32service.SERVICE_STOPPED:
            return
        try:
            win32service.ControlService(handle, win32service.SERVICE_CONTROL_STOP)
        except Exception:
            return
        deadline = time.time() + timeout
        while time.time() < deadline:
            if win32service.QueryServiceStatus(handle)[1] == win32service.SERVICE_STOPPED:
                return
            time.sleep(0.25)
    finally:
        win32service.CloseServiceHandle(handle)


# Servicios de versiones anteriores del nombre. Tras un rebrandeo el viejo
# queda corriendo y bloquea la instalacion nueva, pero uninstall() solo conoce
# el nombre actual: por eso se limpian explicitamente.
_NOMBRES_ANTIGUOS = ("FocusLockSvc",)


def _esta_registrado(nombre: str) -> bool:
    """True si existe un servicio con ese nombre en el registro de Windows."""
    try:
        win32service.OpenService(
            win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT),
            nombre,
            win32service.SERVICE_QUERY_STATUS,
        ).Close()
        return True
    except Exception:
        return False


def _parar_y_borrar(nombre: str) -> bool:
    try:
        win32serviceutil.RemoveService(nombre)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  no se pudo borrar {nombre}: {exc}", file=sys.stderr)
        return False


def uninstall() -> None:
    """Detiene el servicio, lo borra y limpia las claves IFEO (Windows).

    En Linux detiene y borra la unidad systemd de usuario. No hay IFEO:
    `ifeo.clear` es no-op ahí y el guard muere con el proceso.
    """
    if not _WIN:
        _uninstall_linux()
        try:
            from . import shortcuts

            shortcuts.uninstall()
        except Exception:
            pass
        return
    # Servicios de versiones anteriores del nombre. Tras un rebrandeo el viejo
    # queda corriendo: ocupa pythonservice.exe y el puerto del servidor HTTP, y
    # la instalacion nueva falla con "Acceso denegado" y "WinError 10048" sin
    # que se entienda por que. Hay que limpiarlo tambien.
    for anterior in _NOMBRES_ANTIGUOS:
        if anterior != paths.SERVICE_NAME and _esta_registrado(anterior):
            print(f"  queda el servicio de una version anterior: {anterior}")
            _parar_y_borrar(anterior)

    if _is_installed():
        stop()
        win32serviceutil.RemoveService(paths.SERVICE_NAME)

    # Accesos directos: sin esto queda uno que no abre nada.
    try:
        from . import shortcuts

        shortcuts.uninstall()
    except Exception:
        pass

    # Aunque el servicio ya no exista, puede haber claves IFEO huerfanas.
    try:
        from . import ifeo

        released = []
        for exe in ifeo.list_blocked():
            ifeo.clear(exe)
            released.append(exe)
        if released:
            print(f"  liberadas {len(released)} claves IFEO: {', '.join(released)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  no se pudieron limpiar las claves IFEO: {exc}", file=sys.stderr)


def _service_args_look_right() -> bool:
    """La clase se registra en el registro, no en la linea de comandos."""
    return _service_command() is None


# ---------------------------------------------------------------------------
# Backend Linux: unidad systemd de usuario. Sin root, sin HKLM.
# ---------------------------------------------------------------------------
_UNIT = "tickfence.service"


def _unit_path():
    from pathlib import Path

    base = __import__("os").environ.get("XDG_CONFIG_HOME") or str(
        Path.home() / ".config"
    )
    return Path(base) / "systemd" / "user" / _UNIT


def _systemctl(*args: str) -> int:
    try:
        return subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            timeout=30,
        ).returncode
    except Exception:
        return 1


def _unit_text() -> str:
    exe = sys.executable
    return f"""[Unit]
Description=TickFence Enforcement Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={exe} -m focuslock daemon
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""


def _wait_active(timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _systemctl("is-active", "--quiet", _UNIT) == 0:
            return True
        time.sleep(0.5)
    raise RuntimeError(f"El servicio no quedó activo en {timeout:.0f}s.")


def _install_linux(display: bool = True) -> None:
    unit = _unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(_unit_text(), encoding="utf-8")
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", _UNIT)
    if display:
        _wait_active(20.0)
        print(f"  unidad    : {unit}")
        print("  estado    : systemctl --user status tickfence")


def _uninstall_linux() -> None:
    _systemctl("disable", "--now", _UNIT)
    try:
        _unit_path().unlink()
    except OSError:
        pass
    _systemctl("daemon-reload")


def run_console(arm_guard: bool = False) -> int:
    """Ejecuta el motor en primer plano (para depurar).

    arm_guard=False deja el vigilante de procesos apagado. Es lo correcto por
    defecto: este modo corre en la sesion del usuario, y un killer de procesos
    activo ahi se lleva por delante el escritorio, el explorador de archivos y
    todo lo que estes usando.
    """
    engine = Engine(arm_guard=arm_guard)
    engine.start()
    print(
        f"  guard   : {'ARMADO (mata procesos)' if arm_guard else 'desactivado (modo seguro)'}",
        flush=True,
    )
    print(f"TickFence motor en marcha. Ctrl+C para salir.", flush=True)
    if paths.is_windows():
        print(f"  pipe  : {paths.PIPE_NAME}", flush=True)
    else:
        print(f"  socket: {paths.socket_path()}", flush=True)
    print(f"  estado: http://127.0.0.1:{engine.store.get('server_port', 0)}/state", flush=True)
    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        print("\nDeteniendo…")
    finally:
        engine.stop()
    return 0


if __name__ == "__main__":
    if not _WIN:
        raise SystemExit("En Linux el motor lo arranca systemd: systemctl --user start tickfence")
    # pythonservice.exe llama con -u -m focuslock.service --start-service.
    # HandleCommandLine ve "--start-service" y arranca la clase del servicio,
    # que es lo que busca en la funcion ServiceMain.
    win32serviceutil.HandleCommandLine(TickFenceService)
