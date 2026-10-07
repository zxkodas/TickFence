"""Pruebas de la lógica de TickFence. Solo stdlib:  python -m tests.test_focuslock"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from focuslock import emergency as em  # noqa: E402
from focuslock import rules  # noqa: E402
from focuslock import secrets  # noqa: E402
from focuslock.config import Config  # noqa: E402
from focuslock.daemon import Engine  # noqa: E402
from focuslock.gate import Gate  # noqa: E402
from focuslock.ipc import IpcClient, IpcError  # noqa: E402
from focuslock.rules import norm_program  # noqa: E402
from focuslock.secrets import protect, unprotect  # noqa: E402
from focuslock.server import StateServer  # noqa: E402
from focuslock.store import Store  # noqa: E402
from focuslock.ticktick import TickTickError  # noqa: E402


# --------------------------------------------------------------------------
class TestTaskMatching(unittest.TestCase):
    def test_lecturas_count(self):
        for title in ("Lectura 1", "Lectura 4", "Lecturas", "lectura 12", "  Lectura 3"):
            self.assertTrue(rules.title_matches_prefix(title, "Lectura"), title)

    def test_others_do_not_count(self):
        for title in ("TP 1", "TP 4", "Parcial 2", "Modulo 4", "Trabajo práctico", "Repaso"):
            self.assertFalse(rules.title_matches_prefix(title, "Lectura"), title)

    def test_accent_insensitive(self):
        self.assertTrue(rules.title_matches_prefix("Léctura 1", "Lectura"))
        self.assertTrue(rules.title_matches_prefix("ANÁLISIS", "analisis"))

    def test_strip_decoration(self):
        self.assertEqual(rules.strip_decoration("📖Estudios"), "Estudios")
        self.assertEqual(rules.strip_decoration("🔒Vida"), "Vida")
        self.assertEqual(rules.norm_key("📖 Estudios"), "estudios")

    def test_empty_prefix_matches_nothing(self):
        self.assertFalse(rules.title_matches_prefix("Lectura 1", ""))


# --------------------------------------------------------------------------
class TestSiteRules(unittest.TestCase):
    def test_normalization(self):
        # norm_site conserva el path (las reglas con ruta estan soportadas),
        # pero match_host ignora el path: pegar una URL completa bloquea el host entero.
        self.assertEqual(rules.norm_site("https://www.YouTube.com/feed/"), "youtube.com/feed")
        self.assertEqual(rules.norm_site("youtube.com"), "youtube.com")
        self.assertEqual(rules.norm_site("upt.edu.ar/inscripciones"), "upt.edu.ar/inscripciones")
        self.assertEqual(rules.norm_site(""), "")
        self.assertTrue(
            rules.match_host("music.youtube.com", ["https://www.youtube.com/feed/"], [])
        )

    def test_subdomains_are_covered(self):
        blocked = ["youtube.com"]
        allowed: list[str] = []
        for host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
            self.assertTrue(rules.match_host(host, blocked, allowed), host)

    def test_unrelated_host_is_free(self):
        self.assertFalse(rules.match_host("github.com", ["youtube.com"], []))

    def test_allowed_wins(self):
        self.assertFalse(rules.match_host("m.youtube.com", ["youtube.com"], ["m.youtube.com"]))
        self.assertFalse(rules.match_host("music.youtube.com", ["youtube.com"], ["youtube.com"]))
        # un permiso puntual no exime a los hermanos
        self.assertTrue(rules.match_host("www.youtube.com", ["youtube.com"], ["m.youtube.com"]))

    def test_evil_suffix_not_blocked(self):
        # notyoutube.com no debe quedar atrapado por youtube.com
        self.assertFalse(rules.match_host("notyoutube.com", ["youtube.com"], []))

    def test_url_path_rule(self):
        self.assertTrue(rules.match_url("https://upt.edu.ar/inscripciones/x", ["upt.edu.ar/inscripciones"], []))
        self.assertFalse(rules.match_url("https://upt.edu.ar/biblioteca", ["upt.edu.ar/inscripciones"], []))


# --------------------------------------------------------------------------
class TestProgramRules(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(rules.norm_program(r"C:\Games\Steam\steam.exe"), "steam.exe")
        self.assertEqual(rules.norm_program("Discord"), "discord.exe")

    def test_allowed_wins(self):
        self.assertFalse(rules.match_program("steam.exe", ["steam.exe"], ["steam.exe"]))

    def test_block(self):
        self.assertTrue(rules.match_program("steam.exe", ["steam.exe"], []))
        self.assertFalse(rules.match_program("notepad.exe", ["steam.exe"], []))


class TestInterpreterIsUnblockable(unittest.TestCase):
    """TickFence corre sobre Python. Python no se puede bloquear.

    Si el usuario pone pythonw.exe en la lista de bloqueados, el guard mata la
    ventana. El servicio sobrevive (es pythonservice.exe, y ademas protege su
    propio PID), asi que el bloqueo sigue activo: quedas encerrado sin
    ventana para desbloquear.

    Estos tests cubren las dos capas:

      - match_program: el proceso tiene que|matchear| la lista de bloqueados
      - guard.is_dangerous: la UI tiene que avisar antes de confirmarlo
    """

    # (rol, ejecutable real)
    PROCESOS = (
        ("el servicio", "pythonservice.exe"),
        ("la ventana", "pythonw.exe"),
        ("el aviso de bloqueo", "pythonw.exe"),
        ("el modo console", "python.exe"),
    )

    def test_el_guard_nunca_acepta_bloquear_python(self):
        from focuslock import guard

        for nombre in ("python.exe", "pythonw.exe", "pythonservice.exe"):
            with self.subTest(exe=nombre):
                self.assertFalse(
                    rules.match_program(nombre, [nombre], []),
                    f"{nombre} matchea la lista de bloqueados: el guard lo mataria",
                )

    def test_is_dangerous_lo_sabe(self):
        """Sin esto la UI no pide confirmacion y lo agrega en silencio."""
        from focuslock import guard

        for nombre in ("python.exe", "pythonw.exe", "pythonservice.exe"):
            with self.subTest(exe=nombre):
                self.assertTrue(guard.is_dangerous(nombre))

    def test_bloquear_python_no_toca_a_tickfence(self):
        """El escenario completo: bloquear pythonw.exe mata la ventana?

        Este es el que se quedo sin cubrir cuando la app todavia no se
        traducía. El servicio tiene que sobrevivir Y la ventana tambien: si la
        ventana muere con el bloqueo activo, no hay forma de salir.
        """
        from focuslock import guard

        for nombre in ("python.exe", "pythonw.exe", "pythonservice.exe"):
            for rol, ejecutable in self.PROCESOS:
                with self.subTest(bloquea=nombre, rol=rol):
                    matchea = rules.match_program(ejecutable, [nombre], [])
                    if matchea:
                        self.assertTrue(
                            guard.is_dangerous(ejecutable),
                            f"bloquear {nombre} le pega a {rol} ({ejecutable}) "
                            f"y is_dangerous() no lo avisa",
                        )


# --------------------------------------------------------------------------
class TestEmergency(unittest.TestCase):
    CFG = {"emergency": {"min_words": 300, "min_minutes": 5, "unlock_minutes": 20}}

    # Los errores los arma el SERVICIO, que ya sabe el idioma del usuario
    # (daemon lo fija desde la config antes de validar). Cada prueba corre en
    # los dos idiomas: cambiar la expectativa al inglés dejaría el español
    # sin verificar.
    MARCA = {
        "en": {
            "pocas": "words short",
            "rapido": "real writing",
            "pegado": "clipboard",
            "idle": "without writing",
            "prompt": "Incomplete answer",
            "pulsaciones": "keystrokes",
        },
        "es": {
            "pocas": "palabras",
            "rapido": "escritura real",
            "pegado": "portapapeles",
            "idle": "sin escribir",
            "prompt": "Respuesta incompleta",
            "pulsaciones": "pulsación",
        },
    }

    def setUp(self):
        from focuslock import i18n

        self.i18n = i18n
        self._lang_previo = i18n.lang()

    def tearDown(self):
        self.i18n.set_lang(self._lang_previo)

    def _validate(self, sub, lang="en"):
        self.i18n.set_lang(lang)
        return em.validate(sub, self.CFG)

    def _errors(self, sub):
        """Errores que contienen una marca, en el idioma que se pide.

        Devolver todos los idiomas juntos hace que una prueba falle UNA vez
        con un mensaje util, en vez de depender de subTest.
        """
        v = self._validate(sub, "en")
        return [e for e in v.errors
                if any(m in e for m in self.MARCA["en"].values())] + [
            e for e in self._validate(sub, "es").errors
            if any(m in e for m in self.MARCA["es"].values())
        ]

    def _assert_error(self, sub, clave):
        for lang, marcas in self.MARCA.items():
            with self.subTest(lang=lang):
                v = self._validate(sub, lang)
                self.assertFalse(v.ok)
                self.assertTrue(
                    any(marcas[clave] in e for e in v.errors),
                    f"ningun error en {lang} contiene {marcas[clave]!r}: {v.errors}",
                )

    def _good(self, **kw):
        text = "palabra " * 320
        prompts = {t: "respuesta " * 35 for t, _ in em.PROMPTS}
        return em.EmergencySubmission(
            text=text, prompts=prompts, keystrokes=len(text),
            elapsed=330.0, longest_idle=20.0, started_at=time.time(), **kw
        )

    def test_valid_submission_passes(self):
        self.assertTrue(em.validate(self._good(), self.CFG).ok)

    def test_too_short_rejected(self):
        s = self._good()
        s.text = "corto " * 10
        self._assert_error(s, "pocas")

    def test_too_fast_rejected(self):
        s = self._good()
        s.elapsed = 12.0
        self._assert_error(s, "rapido")

    def test_paste_detected(self):
        s = self._good()
        s.keystrokes = 20          # 2000 caracteres en 20 pulsaciones
        self._assert_error(s, "pegado")

    def test_long_idle_rejected(self):
        s = self._good()
        s.longest_idle = 300.0
        self._assert_error(s, "idle")

    def test_incomplete_prompt_rejected(self):
        s = self._good()
        s.prompts[em.PROMPTS[0][0]] = "muy poco"
        self._assert_error(s, "prompt")

    def test_no_keystrokes_rejected(self):
        s = self._good()
        s.keystrokes = 0
        self.assertFalse(em.validate(s, self.CFG).ok)


# --------------------------------------------------------------------------
class _FakeClient:
    def __init__(self, token="tp_test"):
        self._token = token
        self.tasks: list[dict] = []
        self.columns = [{"id": "c1", "name": "Analisis Matematico"}]

    @property
    def configured(self):
        return bool(self._token)

    def projects(self):
        return [{"id": "p1", "name": "📖Estudios", "viewMode": "kanban"}]

    def project_data(self, _pid):
        return {
            "project": {"id": "p1", "name": "Estudios"},
            "tasks": self.tasks,
            "columns": self.columns,
        }

    def complete_task(self, *_a):
        return True

    def test_connection(self):
        return {"ok": True, "projects": 1, "names": ["Estudios"]}


class _BadClient(_FakeClient):
    def test_connection(self):
        raise TickTickError("401/403 token invalido")


def _bare_engine(config: Config | None = None, store: Store | None = None) -> Engine:
    """Engine con lo minimo necesario, sin pipe, HTTP ni vigilante de procesos."""
    cfg = config if config is not None else Config(Path(tempfile.mkdtemp()) / "c.json")
    st = store if store is not None else Store(Path(tempfile.mkdtemp()) / "s.json")
    if not cfg._data:
        cfg.load()
    st.read()
    client = _FakeClient()
    engine = Engine.__new__(Engine)
    engine._lock = threading.RLock()
    engine._stop = threading.Event()
    engine._last_sync = 0.0
    engine.config = cfg
    engine.store = st
    engine.client = client
    engine.gate = Gate(client, cfg, st)
    engine._sync_ifeo = lambda force=False: {}
    return engine


def _task(tid, title, status=0, completed_at=None):
    task = {"id": tid, "title": title, "status": status, "columnId": "c1"}
    if completed_at is not None:
        task["completedTime"] = completed_at
    return task


def _stamp(offset: float = 0.0) -> str:
    """completedTime al estilo de TickTick: ISO con offset sin dos puntos."""
    from datetime import datetime, timedelta, timezone

    when = datetime.now(timezone.utc) + timedelta(seconds=offset)
    return when.strftime("%Y-%m-%dT%H:%M:%S+0000")


class _GateCase(unittest.TestCase):
    """Base con el gateArmado y los asserts de estado.

    `is_unlocked() == True` significa DESBLOQUEADO. Los helpers existen para no
    invertir el sentido por error, que es la falla más fácil de cometer.
    """

    def build(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = Config(self.tmp / "config.json")
        self.cfg.load()
        self.store = Store(self.tmp / "state.json")
        self.store.read()
        self.client = _FakeClient()
        self.gate = Gate(self.client, self.cfg, self.store)
        return self.gate

    def tearDown(self):
        tmp = getattr(self, "tmp", None)
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)

    def assert_locked(self):
        self.assertFalse(self.gate.is_unlocked(), "se esperaba BLOQUEADO")

    def assert_unlocked(self):
        self.assertTrue(self.gate.is_unlocked(), "se esperaba DESBLOQUEADO")


class TestGate(_GateCase):
    def setUp(self):
        self.build()
        self.gate.relock()

    def test_starts_locked_with_zero_credits(self):
        st = self.gate.poll()
        self.assert_locked()
        self.assertEqual(st.credits, 0)
        self.assertEqual(st.required, 2)

    def test_ignores_tp_and_parcial(self):
        """Ya no hay filtro por nombre: cuenta cualquier tarea del proyecto."""
        self.client.tasks = [_task("a", "TP 1"), _task("b", "Parcial 2")]
        st = self.gate.poll()
        self.assertEqual(len(st.pending), 2, "ahora cuentas todas las tareas")
        self.assert_locked()

    def test_one_lectura_is_not_enough(self):
        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        self.gate.poll()
        self.assert_locked()

        self.client.tasks[0]["status"] = 2
        st = self.gate.poll()
        self.assert_locked()
        self.assertEqual(st.credits, 1)
        self.assertEqual(st.remaining(), 1)

    def test_two_lecturas_unlock(self):
        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        self.gate.poll()
        self.client.tasks[0]["status"] = 2
        self.gate.poll()
        self.assert_locked()
        self.client.tasks[1]["status"] = 2
        st = self.gate.poll()
        self.assert_unlocked()
        self.assertEqual(st.credits, 2)
        self.assertEqual(st.remaining(), 0)
        self.assertIn("TickTick", st.unlock_reason)

    def test_no_double_credit_on_repoll(self):
        self.client.tasks = [_task("a", "Lectura 1")]
        self.gate.poll()
        self.client.tasks[0]["status"] = 2
        self.gate.poll()
        for _ in range(4):
            self.gate.poll()
        self.assertEqual(self.store.get("credits"), 1)

    def test_empty_project_counts_as_finished_work(self):
        """Vaciar el proyecto cuenta como trabajo. Decision del usuario.

        Tus tareas son recurrentes: al completarlas desaparecen del proyecto en
        vez de quedar archivadas. Para una app asi, "el proyecto vino vacio" es
        la senal de que terminaste, no un fallo. Si se lousha, completar TODAS
        las tareas del proyecto no bonifica y te deja trabado sin salida
        aparente.

        El precio, asumido a conscious: si TickTick devolviera el proyecto vacio
        por un fallo puntual, el bloqueo se abriria sin trabajo. Es el unico
        punto ciego, y la red de seguridad sigue siendo el desbloqueo de
        emergencia.
        """
        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        self.gate.relock()
        self.gate.poll()                     # siembra: 2 pendientes

        self.client.tasks = []               # completadas las 2 -> proyecto vacio
        st = self.gate.poll()

        self.assertEqual(st.credits, 2, "vaciar el proyecto acredita lo que hiciste")
        self.assert_unlocked()
        self.assertEqual(st.error, "", "no es un error, es el caso normal")

    def test_empty_project_without_baseline_does_not_seed(self):
        """Sin linea base previa, un vacio no se procesa: no hay nada que comparar.

        Esta es la proteccion que sobrevive. Es la primera consulta de un ciclo:
        si el proyecto vuelve vacioTodavia no sabemos si terminaste o fallo
        TickTick, y no hay con que contrastar, asi que no se siembra nada ni se
        acredita.
        """
        self.client.tasks = []
        st = self.gate.poll()                 # primera consulta, sin sembrar antes

        self.assertEqual(st.credits, 0, "no hay linea base: no se acredita nada")
        self.assert_locked()
        self.assertNotEqual(st.error, "", "pero avisa del problema")
        self.assertEqual(self.store.get("lectura_status"), {}, "no siembra nada")

    def test_recovery_after_empty_project_keeps_working(self):
        """Si el proyecto vuelve a tener tareas, el ciclo sigue normal."""
        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        self.gate.relock()
        self.gate.poll()

        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        st = self.gate.poll()
        self.assertEqual(st.error, "")
        self.assertEqual(len(st.pending), 2)

    def test_preexisting_completed_lecturas_give_no_credit(self):
        """Bug REAL: al instalar, Lecturas ya terminadas de antes no pueden
        acreditar nada. Se siembra la linea base sin dar creditos."""
        self.client.tasks = [
            _task("a", "Lectura 1", 2),
            _task("b", "Lectura 2", 2),
            _task("c", "Lectura 3", 2),
        ]
        st = self.gate.poll()
        self.assertEqual(st.credits, 0, "no debe acreditar trabajo viejo")
        self.assert_locked()
        self.assertEqual(len(st.done), 3, "pero si las muestra como completadas")

    def test_new_lectura_counts_only_after_being_seen_pending(self):
        self.client.tasks = [_task("a", "Lectura 1", 2)]
        self.gate.poll()
        self.assertEqual(self.store.get("credits"), 0)

        # aparece una Lectura nueva todavia pendiente
        self.client.tasks.append(_task("d", "Lectura 4", 0))
        st = self.gate.poll()
        self.assertEqual(st.credits, 0)

        # ahora la completo
        self.client.tasks[1]["status"] = 2
        st = self.gate.poll()
        self.assertEqual(st.credits, 1)
        self.assert_locked()

        # y una segunda
        self.client.tasks.append(_task("e", "Lectura 5", 0))
        self.gate.poll()
        self.client.tasks[2]["status"] = 2
        st = self.gate.poll()
        self.assertEqual(st.credits, 2)
        self.assert_unlocked()

    def test_completedTime_marks_task_done_without_credit(self):
        self.client.tasks = [dict(_task("a", "Lectura 1"), completedTime="2026-01-01T00:00:00+0000")]
        st = self.gate.poll()
        self.assertEqual(st.credits, 0)
        self.assertEqual(len(st.done), 1)

    def test_task_appearing_already_done_gives_no_credit(self):
        """Si la API devuelve una lista truncada y una tarea reaparece ya
        completada, no debe contar: solo valen las transiciones de una tarea
        que ya habiamos visto pendiente."""
        self.client.tasks = [_task("a", "Lectura 1")]
        self.gate.poll()                      # siembra: "a" queda como pendiente
        self.client.tasks[0]["status"] = 2
        self.gate.poll()                      # credito legitimo
        self.assertEqual(self.store.get("credits"), 1)

        # desaparece del historial y reaparece "nueva", ya completada
        self.store.set("lectura_status", {})
        st = self.gate.poll()
        self.assertEqual(st.credits, 1, "no debe sumar otro credito")

    def test_credit_requires_task_to_have_been_seen_pending(self):
        self.client.tasks = [_task("a", "Lectura 1", 2)]
        self.gate.poll()
        self.assertEqual(self.store.get("credits"), 0)
        self.client.tasks[0]["status"] = 0
        self.gate.poll()
        self.client.tasks[0]["status"] = 2
        st = self.gate.poll()
        self.assertEqual(st.credits, 1)

    def test_relock_resets_credits(self):
        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        self.gate.poll()
        for t in self.client.tasks:
            t["status"] = 2
        self.gate.poll()
        self.assert_unlocked()
        self.gate.relock()
        self.assert_locked()
        self.assertEqual(self.gate.credits(), 0)

    def test_emergency_unlock_is_temporary(self):
        self.gate.unlock_now("emergencia", minutes=20)
        self.assert_unlocked()
        self.assertTrue(self.gate.is_unlocked(now=time.time() + 10 * 60))
        expired = self.gate.is_unlocked(now=time.time() + 21 * 60)
        self.assertFalse(expired, "al expirar debe re-bloquear solo, sin pedir nada")

    def test_modules_are_grouped(self):
        """Ahora cuenta cualquier tarea, así que la columna cuenta todo."""
        self.client.columns = [
            {"id": "c1", "name": "Analisis Matematico"},
            {"id": "c2", "name": "Produccion"},
        ]
        self.client.tasks = [
            _task("a", "Lectura 1"),
            _task("b", "TP 1"),
            dict(_task("c", "Lectura 2"), columnId="c2"),
        ]
        st = self.gate.poll()
        self.assertEqual(st.modules.get("Analisis Matematico"), 2)
        self.assertEqual(st.modules.get("Produccion"), 1)


# --------------------------------------------------------------------------
class TestListOperations(unittest.TestCase):
    """Normalizacion y coherencia de las listas de bloqueo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = Config(self.tmp / "config.json")
        self.cfg.load()
        self.store = Store(self.tmp / "state.json")
        self.store.read()
        # Engine sin arrancar el pipe/http: probamos solo la logica de listas.
        self.engine = _bare_engine(self.cfg, self.store)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_program_is_normalized(self):
        r = self.engine.handle("programs_blocked_add", {"value": r"C:\Games\Steam\STEAM.EXE"})
        self.assertIn("steam.exe", r["list"])
        self.assertEqual(len([x for x in r["list"] if x == "steam.exe"]), 1)

    def test_site_strips_scheme_www_and_query(self):
        r = self.engine.handle(
            "sites_blocked_add", {"value": "https://www.YouTube.com/watch?v=abc#t=10"}
        )
        self.assertIn("youtube.com", r["list"])

    def test_adding_to_allowed_moves_it_out_of_blocked(self):
        self.engine.handle("programs_blocked_add", {"value": "steam.exe"})
        r = self.engine.handle("programs_allowed_add", {"value": "steam.exe"})
        self.assertIn("steam.exe", r["list"])
        blocked = self.cfg.get("programs")["blocked"]
        self.assertNotIn("steam.exe", blocked)

    def test_adding_to_blocked_moves_it_out_of_allowed(self):
        self.engine.handle("programs_allowed_add", {"value": "discord.exe"})
        r = self.engine.handle("programs_blocked_add", {"value": "Discord.exe"})
        self.assertIn("discord.exe", r["list"])
        self.assertNotIn("discord.exe", self.cfg.get("programs")["allowed"])

    def test_duplicates_are_collapsed(self):
        for value in ("steam.exe", "Steam.EXE", r"C:\x\steam.exe"):
            self.engine.handle("programs_blocked_add", {"value": value})
        count = [x for x in self.cfg.get("programs")["blocked"] if x == "steam.exe"]
        self.assertEqual(len(count), 1)

    def test_dangerous_program_requires_confirmation(self):
        r = self.engine.handle("programs_blocked_add", {"value": "cmd.exe"})
        self.assertTrue(r.get("needs_confirm"))
        self.assertNotIn("cmd.exe", self.cfg.get("programs")["blocked"])

        r = self.engine.handle(
            "programs_blocked_add", {"value": "cmd.exe", "force": True}
        )
        self.assertTrue(r.get("ok"))
        self.assertIn("cmd.exe", self.cfg.get("programs")["blocked"])

    def test_never_block_cannot_be_added_even_with_force(self):
        """explorer.exe y opencode.exe jamas deben entrar en la lista de
        bloqueados, ni siquiera con force=True."""
        for name in ("explorer.exe", "OpenCode.exe", "lsass.exe", "csrss.exe"):
            r = self.engine.handle("programs_blocked_add", {"value": name, "force": True})
            self.assertTrue(r.get("immutable"), f"{name} deberia ser inmutable")
            self.assertFalse(r.get("ok"))
            self.assertNotIn(norm_program(name), self.cfg.get("programs")["blocked"])

    def test_explorer_is_not_removed_from_allowed_when_protected(self):
        """Pedir explorer.exe bloqueado no debe sacarlo de la lista de permitidos."""
        self.engine.handle("programs_allowed_add", {"value": "notepad.exe"})
        self.engine.handle("programs_blocked_add", {"value": "explorer.exe", "force": True})
        self.assertIn("notepad.exe", self.cfg.get("programs")["allowed"])

    def test_never_block_wins_even_when_allowlisted(self):
        # svchost.exe esta en NEVER_BLOCK: nunca debe quedar bloqueado.
        r = self.engine.handle("programs_blocked_add", {"value": "svchost.exe"})
        self.assertTrue(r.get("needs_confirm") or r.get("dangerous"))
        blocked = self.cfg.get("programs")["blocked"]
        if "svchost.exe" not in blocked:
            self.assertFalse(rules.match_program("svchost.exe", blocked, []))

    def test_empty_value_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.handle("programs_blocked_add", {"value": "   "})


class TestTokenCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = Config(self.tmp / "config.json")
        self.cfg.load()
        self.store = Store(self.tmp / "state.json")
        self.store.read()
        self.engine = _bare_engine(self.cfg, self.store)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bad_token_does_not_overwrite_good_one(self):
        good = secrets.protect("tp_bueno")
        self.store.set("ticktick_token", good)
        # Inyectamos un cliente que siempre falla, sin tocar la red.
        from focuslock import daemon as daemon_mod

        original = daemon_mod.TickTickClient
        daemon_mod.TickTickClient = _BadClient
        self.addCleanup(setattr, daemon_mod, "TickTickClient", original)

        r = self.engine._cmd_ticktick_set_token({"token": "tp_malo"})
        self.assertFalse(r.get("ok"))
        self.assertEqual(
            self.store.get("ticktick_token"), good, "el token bueno debe intacto"
        )

    def test_good_token_is_stored_encrypted(self):
        # Cliente de red inyectado: valida el camino feliz sin salir a internet.
        from focuslock import daemon as daemon_mod

        original = daemon_mod.TickTickClient
        daemon_mod.TickTickClient = _FakeClient
        self.addCleanup(setattr, daemon_mod, "TickTickClient", original)

        r = self.engine._cmd_ticktick_set_token({"token": "tp_nuevo"})
        self.assertTrue(r.get("ok"), f"esperaba ok, vino {r!r}")
        blob = self.store.get("ticktick_token")
        self.assertNotIn("tp_nuevo", blob, "el token no debe quedar en claro")
        self.assertEqual(secrets.unprotect(blob), "tp_nuevo")

    def test_unknown_command_is_rejected(self):
        with self.assertRaises(KeyError):
            self.engine.handle("hackear_todo", {})


class TestSecrets(unittest.TestCase):
    def test_roundtrip(self):
        # Token inventado con la forma real de TickTick. Nunca pegues uno
        # verdadero acá: el repo es público para cualquiera que lo clone.
        token = "tp_" + "0" * 32
        blob = protect(token)
        self.assertNotIn(token, blob)
        self.assertEqual(unprotect(blob), token)


# --------------------------------------------------------------------------
class TestIpcClientErrors(unittest.TestCase):
    """El cliente debe convertir los errores de Win32 en mensajes claros."""

    def test_missing_pipe_gives_friendly_error(self):
        client = IpcClient(pipe=r"\\.\pipe\TickFenceNoExiste_TEST")
        with self.assertRaises(IpcError) as ctx:
            client.call("status", retries=0)
        self.assertIn("TickFence", str(ctx.exception))

    def test_retryable_codes_are_defined(self):
        from focuslock.ipc import _RETRYABLE

        for code in (2, 231, 233):
            self.assertIn(code, _RETRYABLE)

    def test_pywintypes_error_is_not_oserror(self):
        # Solo Windows: pywintypes.error no hereda de OSError y hay que
        # capturarlo por separado. En Linux no hay pywintypes.
        if not sys.platform.startswith("win"):
            self.skipTest("solo Windows")
        import pywintypes

        self.assertFalse(issubclass(pywintypes.error, OSError))
        self.assertTrue(issubclass(pywintypes.error, Exception))


class TestStateServer(unittest.TestCase):
    def setUp(self):
        self.payload = {"locked": True, "blockedHosts": ["youtube.com"], "allowedHosts": [], "credits": 1, "required": 2}
        # Puerto distinto al de producción: si el servicio está corriendo,
        # pedir el fijo haría fallar el bind.
        self.server = StateServer(lambda: self.payload, port=0)
        self.port = self.server.start()
        self.url = f"http://127.0.0.1:{self.port}/state?token={self.server.token}"

    def tearDown(self):
        self.server.stop()

    def test_accepts_null_origin(self):
        """Regresión: Firefox manda `Origin: null` desde el popup MV3.

        Rechazarlo daba 403 y el popup mostraba "sin conexión" mientras el
        servicio estaba perfecto y el bloqueo funcionando.
        """
        import urllib.error
        import urllib.request

        req = urllib.request.Request(self.url)
        req.add_header("Origin", "null")
        data = urllib.request.urlopen(req).read()
        self.assertIn(b"blockedHosts", data)

    def test_rejects_foreign_origin(self):
        """Un sitio web cualquiera no puede leer el estado."""
        import urllib.error
        import urllib.request

        req = urllib.request.Request(self.url)
        req.add_header("Origin", "https://sitio-malo.example")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_default_port_is_fixed(self):
        """Puerto fijo: la extensión guarda la dirección con el puerto adentro.

        Si fuera efímero, cada reinicio del servicio invalidaría la dirección
        y la extensión dejaría de bloquear sin avisar.
        """
        server = StateServer(lambda: {})
        self.assertNotEqual(
            server._requested_port, 0, "el puerto por defecto no puede ser efímero"
        )
        self.assertGreater(server._requested_port, 1024)

    def test_requires_token(self):
        import urllib.error
        import urllib.request

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/state?token=wrong")
        self.assertEqual(ctx.exception.code, 403)

    def test_returns_state(self):
        import urllib.request

        data = json.loads(urllib.request.urlopen(self.url).read())
        self.assertTrue(data["locked"])
        self.assertEqual(data["blockedHosts"], ["youtube.com"])

    def test_health_needs_no_token(self):
        import urllib.request

        data = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health").read())
        self.assertTrue(data["ok"])

    def test_rejects_foreign_origin(self):
        import urllib.error
        import urllib.request

        req = urllib.request.Request(self.url)
        req.add_header("Origin", "https://sitio-malo.example")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)


# --------------------------------------------------------------------------
class TestConfigReload(unittest.TestCase):
    """El servicio tiene que enterarse de los cambios hechos en el archivo.

    Sin esto, editar config.json a mano deja el IFEO con claves de programas
    que ya no estan bloqueados, y no hay forma de limpiarlas desde la UI.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "config.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _edit_on_disk(self, blocked: list[str]) -> None:
        """Escribe el archivo por fuera, como haria un editor o el usuario."""
        data = {"programs": {"blocked": blocked}}
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_reload_detects_external_change(self):
        self._edit_on_disk(["steam.exe", "discord.exe"])
        cfg = Config(self.path)
        cfg.load()
        self.assertEqual(len(cfg.get("programs")["blocked"]), 2)

        # Alguien edita el archivo a mano.
        self._edit_on_disk(["spotify.exe"])

        self.assertTrue(cfg.reload_if_changed(), "deberia detectar el cambio")
        self.assertEqual(cfg.get("programs")["blocked"], ["spotify.exe"])

    def test_reload_is_noop_when_unchanged(self):
        self._edit_on_disk(["steam.exe"])
        cfg = Config(self.path)
        cfg.load()
        self.assertFalse(cfg.reload_if_changed(), "sin cambios no debe recargar")

    def test_own_save_does_not_trigger_reload(self):
        self._edit_on_disk(["steam.exe"])
        cfg = Config(self.path)
        cfg.load()
        cfg.set("programs", {"blocked": ["discord.exe"]})
        cfg.save()
        self.assertFalse(
            cfg.reload_if_changed(), "un save propio no debe pedir recarga"
        )
        self.assertEqual(cfg.get("programs")["blocked"], ["discord.exe"])

    def test_reload_before_first_load(self):
        cfg = Config(self.path)
        self.assertTrue(cfg.reload_if_changed(), "la primera vez siempre carga")

    def test_missing_file_is_not_fatal(self):
        """Sin archivo, la lista de bloqueados arranca vacía a propósito."""
        cfg = Config(self.tmp / "no-existe.json")
        cfg.load()  # no debe levantar
        self.assertEqual(cfg.get("programs")["blocked"], [])
        self.assertFalse(cfg.get("general")["start_locked"])

    def test_corrupt_file_falls_back_to_defaults(self):
        self.path.write_text("{esto no es json", encoding="utf-8")
        cfg = Config(self.path)
        cfg.load()
        self.assertEqual(cfg.get("ticktick")["project_name"], "Estudios")
        self.assertEqual(cfg.get("ticktick")["required"], 2)


class TestOptInBlocking(unittest.TestCase):
    """El bloqueo tiene que ser opt-in.

    Requisito explícito del usuario: abrir TickFence no debe activar el
    bloqueo. Si arrancara bloqueado, un día sin ganas de hacer lecturas lo
    dejaría encerrado sin haberlo pedido.
    """

    def test_default_config_has_empty_blocklist(self):
        from focuslock.config import DEFAULTS

        self.assertEqual(
            DEFAULTS["programs"]["blocked"], [],
            "la lista por defecto no debe bloquear nada",
        )

    def test_default_is_not_start_locked(self):
        from focuslock.config import DEFAULTS

        self.assertFalse(
            DEFAULTS["general"]["start_locked"],
            "arrancar no debe activar el bloqueo",
        )

    def test_default_state_is_unlocked(self):
        from focuslock.store import DEFAULT_STATE

        self.assertFalse(
            DEFAULT_STATE["locked"],
            "el estado inicial debe ser desbloqueado",
        )

    def test_fresh_state_is_unlocked(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            store = Store(tmp / "state.json")
            store.read()
            self.assertFalse(store.get("locked"))
            self.assertEqual(store.get("credits"), 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unlock_is_always_possible(self):
        """Prender y apagar tienen que funcionar en ambos sentidos."""
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = Config(tmp / "config.json")
            cfg.load()
            store = Store(tmp / "state.json")
            store.read()
            gate = Gate(_FakeClient(), cfg, store)

            self.assertTrue(gate.is_unlocked(), "empieza desbloqueado")

            gate.relock()
            self.assertFalse(gate.is_unlocked(), "relock bloquea")

            gate.unlock_now("apagado a mano")
            self.assertTrue(gate.is_unlocked(), "unlock desbloquea")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_emergency_unlocks_are_never_permanent(self):
        """Una emergencia no puede dejar el bloqueo puesto para siempre."""
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = Config(tmp / "config.json")
            cfg.load()
            store = Store(tmp / "state.json")
            store.read()
            gate = Gate(_FakeClient(), cfg, store)

            gate.relock()
            gate.unlock_now("emergencia", minutes=20)
            self.assertTrue(gate.is_unlocked())
            # al expirar vuelve a bloquear, no queda abierto para siempre
            self.assertTrue(gate.is_unlocked(now=time.time() + 10))
            self.assertFalse(gate.is_unlocked(now=time.time() + 21 * 60))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCompletedTimeRule(_GateCase):
    """El credito se decide por `completedTime`, no por una linea base sembrada.

    La linea base tenía un fallo_reportado: si la siembra corría después de que
    el usuario tachara sus Lecturas, quedaban marcadas como "ya hechas" y no
    contaban nunca. Con completedTime no importa el orden.
    """

    def setUp(self):
        self.build()

    def test_readings_done_before_locking_do_not_count(self):
        self.client.tasks = [_task("a", "Lectura 1", 2, _stamp(-3600))]
        self.gate.relock()
        st = self.gate.poll()
        self.assertEqual(st.credits, 0, "lo hecho antes de activar no cuenta")
        self.assert_locked()

    def test_readings_done_after_locking_count(self):
        self.gate.relock()
        self.gate.poll()                       # siembra
        self.client.tasks = [_task("a", "Lectura 1", 2, _stamp(-5))]
        st = self.gate.poll()
        self.assertEqual(st.credits, 1, "una Lectura tachada despues debe contar")
        self.assert_locked()

    def test_vanishing_tasks_count(self):
        """Regresión del caso real: tus tareas se reinician al tacharlas.

        TickTick saca la tarea del proyecto en vez de marcarla completada, así
        que no hay transición que ver. Lo que se detecta es que estaba y dejó
        de estar.
        """
        self.gate.relock()
        self.client.tasks = [
            _task("m1", "Modulo 4"),
            _task("a", "Lectura 1"),
            _task("b", "Lectura 2"),
            _task("c", "Lectura 3"),
        ]
        self.gate.poll()
        self.assertEqual(self.store.get("credits"), 0)

        # El usuario tacha 2: desaparecen del proyecto.
        self.client.tasks = [_task("m1", "Modulo 4"), _task("c", "Lectura 3")]
        st = self.gate.poll()
        self.assertEqual(st.credits, 2, "las 2 que desaparecen cuentan")
        self.assert_unlocked()

    def test_credited_tasks_are_not_counted_twice(self):
        """Si una tarea desaparece y vuelve, no tiene que contar dos veces."""
        self.gate.relock()
        self.client.tasks = [_task("m1", "Modulo 4"), _task("a", "Lectura 1")]
        self.gate.poll()
        self.client.tasks = [_task("m1", "Modulo 4")]
        st = self.gate.poll()
        self.assertEqual(st.credits, 1)

        # reaparece
        self.client.tasks = [_task("m1", "Modulo 4"), _task("a", "Lectura 1")]
        st = self.gate.poll()
        self.assertEqual(st.credits, 1, "no debe volver a contar")

    def test_any_task_name_counts(self):
        """Ya no importa que se llame Lectura: cuenta cualquier tarea."""
        self.gate.relock()
        self.client.tasks = [_task("a", "TP 1"), _task("b", "Parcial 2")]
        self.gate.poll()
        # "TP 1" desaparece del proyecto: cuenta.
        self.client.tasks = [_task("b", "Parcial 2")]
        st = self.gate.poll()
        self.assertEqual(st.credits, 1)
        titles = [i.title for i in st.done]
        self.assertIn("TP 1", titles)

    def test_the_reported_bug(self):
        """Reproduce exactamente lo que le paso al usuario.

        Activa el bloqueo, la app reinicia el servicio, y las Lecturas ya
        estaban tachadas. Con la linea base quedaban quemadas para siempre.
        """
        self.gate.relock()
        # Las tachó 10 segundos despues de activar.
        self.client.tasks = [
            _task("a", "Lectura 1", 2, _stamp(-10)),
            _task("b", "Lectura 2", 2, _stamp(-8)),
            _task("c", "Lectura 3", 0),
        ]
        # El servicio se reinicia: la linea base se pierde.
        self.store.set("lectura_status", {})
        self.store.set("lectura_seeded", False)

        st = self.gate.poll()
        self.assertEqual(
            st.credits, 2,
            "las 2 Lecturas tachadas despues de activar tienen que contar, "
            "aunque se haya perdido la linea base",
        )
        self.assert_unlocked()

    def test_stale_readings_never_credit(self):
        """Lecturas viejas no cuentan aunque se repollien 50 veces."""
        self.gate.relock()
        self.client.tasks = [_task("a", "Lectura 1", 2, _stamp(-86400 * 30))]
        for _ in range(5):
            st = self.gate.poll()
            self.assertEqual(st.credits, 0)
        self.assert_locked()

    def test_order_does_not_matter(self):
        """Tachar antes o despues de activar da el mismo resultado."""
        self.gate.relock()
        self.client.tasks = [_task("a", "Lectura 1", 2, _stamp(-2))]
        st = self.gate.poll()
        self.assertEqual(st.credits, 1)

    def test_tolerance_for_clock_skew(self):
        """Un reloj de TickTick atrasado no puede hacerte perder el credito."""
        self.gate.relock()
        # Completada 30s "antes" del bloqueo por desfas del servidor.
        self.client.tasks = [_task("a", "Lectura 1", 2, _stamp(-30))]
        st = self.gate.poll()
        self.assertEqual(st.credits, 1, "30s de desfase no deben perder el credito")

    def test_falls_back_to_transitions_without_completedtime(self):
        """Si la API no manda completedTime, se usa la transición."""
        self.gate.relock()
        self.client.tasks = [_task("a", "Lectura 1", 0)]
        self.gate.poll()
        self.client.tasks[0]["status"] = 2
        st = self.gate.poll()
        self.assertEqual(st.credits, 1)

    def test_done_list_is_populated(self):
        """La lista de completadas de la UI no puede venir vacía."""
        self.gate.relock()
        self.client.tasks = [_task("a", "Lectura 1", 2, _stamp(-5))]
        st = self.gate.poll()
        titles = [i.title for i in st.done]
        self.assertIn("Lectura 1", titles)

    def test_poll_does_not_raise_on_completedtime(self):
        """Regresión: completedTime vive en la tarea cruda, no en el dataclass.

        Pasarle el dataclass a una función que espera el dict de la API tiraba
        AttributeError en cada poll, y el contador se quedaba en 0 para siempre
        sin avisar nada visible.
        """
        self.gate.relock()
        self.client.tasks = [
            _task("a", "Lectura 1", 2, _stamp(-5)),
            _task("b", "Lectura 2", 2, _stamp(-4)),
        ]
        st = self.gate.poll()   # no debe levantar
        self.assertEqual(st.error, "", f"hubo error: {st.error}")
        self.assertEqual(st.credits, 2)

    def test_error_is_surfaced_not_swallowed(self):
        """Si el poll falla, el error tiene que verse en el estado."""
        self.gate.relock()
        self.client.project_data = lambda _pid: (_ for _ in ()).throw(
            ValueError("boom")
        )
        st = self.gate.poll()
        self.assertIn("boom", st.error)


class TestCompletedAtParsing(unittest.TestCase):
    def test_formats(self):
        from focuslock.gate import _completed_at

        expected = 1769342400.0
        for raw in (
            "2026-01-25T12:00:00+0000",
            "2026-01-25T12:00:00Z",
            "2026-01-25T12:00:00+00:00",
            "2026-01-25T12:00:00",
            "2026-01-25T09:00:00-0300",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(_completed_at({"completedTime": raw}), expected)

    def test_none_when_missing(self):
        from focuslock.gate import _completed_at

        for raw in (None, "", 123, "no es fecha", {}):
            with self.subTest(raw=raw):
                self.assertIsNone(_completed_at({"completedTime": raw}))

    def test_no_completedtime_key(self):
        from focuslock.gate import _completed_at

        self.assertIsNone(_completed_at({"id": "x"}))


class TestLockCycleBaseline(_GateCase):
    """Regresión del bug reportado: activar el bloqueo y que nunca se libere."""

    def setUp(self):
        self.build()

    def test_relock_clears_the_baseline(self):
        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        self.gate.poll()                       # siembra
        self.client.tasks[0]["status"] = 2
        self.gate.poll()                       # credito 1
        self.assertEqual(self.store.get("credits"), 1)

        # Nuevo ciclo: como si el usuario activara el bloqueo.
        self.gate.relock()

        self.assertEqual(self.store.get("credits"), 0)
        self.assertEqual(
            self.store.get("lectura_status"), {},
            "la linea base debe borrarse al reiniciar el ciclo",
        )
        self.assertFalse(
            self.store.get("lectura_seeded"),
            "debe volver a sembrarse en la proxima consulta",
        )

    def test_readings_done_before_locking_do_not_count(self):
        """Las Lecturas ya terminadas antes de activar no acreditan.

        Es lo correcto: si ya las habías hecho, no cuenta como trabajo de
        esta sesión. Y al borrar la línea base, no quedan "quemadas" para
        siempre.
        """
        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        self.gate.poll()
        for t in self.client.tasks:
            t["status"] = 2
        self.gate.poll()          # el las ve completadas

        self.gate.relock()        # activar bloqueo
        st = self.gate.poll()     # nueva siembra
        self.assertEqual(st.credits, 0, "lo ya hecho antes no cuenta")
        self.assert_locked()

        # y ahora sí: completar 2 durante el bloqueo desbloquea
        self.client.tasks.append(_task("c", "Lectura 3", 0))
        self.client.tasks.append(_task("d", "Lectura 4", 0))
        self.gate.poll()
        self.client.tasks[2]["status"] = 2
        self.gate.poll()
        self.client.tasks[3]["status"] = 2
        st = self.gate.poll()
        self.assertEqual(st.credits, 2)
        self.assert_unlocked()

    def test_readings_done_while_blocked_always_count(self):
        """El caso normal: activar, trabajar, desbloquear."""
        self.client.tasks = [_task("a", "Lectura 1"), _task("b", "Lectura 2")]
        self.gate.relock()
        self.gate.poll()          # siembra tras activar

        self.client.tasks[0]["status"] = 2
        self.gate.poll()
        self.assertEqual(self.store.get("credits"), 1)
        self.assert_locked()

        self.client.tasks[1]["status"] = 2
        st = self.gate.poll()
        self.assertEqual(st.credits, 2)
        self.assert_unlocked()

    def test_two_consecutive_cycles(self):
        """El segundo ciclo tiene que funcionar igual que el primero.

        Cada ciclo usa tareas nuevas, como pasa en la vida real.
        """
        for ciclo in range(2):
            with self.subTest(ciclo=ciclo):
                a, b = f"a{ciclo}", f"b{ciclo}"
                self.client.tasks = [_task(a, "Lectura 1"), _task(b, "Lectura 2")]
                self.gate.relock()
                self.gate.poll()
                # el usuario tacha 2: desapareyen del proyecto
                self.client.tasks = []
                st = self.gate.poll()
                self.assertEqual(st.credits, 2, f"ciclo {ciclo}")
                self.assert_unlocked()


class TestConfigRoundTrip(unittest.TestCase):
    def test_merge_keeps_defaults(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = Config(tmp / "c.json")
            cfg.load()
            cfg.set("ticktick", {"required": 5})
            cfg.save()
            again = Config(tmp / "c.json")
            again.load()
            self.assertEqual(again.get("ticktick")["required"], 5)
            self.assertEqual(again.get("ticktick")["project_name"], "Estudios")
            self.assertEqual(again.get("programs")["blocked"], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _ServicioFalso:
    """Doble del servicio, con la falla que importa.

    service.stop() NO lanza excepcion cuando no puede parar el servicio: agota el
    tiempo de espera y devuelve. Un doble que solo implemente stop() lanzando
    excepcion reproduciria el bug equivocado, y por eso este tiene un flag.
    """

    def __init__(self, corriendo=True, puede_parar=True, instalado=True):
        self.corriendo = corriendo
        self.puede_parar = puede_parar
        self.instalado = instalado
        self.paradas = 0

    def is_running(self):
        return self.corriendo

    def _is_installed(self):
        return self.instalado

    def stop(self, timeout=15.0):
        self.paradas += 1
        if self.puede_parar:
            self.corriendo = False

    def start(self, timeout=20.0):
        self.corriendo = True
        return True


class TestResetFallaSinElServicioParado(unittest.TestCase):
    """reset no puede decir "Listo" si el servicio sigue vivo.

    El reset escribe el estado y el servicio lo sobreescribe con lo que tiene en
    memoria. Pasa siempre, en ~14 segundos, y el comando igual imprimia "Listo".
    Un test normal no lo caza: hay que dejar el servicio fijo en RUNNING.
    """

    def test_stop_que_no_lanza_no_alcanza_para_aber_si_paro(self):
        from focuslock.reset import _detener_servicio

        parado, motivo = _detener_servicio(_ServicioFalso(puede_parar=False))
        self.assertFalse(
            parado,
            "stop() no lanza excepcion: hay que preguntar despues si quedo "
            "parado. Sin esto el reset cree que frene el servicio y no frena nada",
        )
        self.assertIn("RUNNING", motivo)

    def test_detener_falla_si_stop_lanza(self):
        from focuslock.reset import _detener_servicio

        class _Explota(_ServicioFalso):
            def stop(self, timeout=15.0):
                raise PermissionError("Acceso denegado.")

        parado, motivo = _detener_servicio(_Explota())
        self.assertFalse(parado)
        self.assertIn("Acceso denegado", motivo)

    def test_detener_exito_cuando_frena(self):
        from focuslock.reset import _detener_servicio

        parado, motivo = _detener_servicio(_ServicioFalso())
        self.assertTrue(parado, f"motivo: {motivo}")

    def test_sin_el_servicio_parado_no_escribe_nada(self):
        """Lo que importa: no tocar el archivo si el efecto se va a perder."""
        import tempfile

        from focuslock.reset import main

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            st = raiz / "state.json"
            (raiz / "config.json").write_text(
                '{"general": {}, "programs": {}}', encoding="utf-8")
            original = '{"locked": true, "credits": 7}'
            st.write_text(original, encoding="utf-8")

            with mock.patch("focuslock.service.is_running",
                            return_value=True), \
                 mock.patch("focuslock.service.stop"), \
                 mock.patch("focuslock.service._is_installed",
                            return_value=True), \
                 mock.patch("focuslock.reset.reset") as reset_falso, \
                 mock.patch("focuslock.ifeo.list_blocked", return_value=[]):
                codigo = main()

            self.assertNotEqual(
                0, codigo,
                "tiene que salir con error cuando el servicio sigue vivo",
            )
            self.assertFalse(
                reset_falso.called,
                "no debe escribir nada: el servicio lo sobreescribe igual",
            )
            self.assertEqual(
                original, st.read_text(encoding="utf-8"),
                "el archivo de estado quedo tocado sin efecto",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
