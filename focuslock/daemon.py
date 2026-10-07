"""Motor de aplicación. Corre dentro del servicio (LocalSystem).

Responsabilidades:
  - mantener el estado bloqueado/desbloqueado
  - vigilar procesos y aplicar/quitar IFEO
  - consultar TickTick y acreditar Lecturas
  - servir el estado a las extensiones del navegador
  - atender los comandos de la GUI por named pipe
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import config as config_mod
from . import emergency as emergency_mod
from . import i18n
from . import ifeo, secrets
from .config import Config
from .gate import Gate
from .guard import ProcessGuard, is_dangerous
from .i18n import tr
from .ipc import IpcServer
from .rules import in_never_block, match_program, norm_program, norm_site
from .server import StateServer
from .store import Store
from .ticktick import TickTickClient, TickTickError


def stub_command() -> str:
    """Comando que Windows ejecutará en lugar del programa bloqueado."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --ifeo-stub'
    if sys.platform.startswith("win"):
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        if not pyw.exists():
            pyw = exe
        return f'"{pyw}" "{Path(__file__).with_name("stub.py")}"'
    return f'"{sys.executable}" "{Path(__file__).with_name("stub.py")}"'


def _host_only(rule: str) -> str:
    return norm_site(rule).partition("/")[0]


class Engine:
    """Comandos expuestos a la GUI.

    Se delegan en metodos _cmd_<nombre>; el prefijo es lo que permite despachar
    por reflection desde el pipe. La lista de abajo es la superficie real y la
    que validan los tests.
    """

    def __init__(self, arm_guard: bool = True) -> None:
        """arm_guard=False deja el vigilante de procesos apagado.

        Por defecto True porque el uso normal es como servicio, donde el
        vigilante es justo lo que tiene que hacer. En modo consola hay que
        pedirlo a proposito: ahi el motor corre en la sesion del usuario y un
        killer de procesos se lleva por delante el escritorio entero.
        """
        self.config: Config = config_mod.instance()
        # El servicio arma sus propios mensajes (los errores de la emergencia,
        # el motivo del desbloqueo), asi que tiene que saber el idioma ANTES
        # de que se le pida nada. La UI hace lo mismo al arrancar.
        i18n.set_lang(self.config.get("general").get("language", "en"))
        self.store: Store = Store()
        self._publish_language()
        self.store.read()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self.arm_guard = arm_guard

        self.client = TickTickClient(secrets.wipe(self.store.get("ticktick_token", "")))
        self.gate = Gate(self.client, self.config, self.store)
        self.guard = ProcessGuard(self._should_block, self._on_block)
        # El proceso de TickFence y OpenCode quedan intocables siempre.
        self.guard.protect_name("explorer.exe")
        self.guard.protect_name("opencode.exe")
        if not sys.platform.startswith("win"):
            self.guard.protect_name("gnome-shell")
            self.guard.protect_name("systemd")
        self.server = StateServer(self.state_payload, self._server_token())
        self.ipc = IpcServer(self.handle)
        self._poller: threading.Thread | None = None
        self._last_sync: float = 0.0

    # ------------------------------------------------------------------
    # Arranque / parada
    # ------------------------------------------------------------------
    def start(self) -> None:
        port = self.server.start()
        self.store.update(server_port=port)
        self._stop.clear()
        self._poller = threading.Thread(target=self._poll_loop, name="poller", daemon=True)
        self._poller.start()
        # El pipe va antes del guard: si el motor no puede recibir ordenes,
        # no tiene sentido vigilar procesos.
        self.ipc.start()
        if self.arm_guard:
            self.guard.start()

        # Si el bloqueo quedó activo de un reinicio anterior (una reinstalación,
        # un crash, un reinicio de PC), el ciclo arranca con horas de antigüedad
        # y cualquier Lectura tachada "durante" ese ciclo viejo cuenta como
        # anterior. Se reinicia para que el reloj del ciclo sea honesto.
        self._reset_stale_lock_cycle()
        try:
            self.gate.poll()
        except Exception as exc:  # noqa: BLE001
            self.store.set("last_error", str(exc))
        self._sync_ifeo(force=True)

    # Un ciclo de bloqueo más viejo que esto se considera de una sesión previa:
    # reiniciar el PC o reinstalar no debería dejarte encerrado en un ciclo
    # que empezó hace horas.
    _MAX_CYCLE_SECONDS = 6 * 3600

    def _reset_stale_lock_cycle(self) -> None:
        data = self.store.read()
        if not data.get("locked", False):
            return
        started = float(data.get("lock_started", 0) or 0)
        if not started or (time.time() - started) < self._MAX_CYCLE_SECONDS:
            return
        # No reiniciar si ya hay créditos: el usuario está trabajando.
        if int(data.get("credits", 0) or 0) > 0:
            return
        self.gate.relock()

    def stop(self) -> None:
        self._stop.set()
        self.guard.stop()
        self.server.stop()
        # Nunca dejar IFEO puesto al apagar el servicio.
        try:
            for exe in ifeo.list_blocked():
                ifeo.clear(exe)
        except Exception:
            pass

    def _server_token(self) -> str:
        from .server import new_token

        token = secrets.wipe(self.store.get("server_token", ""))
        if not token:
            token = new_token()
            self.store.set("server_token", secrets.protect(token))
        return token

    # ------------------------------------------------------------------
    # Decisiones de bloqueo
    # ------------------------------------------------------------------
    def _should_block(self, name: str) -> bool:
        if not name:
            return False
        if self.gate.is_unlocked():
            return False
        cfg = self.config.get("programs")
        return match_program(name, cfg.get("blocked", []), cfg.get("allowed", []))

    def _on_block(self, name: str, pid: int) -> None:
        self.gate.log_block(
            {"at": time.time(), "process": name, "pid": pid, "method": "watchdog"}
        )

    def _site_cfg(self) -> dict[str, list[str]]:
        cfg = self.config.get("sites")
        return {
            "blocked": [_host_only(r) for r in cfg.get("blocked", []) if _host_only(r)],
            "allowed": [_host_only(r) for r in cfg.get("allowed", []) if _host_only(r)],
        }

    def state_payload(self) -> dict[str, Any]:
        """Lo que consume la extensión del navegador."""
        status = self.gate.status()
        sites = self._site_cfg()
        return {
            "locked": not status.unlocked,
            "blockedHosts": sites["blocked"],
            "allowedHosts": sites["allowed"],
            "credits": status.credits,
            "required": status.required,
            "reason": status.unlock_reason,
            "expires": self.store.get("unlock_until", 0) or 0,
            "serverTime": time.time(),
        }

    # ------------------------------------------------------------------
    # IFEO
    # ------------------------------------------------------------------
    def _sync_ifeo(self, force: bool = False) -> dict:
        """Reconcilia las claves IFEO con la configuracion vigente.

        Recarga la config desde el archivo antes de decidir: si alguien edito
        config.json a mano, el bloqueo tiene que seguirlo. Sin esto el servicio
        se queda con lo que leyo al arrancar y deja claves de programas que ya
        no estan bloqueados, sin salida desde la interfaz.
        """
        if not force and time.time() - self._last_sync < 20:
            return {}
        self._last_sync = time.time()
        self.config.reload_if_changed()
        cfg = self.config.get("programs")
        if not cfg.get("use_ifeo", True) or self.gate.is_unlocked():
            removed = ifeo.list_blocked()
            for exe in removed:
                ifeo.clear(exe)
            return {"removed": removed, "applied": []}
        return ifeo.sync(cfg.get("blocked", []), cfg.get("allowed", []), stub_command())

    # ------------------------------------------------------------------
    # Bucle periódico
    # ------------------------------------------------------------------
    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._sync_ifeo()
                every = max(15, int(self.config.get("ticktick").get("poll_seconds", 45)))
                if time.time() - float(self.store.get("last_poll", 0) or 0) >= every:
                    self.gate.poll()
                    self._sync_ifeo()
            except Exception:
                pass
            self._stop.wait(2.0)

    # ------------------------------------------------------------------
    # Comandos de la GUI
    # ------------------------------------------------------------------
    def handle(self, command: str, req: dict) -> Any:
        with self._lock:
            handler = getattr(self, f"_cmd_{command}", None)
            if handler is None:
                raise KeyError(f"Comando desconocido: {command}")
            result = handler(req)
            if isinstance(result, dict):
                result.setdefault("state", self.state_payload())
            return result

    def _cmd_status(self, req: dict) -> dict:
        status = self.gate.status()
        return {
            "locked": not status.unlocked,
            "enforcement": True,
            "checked_at": status.checked_at,
            "credits": status.credits,
            "required": status.required,
            "remaining": status.remaining(),
            "reason": status.unlock_reason,
            "modules": status.modules,
            "pending": [
                {"id": t.id, "title": t.title, "module": t.module()}
                for t in status.pending[:200]
            ],
            "done": [
                {"id": t.id, "title": t.title, "module": t.module()}
                for t in status.done[:200]
            ],
            "error": status.error,
            "ticktick_ok": self.client.configured,
            "port": self.store.get("server_port", 0),
            "token": secrets.wipe(self.store.get("server_token", "")),
            "ifeo": ifeo.list_blocked(),
            "guard": self.guard.stats(),
            "guard_armed": self.arm_guard,
        }

    def _cmd_poll(self, req: dict) -> dict:
        status = self.gate.poll()
        self._sync_ifeo()
        return {
            "locked": not status.unlocked,
            "enforcement": True,
            "checked_at": status.checked_at,
            "credits": status.credits,
            "required": status.required,
            "remaining": status.remaining(),
            "reason": status.unlock_reason,
            "modules": status.modules,
            "pending": [
                {"id": t.id, "title": t.title, "module": t.module()}
                for t in status.pending[:200]
            ],
            "done": [
                {"id": t.id, "title": t.title, "module": t.module()}
                for t in status.done[:200]
            ],
            "error": status.error,
        }

    def _cmd_lock(self, req: dict) -> dict:
        """Activa el bloqueo. Es la unica via para encerrar al usuario."""
        self.gate.relock()
        # Consulta inmediata: fija la linea base ahora y no en el proximo
        # ciclo de poll. Si no, una Lectura que el usuario tacha durante la
        # ventana de 45s queda como "ya completada" en la siembra y no cuenta.
        self.gate.poll()
        self._sync_ifeo(force=True)
        applied = ifeo.list_blocked()
        if sys.platform.startswith("win"):
            message = tr(
                "Lock on. {n} program(s) blocked at the Windows level. Finish "
                "the Readings to release them."
            ).format(n=len(applied))
        else:
            # Sin IFEO en Linux: el guard mata el proceso si arranca.
            message = tr(
                "Lock on. {n} program(s) watched by the process guard. Finish "
                "the Readings to release them."
            ).format(n=len(self.config.get("programs").get("blocked", [])))
        return {
            "locked": True,
            "ifeo": applied,
            "message": message,
        }

    def _cmd_unlock(self, req: dict) -> dict:
        """Apaga el bloqueo. Siempre permitido, sin preguntas ni registro."""
        self.gate.unlock_now("desactivado a mano desde la app", minutes=0)
        self._sync_ifeo(force=True)
        cleared = [exe for exe in ifeo.list_blocked() if not ifeo.is_blocked(exe)]
        # unlock_now con unlock_until=0 deja locked=False; el IFEO se limpia
        # porque is_unlocked() ahora da True.
        return {
            "locked": False,
            "message": (
                "Bloqueo desactivado. Los programas bloqueados vuelven a "
                "abrirse con normalidad."
            ),
        }

    def _cmd_relock(self, req: dict) -> dict:
        return self._cmd_lock(req)

    def _cmd_emergency(self, req: dict) -> dict:
        """Valida el compromiso y, si cumple, desbloquea de verdad.

        A diferencia de LocalBackend, acá si hay enforcement: las claves IFEO
        se levantan y el desbloqueo tiene efecto.
        """
        submission = emergency_mod.EmergencySubmission(
            text=req.get("text", "") or "",
            prompts=req.get("prompts", {}) or {},
            keystrokes=int(req.get("keystrokes", 0) or 0),
            elapsed=float(req.get("elapsed", 0) or 0),
            longest_idle=float(req.get("longest_idle", 0) or 0),
            started_at=float(req.get("started_at", 0) or time.time()),
        )
        verdict = emergency_mod.validate(submission, self.config.all())
        if not verdict.ok:
            return {"granted": False, "errors": verdict.errors, "words": verdict.words,
                    "seconds": verdict.seconds, "ratio": round(verdict.ratio, 2)}

        minutes = int(self.config.get("emergency").get("unlock_minutes", 20))
        self.gate.log_emergency(emergency_mod.summarize(submission, verdict))
        self.gate.unlock_now(
            reason=i18n.tr("Emergency: written commitment ({w} words, {m} min)").format(
                w=verdict.words, m=int(verdict.seconds // 60)),
            minutes=minutes,
        )
        self._sync_ifeo(force=True)
        return {
            "granted": True,
            "words": verdict.words,
            "seconds": verdict.seconds,
            "minutes": minutes,
            "message": tr(
                "Unlocked for {n} min. Your commitment was recorded."
            ).format(n=minutes),
        }

    def _cmd_history(self, req: dict) -> dict:
        return {
            "emergencies": self.gate.emergencies(),
            "blocks": self.gate.blocks()[-40:],
        }

    def _cmd_ticktick_test(self, req: dict) -> dict:
        try:
            return self.client.test_connection()
        except TickTickError as exc:
            return {"ok": False, "error": str(exc)}

    def _cmd_install_ready(self, req: dict) -> dict:
        """Lo usa install.ps1 para confirmar que el servicio quedo operativo.

        Devuelve info de diagnostico sin secretos.
        """
        return {
            "service_pid": os.getpid(),
            "python": sys.executable,
            "stub": stub_command(),
            "config_path": str(self.config.path),
            "state_path": str(self.store.path),
            "port": self.store.get("server_port", 0),
            "ticktick_ok": self.client.configured,
            "poll_seconds": int(self.store.get("last_poll", 0) or 0) > 0,
            "ifeo_applied": ifeo.list_blocked(),
            "guard": self.guard.stats(),
            "guard_armed": self.arm_guard,
        }

    def _cmd_ticktick_set_token(self, req: dict) -> dict:
        token = (req.get("token", "") or "").strip()
        if not token:
            self.store.set("ticktick_token", "")
            self.client = TickTickClient("")
            self.gate = Gate(self.client, self.config, self.store)
            return {"ok": True, "message": "Token eliminado."}

        # Probamos ANTES de guardar: un token invalido no debe pisar el bueno.
        try:
            probe = TickTickClient(token).test_connection()
        except TickTickError as exc:
            return {"ok": False, "error": str(exc)}

        self.store.set("ticktick_token", secrets.protect(token))
        self.client = TickTickClient(token)
        self.gate = Gate(self.client, self.config, self.store)
        # La UI lo usa para decir "quedó guardado pero no bloquea".
        probe["enforcement"] = True
        return probe

    def _cmd_config_get(self, req: dict) -> dict:
        return {"config": self.config.all()}

    def _publish_language(self) -> None:
        """Copia el idioma al estado.

        El stub de IFEO no puede leer la config (para no tocar el token) y
        tiene que poder escribir el aviso en el idioma del usuario. El estado
        es lo unico que puede leer, asi que el idioma se duplica ahi.
        """
        self.store.set("language", i18n.lang())
        self.store.write()

    def _cmd_config_set(self, req: dict) -> dict:
        section = str(req.get("section", ""))
        values = req.get("values", {}) or {}
        if not section or not isinstance(values, dict):
            raise ValueError("Falta 'section' o 'values'")
        self.config.set(section, values)
        # SIN ESTA LINEA el cambio vivia solo en memoria. Config.set() hace
        # merge pero no escribe, y el servicio se reinicia (o se apaga la
        # maquina), asi que todo lo que guardaras en la ventana se perdia.
        # Se comprobo: config_set con poll_seconds=77 dejaba al servicio
        # diciendo 77 y el archivo con 45, sin tocarse.
        #
        # Se guarda aca y no en cada handler de seccion porque TODO
        # config_set tiene que persistir, no solo los que alguien se acordaba.
        self.config.save()
        if section == "programs":
            self._sync_ifeo(force=True)
        if section == "general":
            # El idioma cambia dos cosas mas alla de la ventana: los mensajes
            # que arma el servicio, y el aviso que ve el usuario cuando un
            # programa esta bloqueado. El stub lee el idioma del estado, asi
            # que hay que reflejarlo ahi.
            i18n.set_lang(values.get("language", i18n.lang()))
            self._publish_language()
        if section == "ticktick":
            status = self.gate.poll()
            return {"ok": True, "credits": status.credits, "required": status.required}
        return {"ok": True}

    # -- listas de programas / sitios -------------------------------------
    def _list_op(self, req: dict, section: str, field: str, add: bool) -> dict:
        """Agrega o quita una regla, normalizandola y sin duplicados.

        Nota: la lista se guarda con el formato ya normalizado, pero los sitios
        conservan su ruta si el usuario la escribio. `_host_only` se aplica
        recien al enviar el estado a la extension.
        """
        cfg = self.config.get(section)
        raw = cfg.get(field, []) or []
        value = req.get("value", "") or ""
        if section == "programs":
            value = norm_program(value)
        else:
            value = norm_site(value)
        if not value:
            raise ValueError(i18n.tr("Invalid or empty value."))

        def _norm(v: str) -> str:
            return norm_program(v) if section == "programs" else norm_site(v)

        # Re-normalizar toda la lista evita que queden restos de otra version.
        items: list[str] = []
        for entry in raw:
            normalized = _norm(entry)
            if normalized and normalized not in items:
                items.append(normalized)

        danger = is_dangerous(value) if section == "programs" else False

        if add and section == "programs" and in_never_block(value):
            # El guard nunca los mata, pero no vale la pena guardarlos en la
            # lista: daria la impresion de que se pueden bloquear.
            return {
                "ok": False,
                "immutable": True,
                "dangerous": True,
                "value": value,
                "list": items,
                "message": (
                    f"{value} es un proceso protegido de Windows: TickFence nunca "
                    "lo bloquea, y agregarlo a la lista no tendria ningun efecto."
                ),
            }

        if add:
            # El item no puede estar en las dos listas a la vez. Si ya esta en la
            # opuesta, lo movemos en vez de error: es lo que el usuario quiere.
            opposite = "allowed" if field == "blocked" else "blocked"
            other = [_norm(v) for v in (cfg.get(opposite, []) or [])]
            if value in other:
                self.config.set(section, {opposite: [v for v in other if v != value]})
            if value not in items:
                items.append(value)
            if danger and not req.get("force"):
                # El GUI pide confirmacion y reintenta con force=True.
                return {
                    "ok": False,
                    "needs_confirm": True,
                    "dangerous": True,
                    "value": value,
                    "list": items,
                    "message": i18n.tr(
                        "{v} is a critical system or Windows process. Blocking "
                        "it can leave the machine unusable, or stop the app "
                        "itself from opening again."
                    ).format(v=value),
                }
        else:
            items = [i for i in items if i != value]

        self.config.set(section, {field: items})
        # Sin save() la lista vive solo en memoria y se pierde al reiniciar.
        self.config.save()
        if section == "programs":
            self._sync_ifeo(force=True)
        return {"ok": True, "list": items, "dangerous": danger}

    def _cmd_programs_blocked_add(self, req): return self._list_op(req, "programs", "blocked", True)
    def _cmd_programs_blocked_del(self, req): return self._list_op(req, "programs", "blocked", False)
    def _cmd_programs_allowed_add(self, req): return self._list_op(req, "programs", "allowed", True)
    def _cmd_programs_allowed_del(self, req): return self._list_op(req, "programs", "allowed", False)
    def _cmd_sites_blocked_add(self, req): return self._list_op(req, "sites", "blocked", True)
    def _cmd_sites_blocked_del(self, req): return self._list_op(req, "sites", "blocked", False)
    def _cmd_sites_allowed_add(self, req): return self._list_op(req, "sites", "allowed", True)
    def _cmd_sites_allowed_del(self, req): return self._list_op(req, "sites", "allowed", False)

    def _cmd_ifeo_sync(self, req: dict) -> dict:
        return self._sync_ifeo(force=True)

    def _cmd_diag(self, req: dict) -> dict:
        return {
            "service_pid": os.getpid(),
            "python": sys.executable,
            "stub": stub_command(),
            "config_path": str(self.config.path),
            "state_path": str(self.store.path),
            "server_url": f"http://127.0.0.1:{self.store.get('server_port', 0)}/state",
            "installed": True,
        }
