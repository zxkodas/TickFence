"""Canal de control entre la GUI y el motor con enforcement.

Windows: named pipe `\\\\.\\pipe\\TickFence` (el motor corre como LocalSystem).
Linux: socket Unix en `paths.socket_path()` (el motor corre como servicio
systemd de usuario). El protocolo JSON es el mismo en ambos.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from typing import Any, Callable

import psutil

from . import paths

ENCODING = "utf-8"

try:
    import pywintypes  # type: ignore
except ImportError:
    pywintypes = None  # type: ignore


def _log(message: str) -> None:
    """Intenta el log de eventos de Windows; si no, al menos no revienta."""
    try:
        import win32logging  # type: ignore

        win32logging.LogWarning(0xF001, "TickFence: %s", message)
    except Exception:
        try:
            sys.stderr.write(f"[tickfence] {message}\n")
            sys.stderr.flush()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cliente (lo usa la GUI)
# ---------------------------------------------------------------------------


class IpcError(RuntimeError):
    pass


# Codigos de Win32 que vale la pena reintentar: el pipe existe pero en este
# instante no se puede abrir (.instancia ocupada, servicio reiniciandose).
_RETRYABLE = {
    2,    # ERROR_FILE_NOT_FOUND
    231,  # ERROR_PIPE_BUSY  "todas las instancias estan en uso"
    233,  # ERROR_PIPE_NOT_CONNECTED
}


class IpcClient:
    def __init__(self, pipe: str | None = None, timeout: float = 20.0) -> None:
        self._pipe = pipe or paths.PIPE_NAME
        self._timeout = timeout
        # Cuantas veces reintentar si el pipe esta ocupado o el servicio reinicia.
        self._retries = 2

    def call(self, command: str, retries: int | None = None, **payload: Any) -> dict[str, Any]:
        if not paths.is_windows():
            return self._call_unix(command, retries, **payload)
        import win32file  # type: ignore
        import win32pipe  # type: ignore

        retries = self._retries if retries is None else retries

        request = json.dumps({"cmd": command, "pid": os.getpid(), **payload}) + "\n"
        data = request.encode(ENCODING)

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            handle = None
            try:
                # El servidor expone una sola instancia a la vez. Si esta ocupada,
                # esperamos a que la libere en vez de fallar con error 231.
                try:
                    win32pipe.WaitNamedPipe(self._pipe, 5000)
                except pywintypes.error:
                    pass
                handle = win32file.CreateFile(
                    self._pipe,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
                win32file.WriteFile(handle, data)
                win32file.FlushFileBuffers(handle)
                # El pipe es de tipo mensaje: una lectura trae la respuesta entera.
                _, raw = win32file.ReadFile(handle, 65536)
                text = raw.decode(ENCODING, errors="replace").strip()
                if not text:
                    raise IpcError("El servicio no respondio.")
                result = json.loads(text.splitlines()[-1])
                if not result.get("ok"):
                    raise IpcError(result.get("error") or "Error desconocido del servicio.")
                return result.get("data", {})
            except IpcError:
                raise
            except (pywintypes.error, OSError) as exc:
                # pywintypes.error NO hereda de OSError, hay que capturarlo aparte.
                code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
                if code not in _RETRYABLE:
                    raise IpcError(f"Error del servicio (código {code}): {exc}") from exc
                last_error = exc
                if attempt < retries:
                    time.sleep(0.4 * (attempt + 1))  # el servicio puede reiniciarse
                    continue
                raise IpcError(
                    f"No se pudo contactar al servicio de TickFence ({self._pipe}). "
                    "Esta corriendo el servicio de Windows?"
                ) from exc
            finally:
                if handle is not None:
                    try:
                        handle.Close()
                    except Exception:
                        pass
        raise IpcError(str(last_error))

    def _call_unix(self, command: str, retries: int | None = None, **payload: Any) -> dict[str, Any]:
        """Mismo protocolo por socket Unix. Sin dependencias nuevas: stdlib."""
        # ponytail: socket Unix + JSON-línea, permisos del fs como seguridad.
        retries = self._retries if retries is None else retries
        request = json.dumps({"cmd": command, "pid": os.getpid(), **payload}) + "\n"
        data = request.encode(ENCODING)
        sock_path = str(paths.socket_path())
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(self._timeout)
                    sock.connect(sock_path)
                    sock.sendall(data)
                    chunks: list[bytes] = []
                    while True:
                        part = sock.recv(65536)
                        if not part:
                            break
                        chunks.append(part)
                        if b"\n" in part:
                            break
                text = b"".join(chunks).decode(ENCODING, errors="replace").strip()
                if not text:
                    raise IpcError("El servicio no respondio.")
                result = json.loads(text.splitlines()[-1])
                if not result.get("ok"):
                    raise IpcError(result.get("error") or "Error desconocido del servicio.")
                return result.get("data", {})
            except IpcError:
                raise
            except (OSError, ConnectionError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                raise IpcError(
                    f"No se pudo contactar al servicio de TickFence ({sock_path}). "
                    "Esta corriendo? (systemctl --user status tickfence)"
                ) from exc
        raise IpcError(str(last_error))


# ---------------------------------------------------------------------------
# Servidor (corre dentro del servicio)
# ---------------------------------------------------------------------------


# SYSTEM y administradores control total; usuarios interactivos lectura/escritura.
# Sin prefijo de propietario (O:): un usuario normal no puede asignarse
# BUILTIN\Administrators como dueño y CreateNamedPipe falla con error 1307.
_PIPE_SDDL = "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;BU)(A;;GRGW;;;IU)"


class IpcServer:
    def __init__(self, handler: Callable[[str, dict], dict]) -> None:
        self._handler = handler
        self._pipe = paths.PIPE_NAME
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if not paths.is_windows():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run_unix, name="ipc-server", daemon=True)
            self._thread.start()
            return
        import win32pipe  # type: ignore

        self._win32pipe = win32pipe
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ipc-server", daemon=True)
        self._thread.start()

    def _sddl(self):
        """SECURITY_ATTRIBUTES con el DACL del pipe, o None si no se pudo.

        pywin32 expone `SECURITY_DESCRIPTOR` (no `lpSecurityDescriptor`) en el
        objeto PySECURITY_ATTRIBUTES.
        """
        try:
            import win32security  # type: ignore

            attributes = win32security.SECURITY_ATTRIBUTES()
            attributes.bInheritHandle = 0
            attributes.SECURITY_DESCRIPTOR = (
                win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
                    _PIPE_SDDL, win32security.SDDL_REVISION_1
                )
            )
            return attributes
        except Exception as exc:
            _log(f"no se pudo aplicar el DACL del pipe: {exc!r}")
            return None

    def stop(self) -> None:
        self._stop.set()
        if not paths.is_windows():
            # Despierta al accept() conectándose al propio socket.
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1.0)
                    sock.connect(str(paths.socket_path()))
                    sock.sendall(b'{"cmd": "__stop__", "pid": 0}\n')
            except Exception:
                pass
            return
        try:
            import win32file  # noqa: F401

            handle = win32file.CreateFile(
                self._pipe,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
            win32file.CloseHandle(handle)
        except Exception:
            pass

    def _authorized_caller(self, client_pid: int) -> bool:
        """Comprobacion minima: el PID declarado debe seguir vivo.

        La frontera de seguridad real es el DACL del pipe
        (SYSTEM + administradores + usuarios interactivos). Este chequeo solo
        evita que un PID inventado o ya muerto se haga pasar por alguien.
        """
        if not client_pid or client_pid == os.getpid():
            return bool(client_pid)
        try:
            return psutil.Process(client_pid).is_running()
        except psutil.Error:
            return False

    def _run(self) -> None:
        win32pipe = self._win32pipe
        import win32file  # type: ignore

        sa = self._sddl()
        flags = (
            win32pipe.PIPE_ACCESS_DUPLEX
            | win32file.FILE_FLAG_OVERLAPPED
            | win32pipe.FILE_FLAG_FIRST_PIPE_INSTANCE
        )
        mode = win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE
        # nMaxInstances=1 evita el error 231 ("todas las instancias en uso") y
        # serializa las peticiones, que es justo lo que queremos aqui.
        max_instances = 1
        reported = False

        while not self._stop.is_set():
            try:
                pipe = win32pipe.CreateNamedPipe(
                    self._pipe, flags, mode, max_instances, 65536, 65536, 0, sa
                )
                reported = False
            except Exception as exc:  # noqa: BLE001
                if not reported:
                    _log(f"no se pudo crear el pipe {self._pipe}: {exc!r}")
                    reported = True
                self._stop.wait(1.0)
                continue

            connected = False
            try:
                # ERROR_PIPE_CONNECTED: el cliente ya se habia conectado entre
                # CreateNamedPipe y esta llamada. Es normal, no es un error.
                win32pipe.ConnectNamedPipe(pipe, None)
                connected = True
            except pywintypes.error as exc:
                if exc.winerror == 535:  # ERROR_PIPE_CONNECTED
                    connected = True
                else:
                    _log(f"ConnectNamedPipe fallo: {exc!r}")

            if not connected:
                try:
                    win32file.CloseHandle(pipe)
                except Exception:
                    pass
                if self._stop.is_set():
                    break
                continue

            try:
                _, raw = win32file.ReadFile(pipe, 65536)
                text = raw.decode(ENCODING, errors="replace").strip()
                response = self._dispatch(text)
                win32file.WriteFile(pipe, (json.dumps(response) + "\n").encode(ENCODING))
                win32file.FlushFileBuffers(pipe)
            except Exception as exc:  # noqa: BLE001
                try:
                    err = {"ok": False, "error": f"Error interno: {exc}"}
                    win32file.WriteFile(pipe, (json.dumps(err) + "\n").encode(ENCODING))
                except Exception:
                    pass
            finally:
                try:
                    win32pipe.DisconnectNamedPipe(pipe)
                    win32file.CloseHandle(pipe)
                except Exception:
                    pass

    def _run_unix(self) -> None:
        """Servidor en socket Unix. Misma serialización que el pipe."""
        sock_path = paths.socket_path()
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if sock_path.exists():
                sock_path.unlink()
        except OSError:
            pass
        reported = False
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(sock_path))
            try:
                os.chmod(sock_path, 0o600)
            except OSError:
                pass
            server.listen(5)
            server.settimeout(0.5)
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError as exc:
                    if not reported:
                        _log(f"no se pudo aceptar en {sock_path}: {exc!r}")
                        reported = True
                    self._stop.wait(1.0)
                    continue
                with conn:
                    try:
                        chunks: list[bytes] = []
                        conn.settimeout(10.0)
                        while True:
                            part = conn.recv(65536)
                            if not part:
                                break
                            chunks.append(part)
                            if b"\n" in part:
                                break
                        text = b"".join(chunks).decode(ENCODING, errors="replace").strip()
                        if text == '{"cmd": "__stop__", "pid": 0}':
                            continue
                        response = self._dispatch(text)
                        conn.sendall((json.dumps(response) + "\n").encode(ENCODING))
                    except Exception as exc:  # noqa: BLE001
                        try:
                            err = {"ok": False, "error": f"Error interno: {exc}"}
                            conn.sendall((json.dumps(err) + "\n").encode(ENCODING))
                        except Exception:
                            pass
        try:
            if sock_path.exists():
                sock_path.unlink()
        except OSError:
            pass

    def _dispatch(self, text: str) -> dict[str, Any]:
        if not text:
            return {"ok": False, "error": "Petición vacía"}
        try:
            request = json.loads(text.splitlines()[0])
        except json.JSONDecodeError:
            return {"ok": False, "error": "JSON inválido"}
        command = str(request.pop("cmd", ""))
        if not command:
            return {"ok": False, "error": "Falta el comando"}
        if not self._authorized_caller(request.get("pid", 0)):
            return {"ok": False, "error": "Origen no autorizado para este servicio."}
        try:
            data = self._handler(command, request)
            return {"ok": True, "data": data}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
