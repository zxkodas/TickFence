"""Estado persistente del servicio (contadores, sesión, bitácora de emergencias)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from . import paths

DEFAULT_STATE: dict[str, Any] = {
    "version": 1,
    # False a proposito. El estado por defecto es DESBLOQUEADO: el bloqueo se
    # activa explicitamente desde la app. Arrancar bloqueado sin pedirlo es la
    # forma segura de dejar a alguien encerrado.
    "locked": False,
    "credits": 0,
    "required": 2,
    "lock_started": 0.0,
    "unlock_until": 0.0,
    "unlock_reason": "",
    # Idioma del aviso de bloqueo. El servicio lo refleja desde la config
    # (ver daemon._publish_language): el stub de IFEO no puede leer la config
    # porque ahi esta el token, y el estado es lo unico que puede leer.
    "language": "en",
    "lectura_status": {},      # task_id -> bool completado (para detectar transiciones)
    "lectura_titles": {},      # task_id -> titulo (para nombrar lo que desaparece)
    "credited_ids": [],        # tareas ya acreditadas: evita contar dos veces
    "lectura_seeded": False,   # True una vez tomada la linea base
    "last_poll": 0.0,
    "last_error": "",
    "ticktick_token": "",      # cifrado con DPAPI
    "server_token": "",        # cifrado con DPAPI
    "server_port": 0,
    "emergencies": [],         # bitacora de desbloqueos de emergencia
    "block_events": [],        # ultimas detenciones de procesos
}


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (paths.program_data() / "state.json")
        self._lock = threading.RLock()
        self._data: dict[str, Any] | None = None

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> dict[str, Any]:
        with self._lock:
            if self._data is not None:
                return self._data
            raw: dict[str, Any] = {}
            if self._path.exists():
                try:
                    raw = json.loads(self._path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    raw = {}
            data = dict(DEFAULT_STATE)
            data.update(raw)
            self._data = data
            return self._data

    def write(self) -> None:
        with self._lock:
            if self._data is None:
                self.read()
            payload = json.dumps(self._data, indent=2, ensure_ascii=False)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle, tmp = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=".state-", suffix=".tmp"
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                os.replace(tmp, self._path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            # El token vive acá: solo el dueño lo lee (en Windows lo cubre DPAPI).
            if not sys.platform.startswith("win"):
                try:
                    os.chmod(self._path, 0o600)
                except OSError:
                    pass

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.read().get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self.read()[key] = value
            self.write()

    def update(self, **fields: Any) -> None:
        with self._lock:
            self.read().update(fields)
            self.write()

    def reset_lock_cycle(self, required: int) -> None:
        """Prepara un ciclo de bloqueo nuevo.

        IMPORTANTE: también borra la línea base de `lectura_status`.

        Si no se borra, el ciclo anterior deja las tareas ya completadas
        marcadas como True, y como el credito se giveaway por transición
        False->True, esas tareas nunca vuelven a contar. El sintoma: el
        usuario completa 2 Lecturas y no se desbloquea nunca, porque el
        registro ya decía que estaban hechas desde antes de empezar.
        """
        with self._lock:
            data = self.read()
            data["locked"] = True
            data["credits"] = 0
            data["required"] = required
            data["lock_started"] = time.time()
            data["unlock_until"] = 0.0
            data["unlock_reason"] = ""
            # Línea base nueva: la próxima consulta vuelve a sembrar desde cero.
            data["lectura_status"] = {}
            data["lectura_titles"] = {}
            data["credited_ids"] = []
            data["lectura_seeded"] = False
            self.write()


_store: Store | None = None


def instance() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store
