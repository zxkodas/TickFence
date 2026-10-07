"""Backend alternativo para cuando el servicio no esta instalado.

El servicio es el dueño del *bloqueo*, pero no tiene por que ser el dueño de
la *interfaz*. Si el servicio no responde, la GUI puede seguir siendo util:
hablar con TickTick, mostrar el progreso, guardar el token y la config.

Misma interfaz que IpcClient (`call(comando, **payload)`), asi que la UI no
sabe cual de los dos tiene delante.

Lo que NO hace en modo standalone, y hay que decirlo claro:
  - no aplica IFEO (requiere admin)
  - no corre el vigilante de procesos
  - no sirve el endpoint HTTP para las extensiones
Es decir: se ve el estado, pero no bloquea nada. La app lo dice en pantalla.
"""
from __future__ import annotations

import time
from typing import Any

from . import emergency as emergency_mod
from . import ifeo, secrets
from .config import Config
from .gate import Gate
from .guard import is_dangerous
from .rules import in_never_block, match_program, norm_program, norm_site
from .server import StateServer
from .store import Store
from .ticktick import TickTickClient, TickTickError

# Comandos que solo tienen sentido con el servicio corriendo.
SERVICE_ONLY = {"install_ready", "ifeo_sync", "diag"}


class LocalBackend:
    """Implementa la superficie de comandos del Engine, en el proceso de la GUI."""

    def __init__(self) -> None:
        self.config = Config()
        self.config.load()
        self.store = Store()
        self.store.read()
        self.client = TickTickClient(secrets.wipe(self.store.get("ticktick_token", "")))
        self.gate = Gate(self.client, self.config, self.store)
        # El servidor HTTP se puede levantar igual: las extensiones funcionan
        # siempre que la GUI este abierta. Sin servicio no hay bloqueo, asi que
        # su payload dira locked=false.
        self.server = StateServer(self.state_payload, self._server_token())
        try:
            self.port = self.server.start()
            self.store.update(server_port=self.port)
        except OSError:
            self.port = 0

    def close(self) -> None:
        self.server.stop()

    def _server_token(self) -> str:
        from .server import new_token

        token = secrets.wipe(self.store.get("server_token", ""))
        if not token:
            token = new_token()
            self.store.set("server_token", secrets.protect(token))
        return token

    # -- estado que consumen las extensiones -------------------------------
    def state_payload(self) -> dict[str, Any]:
        status = self.gate.status()
        cfg = self.config.get("sites")

        def host(rule: str) -> str:
            return norm_site(rule).partition("/")[0]

        return {
            # Sin servicio no hay nada que upholda el bloqueo, asi que no se
            # promete. La extension no bloquea.
            "locked": False,
            "blockedHosts": [host(r) for r in cfg.get("blocked", []) if host(r)],
            "allowedHosts": [host(r) for r in cfg.get("allowed", []) if host(r)],
            "credits": status.credits,
            "required": status.required,
            "reason": "sin servicio: no se esta bloqueando nada",
            "expires": 0,
            "serverTime": time.time(),
        }

    # -- dispatch -----------------------------------------------------------
    def call(self, command: str, **payload: Any) -> dict[str, Any]:
        handler = getattr(self, f"_cmd_{command}", None)
        if handler is None:
            if command in SERVICE_ONLY:
                raise RuntimeError(
                    "Este comando necesita el servicio instalado."
                )
            raise KeyError(f"Comando desconocido: {command}")
        result = handler(payload)
        if isinstance(result, dict):
            result.setdefault("state", self.state_payload())
        return result

    # -- comandos -----------------------------------------------------------
    def _cmd_status(self, req: dict) -> dict:
        status = self.gate.status()
        return {
            "locked": not status.unlocked,
            "enforcement": False,
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
            "done": [{"id": t.id, "title": t.title, "module": t.module()} for t in status.done[:200]],
            "error": status.error,
            "ticktick_ok": self.client.configured,
            "port": self.port,
            "token": secrets.wipe(self.store.get("server_token", "")),
            "ifeo": [],
            "guard": {"scans": 0, "kills": 0, "running": False},
            "guard_armed": False,
        }

    def _cmd_poll(self, req: dict) -> dict:
        status = self.gate.poll()
        return {
            "locked": not status.unlocked,
            "enforcement": False,
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
            "done": [{"id": t.id, "title": t.title, "module": t.module()} for t in status.done[:200]],
            "error": status.error,
        }

    def _cmd_lock(self, req: dict) -> dict:
        """Activa el conteo de Lecturas.

        En modo local no hay enforcement: no se puede bloquear nada. Igual
        reinicia el contador para que "Activar bloqueo" tenga el efecto que
        corresponde cuando despues se instale el servicio.
        """
        self.gate.relock()
        return {
            "locked": True,
            "enforcement": False,
            "message": (
                "Contador de Lecturas reiniciado. Ojo: sin el servicio "
                "corriendo esto no bloquea nada, solo lleva la cuenta."
            ),
        }

    def _cmd_unlock(self, req: dict) -> dict:
        """Apaga el conteo. En modo local nunca hubo bloqueo, asi que es no-op."""
        self.gate.unlock_now("desactivado a mano desde la app", minutes=0)
        return {"locked": False, "enforcement": False, "message": "Contador reiniciado."}

    def _cmd_relock(self, req: dict) -> dict:
        return self._cmd_lock(req)

    def _cmd_emergency(self, req: dict) -> dict:
        """Se valida igual, pero SIN efecto: no hay nada que desbloquear.

        Aceptarlo y no hacer nada seria una mentira, y anotarlo como unlocked
        sin Enforcement seria peor. Se valida, se registra y se explica.
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
            return {
                "granted": False,
                "errors": verdict.errors,
                "words": verdict.words,
                "seconds": verdict.seconds,
                "ratio": round(verdict.ratio, 2),
            }
        # Cumple los requisitos: se registra igual, como evidencia de que
        # escribio, pero no se "desbloquea" nada porque no hay bloqueo activo.
        self.gate.log_emergency(emergency_mod.summarize(submission, verdict))
        return {
            "granted": False,
            "no_service": True,
            "words": verdict.words,
            "seconds": verdict.seconds,
            "errors": [
                "Cumpliste los requisitos y tu compromiso quedó registrado.",
                "Pero el servicio no está corriendo, así que ahora "
                "mismo no hay nada bloqueado que desbloquear.",
                "Instalalo con: python -m focuslock install (Linux) o install.ps1 (Windows como administrador)",
            ],
        }

    def _cmd_history(self, req: dict) -> dict:
        return {"emergencies": self.gate.emergencies(), "blocks": []}

    def _cmd_ticktick_test(self, req: dict) -> dict:
        try:
            return self.client.test_connection()
        except TickTickError as exc:
            return {"ok": False, "error": str(exc)}

    def _cmd_ticktick_set_token(self, req: dict) -> dict:
        token = (req.get("token", "") or "").strip()
        if not token:
            self.store.set("ticktick_token", "")
            self.client = TickTickClient("")
            self.gate = Gate(self.client, self.config, self.store)
            return {"ok": True, "message": "Token eliminado."}
        try:
            probe = TickTickClient(token).test_connection()
        except TickTickError as exc:
            return {"ok": False, "error": str(exc)}
        self.store.set("ticktick_token", secrets.protect(token))
        self.client = TickTickClient(token)
        self.gate = Gate(self.client, self.config, self.store)
        probe["enforcement"] = False
        return probe

    def _cmd_config_get(self, req: dict) -> dict:
        return {"config": self.config.all()}

    def _cmd_config_set(self, req: dict) -> dict:
        section = str(req.get("section", ""))
        values = req.get("values", {}) or {}
        if not section or not isinstance(values, dict):
            raise ValueError("Falta 'section' o 'values'")
        self.config.set(section, values)
        self.config.save()
        if section == "ticktick":
            status = self.gate.poll()
            return {"ok": True, "credits": status.credits, "required": status.required}
        return {"ok": True}

    def _list_op(self, req: dict, section: str, field: str, add: bool) -> dict:
        cfg = self.config.get(section)
        raw = cfg.get(field, []) or []
        value = req.get("value", "") or ""
        value = norm_program(value) if section == "programs" else norm_site(value)
        if not value:
            raise ValueError("Valor inválido o vacío.")

        def _norm(v: str) -> str:
            return norm_program(v) if section == "programs" else norm_site(v)

        items: list[str] = []
        for entry in raw:
            normalized = _norm(entry)
            if normalized and normalized not in items:
                items.append(normalized)

        danger = is_dangerous(value) if section == "programs" else False

        if add:
            if section == "programs" and in_never_block(value):
                return {
                    "ok": False,
                    "immutable": True,
                    "dangerous": True,
                    "value": value,
                    "list": items,
                    "message": (
                        f"{value} es un proceso protegido del sistema: TickFence "
                        "nunca lo bloquea, y agregarlo a la lista no tendría efecto."
                    ),
                }
            opposite = "allowed" if field == "blocked" else "blocked"
            other = [_norm(v) for v in (cfg.get(opposite, []) or [])]
            if value in other:
                self.config.set(section, {opposite: [v for v in other if v != value]})
            if value not in items:
                items.append(value)
            if danger and not req.get("force"):
                return {
                    "ok": False,
                    "needs_confirm": True,
                    "dangerous": True,
                    "value": value,
                    "list": items,
                    "message": (
                        f"{value} es un proceso crítico del sistema. "
                        "Bloquearlo puede dejar la PC inutilizable o impedir que "
                        "la propia app vuelva a abrirse."
                    ),
                }
        else:
            items = [i for i in items if i != value]

        self.config.set(section, {field: items})
        self.config.save()
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
        raise RuntimeError(
            "El IFEO solo existe en Windows con el servicio instalado como administrador."
        )

    def _cmd_install_ready(self, req: dict) -> dict:
        return {
            "service_pid": None,
            "python": None,
            "stub": None,
            "config_path": str(self.config.path),
            "state_path": str(self.store.path),
            "port": self.port,
            "ticktick_ok": self.client.configured,
            "ifeo_applied": [],
            "guard": {"scans": 0, "kills": 0, "running": False},
            "guard_armed": False,
        }

    def _cmd_diag(self, req: dict) -> dict:
        return {
            "mode": "standalone",
            "config_path": str(self.config.path),
            "state_path": str(self.store.path),
            "port": self.port,
        }


def is_protected(name: str) -> bool:
    """Reexportado para que la UI pueda preguntar lo mismo que el motor."""
    return match_program(name, [], []) is False and in_never_block(name)
