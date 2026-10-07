"""Traducciones de la interfaz.

Por que el ingles es el literal en el codigo y no una clave: si la clave
fuera el ingles ("app.bloquear"), leer el codigo seria traducir mentalmente
en cada linea. Con el ingles como literal, `tr("Active lock")` se lee solo y
la tabla ES queda en un solo lugar.

El idioma vive en config.json y se fija una vez al arrancar con
`set_lang()`. Todo lo que se muestra despues pasa por `tr()`.

OJO con el stub: `focuslock/stub.py` NO importa este modulo. Ese archivo lo
lanza Windows fuera del paquete y tiene que arrancar aunque focuslock no sea
importable (por eso es solo stdlib). Sus textos estan duplicados alla a mano,
y `test_i18n` verifica que las dos copias no se separen.
"""
from __future__ import annotations

_IDIOMA = "en"

# Idiomas que la app acepta. "en" es el literal, asi que no necesita entrada.
IDIOMAS = ("en", "es")

NOMBRES = {
    "en": "English",
    "es": "Español",
}

# Clave = el texto en ingles, que es lo que esta escrito en el codigo.
# Valor = como se muestra si el usuario eligio español.
ES: dict[str, str] = {
    # -- diálogo de emergencia ---------------------------------------------
    "Emergency unlock": "Desbloqueo de emergencia",
    (
        "Heads up: this is an emergency exit, not a shortcut. It unlocks "
        "for {n} minutes and it is logged with a date and the text you "
        "wrote. Read it back next time."
    ): (
        "Atent@: esto es una salida de emergencia, no un atajo. Desbloquea "
        "{n} minutos y queda registrado con fecha y texto. Releelo la "
        "próxima vez."
    ),
    "Requirements": "Requisitos",
    "Words": "Palabras",
    "Writing time": "Tiempo de escritura",
    "Keystrokes": "Pulsaciones",
    "1. Why do you need to unlock right now?": "1. ¿Por qué necesitás desbloquear ahora?",
    "At least {n} words.": "Mínimo {n} palabras.",
    "Summary": "Resumen",
    "One-line summary (it goes into the log)": "Resumen en una línea (queda en la bitácora)",
    "Keep studying": "Seguir estudiando",
    "Verify and unlock": "Verificar y desbloquear",
    "Verifying…": "Verificando…",
    "Not yet:\n": "Todavía no:\n",
    "Unknown error": "Error desconocido",
    "Could not reach the service: {err}": "No se pudo contactar al servicio: {err}",
    "{n} words left.": "Faltan {n} palabras.",
    "Keep writing until the time is up.": "Seguí escribiendo hasta completar el tiempo.",
    "Answer all three questions.": "Completá las tres preguntas.",
    "You can verify. The service will confirm.": "Podés verificar. El servicio va a confirmar.",
    # -- preguntas del diálogo ---------------------------------------------
    "Describe the actual situation. Is it genuinely urgent, or are you tired?": (
        "Describí la situación concreta. ¿Es urgente de verdad o es cansancio?"
    ),
    "If the real reason were getting stuck, what exactly would it be?": (
        "Si el motivo real fuera quedar varado, ¿cuál es exactamente?"
    ),
    "A concrete plan with a time. If you cannot write it, do not unlock.": (
        "Un plan concreto y con horario. Si no podés escribirlo, no desbloquees."
    ),
    "Why you want to unlock right now": "Por qué querés desbloquear ahora",
    "What you lose if you do not": "Qué perdés si no lo hacés",
    "What you are going to do afterwards": "Qué vas a hacer después",
    # -- errores que arma el servicio --------------------------------------
    # Los produce emergency.py, que corre dentro del servicio. El servicio
    # fija el idioma desde la config antes de validar, asi que el error le
    # llega al usuario en el idioma que eligio.
    "You are {n} words short (you wrote {w} of {m}).": (
        "Te faltan {n} palabras (escribiste {w} de {m})."
    ),
    "{n} min {s:02d} s of real writing still to go (you have {a} min {b:02d} s).": (
        "Faltan {n} min {s:02d} s de escritura real (llevás {a} min {b:02d} s)."
    ),
    "No keystrokes were recorded.": "No se registró ninguna pulsación.",
    "This looks pasted from the clipboard ({r:.1f} characters per keystroke). It has to be written.": (
        "El texto parece pegado desde el portapapeles ({r:.1f} caracteres por "
        "pulsación). Hay que escribirlo."
    ),
    "You went {n} min without writing. Waiting does not count if you are not writing.": (
        "Pasaste {n} min sin escribir nada. El tiempo de espera no cuenta si no "
        "estás escribiendo."
    ),
    "Incomplete answer: '{label}' ({n} words short).": (
        "Respuesta incompleta: '{label}' (faltan {n} palabras)."
    ),
    "Emergency: written commitment ({w} words, {m} min)": (
        "Emergencia: compromiso escrito ({w} palabras, {m} min)"
    ),
    # -- navegacion ---------------------------------------------------------
    "Status": "Estado",
    "Programs": "Programas",
    "Sites": "Sitios",
    "Settings": "Ajustes",
    "Log": "Bitácora",
    "Service: LocalSystem": "Servicio: LocalSystem",
    "Service: systemd user": "Servicio: systemd (usuario)",
    "Install it (no admin needed):": "Instalalo (sin admin):",
    "Stop the things you picked, until you work": (
        "Frená lo que elijas hasta trabajar"
    ),
    "The lock is off. Turn it on when you are ready to study.": (
        "El bloqueo está apagado. Prendelo cuando quieras estudiar."
    ),
    "Programs that will not start while the lock is active.": (
        "Elegí qué programas no arrancan mientras el bloqueo está activo."
    ),
    "Domains that will not load, and the ones that always pass.": (
        "Dominios que no cargan y excepciones que siempre pasan."
    ),
    "Your TickTick token, what it costs to unlock, the extension.": (
        "Token de TickTick, cuánto cuesta desbloquear y la extensión."
    ),
    "Every emergency unlock and every blocked process.": (
        "Cada desbloqueo de emergencia y cada intento de bloqueo."
    ),
    "Quit": "Salir",
    # -- ventana principal --------------------------------------------------
    "Turn on the lock": "Activar bloqueo",
    "turn on the lock": "activar bloqueo",
    "emergency unlock": "desbloqueo de emergencia",
    "Shortcuts": "Atajos",
    (
        "The lock is off by default. Turn it on when you want to study; "
        "you can get out of it with the Readings or with the emergency unlock."
    ): (
        "El bloqueo está apagado por defecto. Prendelo cuando quieras "
        "estudiar; te vas a poder liberar con las Lecturas o con el "
        "desbloqueo de emergencia."
    ),
    # -- Ajustes ------------------------------------------------------------
    "Token tp_…  (stored encrypted with DPAPI)": "Token tp_…  (se guarda cifrado con DPAPI)",
    "Token": "Token",
    "Test connection and save": "Probar conexión y guardar",
    "Clear token": "Borrar token",
    "E.g: Studies": "Ej: Estudios",
    "TickTick project": "Proyecto de TickTick",
    (
        "Any task in the project counts; the name is not looked at. Tick off "
        "2 tasks in TickTick and it unlocks."
    ): (
        "Se cuenta cualquier tarea del proyecto, sin mirar el nombre. "
        "Tachá 2 tareas en TickTick y se desbloquea."
    ),
    "Readings needed": "Lecturas necesarias",
    "Poll interval": "Frecuencia de consulta",
    "Language": "Idioma",
    "Interface language": "Idioma de la interfaz",
    "Changing this restarts the window. Your token and settings stay.": (
        "Cambiar esto reinicia la ventana. Tu token y tus ajustes se conservan."
    ),
    "Emergency": "Emergencia",
    "Minimum words": "Palabras mínimas",
    "Writing minutes": "Minutos de escritura",
    "Minutes it unlocks for": "Minutos que desbloquea",
    "Browser extension": "Extensión del navegador",
    (
        "Paste this address into the extension's options page.\n"
        "Chrome: chrome://extensions → Developer mode → Load unpacked "
        "→ the extension/chrome folder.\n"
        "Firefox: about:debugging#/runtime/this-firefox → Load Temporary "
        "Add-on → extension/firefox/manifest.json"
    ): (
        "Copiá esta dirección en la página de opciones de la extensión.\n"
        "Chrome: chrome://extensions → Modo de desarrollador → Cargar descomprimida "
        "→ carpeta extension/chrome.\n"
        "Firefox: about:debugging#/runtime/this-firefox → Cargar complemento temporal "
        "→ extension/firefox/manifest.json"
    ),
    "Address": "Dirección",
    "Copy address": "Copiar dirección",
    "Open extension folder": "Abrir carpeta de la extensión",
    "Save settings": "Guardar ajustes",
    # -- Bitácora -----------------------------------------------------------
    "Emergency unlocks": "Desbloqueos de emergencia",
    "Blocked process attempts": "Intentos de bloqueo de procesos",
    "Refresh log": "Actualizar bitácora",
    "{w} words · {m} min": "{w} palabras · {m} min",
    "No emergency unlocks recorded.": "Sin desbloqueos de emergencia registrados.",
    "No process was stopped.": "Ningún proceso detenido.",
    # -- render del estado --------------------------------------------------
    "{a} of {b} tasks": "{a} de {b} tareas",
    "{n} task left to unlock.": "Te falta {n} tarea para desbloquear.",
    "{n} tasks left to unlock.": "Te faltan {n} tareas para desbloquear.",
    "Unlocked": "Desbloqueado",
    "No lock is active. Use whatever you want.": (
        "No hay bloqueo activo. Podés usar lo que quieras."
    ),
    "Asking TickTick…": "Consultando TickTick…",
    "Pending by module: ": "Pendientes por módulo: ",
    "No Readings pending in TickTick.": "No hay Lecturas pendientes en TickTick.",
    "<b style='color:#e5484d'>Error asking TickTick</b><br>": (
        "<b style='color:#e5484d'>ERROR al consultar TickTick</b><br>"
    ),
    "The Reading count is not being updated.": (
        "El contador de Lecturas no se está actualizando."
    ),
    "Lock active": "Bloqueo activo",
    "Only usable while the lock is active.": (
        "Solo se puede usar con el bloqueo activo."
    ),
    "Extension connected to": "Extensión conectada a",
    "IFEO active on {n} executables": "IFEO activo en {n} ejecutables",
    "{a} scans, {b} stops": "{a} barridos, {b} detenciones",
    "Copied": "Copiado",
    "Address copied. Open the extension's options page and paste it.": (
        "Dirección copiada. Abrí la página de opciones de la extensión y pegala."
    ),
    "Not found": "No encontrado",
    "It does not exist:": "No existe:",
    "Extensions": "Extensiones",
    "Folder opened:": "Carpeta abierta:",
    # -- diálogos -----------------------------------------------------------
    "Already locked": "Ya está bloqueado",
    "The lock is already active.\n\n": "El bloqueo ya está activo.\n\n",
    "Finish the Readings in TickTick, or use the emergency unlock if you need to get out.": (
        "Completá las Lecturas en TickTick o usá el desbloqueo de emergencia "
        "si necesitás salir."
    ),
    "Not enforcing": "Sin enforcement",
    (
        "The TickFence service is not running, so turning the lock on only resets "
        "the Reading counter. To really block, install the service:"
    ): (
        "El servicio de TickFence no está corriendo, así que activar el bloqueo "
        "solo reinicia el contador de Lecturas. Para bloquear de verdad "
        "instalá el servicio:"
    ),
    (
        "There is no program in the blocked list, so this will not lock you out "
        "of anything.\n\n"
    ): (
        "No hay ningún programa en la lista de bloqueados, así que activarlo "
        "no va a encerrarte de nada.\n\n"
    ),
    "It will still count your Readings.\n\n": "Igual va a contar tus Lecturas.\n\n",
    "Turn it on anyway?": "¿Activarlo igual?",
    "{n} program(s) will be blocked until you finish the Readings:": (
        "Se van a bloquear {n} programa(s) hasta que completes las Lecturas:"
    ),
    "The only way out is the Readings or the emergency unlock.": (
        "La única salida son las Lecturas o el desbloqueo de emergencia."
    ),
    "Turn it on?": "¿Activarlo?",
    "Done": "Listo",
    "Could not turn the lock on": "No se pudo activar el bloqueo",
    "Could not read the settings": "No se pudo leer la configuración",
    "Could not add": "No se pudo agregar",
    "Protected process": "Proceso protegido",
    "This can break Windows": "Esto puede romper Windows",
    "The process is critical.": "El proceso es crítico.",
    "Could not remove": "No se pudo quitar",
    # -- token --------------------------------------------------------------
    "Missing token": "Falta el token",
    "Paste your TickTick token.": "Pegá el token de TickTick.",
    "Test connection": "Probar conexión",
    "Testing…": "Probando…",
    "The token was rejected.": "El token fue rechazado.",
    "Connected": "Conectado",
    "Token saved and encrypted.": "Token guardado y cifrado.",
    "Visible projects:": "Proyectos visibles:",
    (
        "Heads up: the service is not running, so the token was saved but "
        "nothing is being blocked yet.\n"
    ): (
        "Ojo: el servicio no está corriendo, así que el token quedó guardado "
        "pero no se está bloqueando nada todavía.\n"
    ),
    "Install it as administrator:": "Instalalo como administrador:",
    "No service running": "No hay servicio corriendo",
    (
        "The token could not be saved because the TickFence service is not "
        "running.\n\n"
    ): (
        "El token no se pudo guardar porque el servicio de TickFence no está "
        "corriendo.\n\n"
    ),
    "Technical detail:": "Detalle técnico:",
    "Token rejected": "Token rechazado",
    "Check the token.": "Revisá el token.",
    # -- línea de comandos --------------------------------------------------
    "'{a}' needs administrator rights.": "'{a}' necesita permisos de administrador.",
    "Close this and reopen it as administrator.": (
        "Cerrá esto y volvé a abrirlo como administrador."
    ),
    "install": "instalación",
    # OJO: "uninstall" NO va acá. Es el nombre del subcomando y el texto que
    # _need_admin imprime ('uninstall' necesita permisos de administrador).
    # Traducirlo haría que el consejo diga un comando que no existe.
    "data in": "datos en",
    "mode": "modo",
    "bundled executable": "ejecutable empaquetado",
    "source code": "código fuente",
    "installing the package for the service": "instalando el paquete para el servicio",
    "the service could not find the package": "el servicio no podría encontrar el paquete",
    "registering the service": "registrando el servicio",
    "starting the service": "arrancando servicio",
    "the service did not respond": "el servicio no respondió",
    "Check the event viewer or try:": "Revisá el visor de eventos o probá:",
    "service ready": "servicio listo",
    "saved and encrypted": "guardado y cifrado",
    "projects": "proyectos",
    "executables blocked at the Windows level": "ejecutables bloqueados a nivel Windows",
    "none: with the machine unlocked the IFEO is clean": (
        "ninguno: con la maquina desbloqueada el IFEO esta limpio"
    ),
    "creating shortcuts": "creando accesos directos",
    "shortcut": "acceso",
    "WARNING": "AVISO",
    "the shortcuts could not be created": "no se pudieron crear los accesos directos",
    "The app still opens with:": "La app se abre igual con:",
    "Removing IFEO blocks": "Quitando bloqueos IFEO",
    "cleared": "liberado",
    "Stopping and removing the service": "Deteniendo y eliminando el servicio",
    "Done. You can delete C:\\ProgramData\\TickFence if you want to.": (
        "Listo. Podés borrar C:\\ProgramData\\TickFence si querés."
    ),
    "Done. Data lives in {p}.": "Listo. Los datos viven en {p}.",
    "Service responding": "Servicio respondsiendo",
    "state": "estado",
    "HTTP port": "servidor HTTP puerto",
    "applied": "aplicado",
    "executables": "ejecutables",
    "guard": "guardia",
    "IFEO stub": "stub IFEO",
    "configured": "configurado",
    "NO TOKEN": "SIN TOKEN",
    "status failed": "status falló",
    "current state": "estado actual",
    "LOCKED": "BLOQUEADO",
    "UNLOCKED": "DESBLOQUEADO",
    "error": "error",
    # -- estado que arma el servicio ----------------------------------------
    "{a}/{b} Readings completed": "{a}/{b} Lecturas completadas",
    "none": "ninguno",
    "The project '{n}' was not found in your TickTick. ": (
        "No se encontró el proyecto '{n}' en tu TickTick. "
    ),
    "Available projects:": "Proyectos disponibles:",
    "Fix the name in TickFence → Settings.": "Corregí el nombre en TickFence → Ajustes.",
    "The project {p} no longer exists in TickTick. ": (
        "El proyecto {p} ya no existe en TickTick. "
    ),
    "Set a name in TickFence → Settings.": "Indicá un nombre en TickFence → Ajustes.",
    "You did not set a TickTick project.": "No configuraste ningún proyecto de TickTick.",
    "No TickTick token. Open TickFence → Settings and paste it.": (
        "Sin token de TickTick. Abrí TickFence → Ajustes y pegalo."
    ),
    "TickTick returned the project with no tasks. It was not taken as the baseline.": (
        "TickTick devolvió el proyecto sin tareas. No se tomó como base."
    ),
    "No service": "Sin servicio",
    "Readings": "Lecturas",
    "reason": "razón",
    "pending": "pendientes",
    "server": "servidor",
    # -- mensajes del servicio que no son f-strings -----------------------
    "Lock on. {n} program(s) blocked at the Windows level. Finish the Readings to release them.": (
        "Bloqueo activado. {n} programa(s) bloqueados a nivel Windows. "
        "Completá las Lecturas para liberarlos."
    ),
    "Lock on. {n} program(s) watched by the process guard. Finish the Readings to release them.": (
        "Bloqueo activado. {n} programa(s) vigilados por el guardián de procesos. "
        "Completá las Lecturas para liberarlos."
    ),
    "Unlocked for {n} min. Your commitment was recorded.": (
        "Desbloqueado por {n} min. Quedó registrado tu compromiso."
    ),
    "Invalid or empty value.": "Valor inválido o vacío.",
    "{v} is a critical system or Windows process. Blocking it can leave the machine unusable, or stop the app itself from opening again.": (
        "{v} es un proceso crítico del sistema o de Windows. Bloquearlo puede "
        "dejar la PC inutilizable o impedir que la propia app vuelva a abrirse."
    ),
    "TickTick: {c} tasks completed in {p}": (
        "TickTick: {c} tareas completadas en {p}"
    ),
    "TickFence in no-lock mode": "TickFence en modo sin bloqueo",
    (
        "The TickFence service is not running, so TickFence will show your "
        "Reading status and save your settings, but it will NOT block any "
        "program.\n\n"
    ): (
        "El servicio de TickFence no está corriendo, así que TickFence va a "
        "mostrarte el estado de tus Lecturas y a guardar la configuración, "
        "pero NO va a bloquear ningún programa.\n\n"
    ),
    "To make it really block, install it once as administrator:\n\n": (
        "Para que bloquee de verdad, instalalo una vez como administrador:\n\n"
    ),
    "To make it really block, install it once (no admin needed):\n\n": (
        "Para que bloquee de verdad, instalalo una vez (sin admin):\n\n"
    ),
    "Meanwhile you can paste the token in Settings and watch it work.": (
        "Mientras tanto podés pegar el token en Ajustes y verlo funcionar."
    ),
    # -- listas de programas y sitios -------------------------------------
    "Progress toward unlocking": "Progreso hacia el desbloqueo",
    "Blocked": "Bloqueados",
    "Allowed (never blocked)": "Permitidos (nunca se bloquean)",
    "Use IFEO — the program never even gets to start": (
        "Usar IFEO — el programa ni siquiera llega a arrancar"
    ),
    (
        "Without IFEO the block is softer: the process guard finishes it off "
        "if it slips through. With IFEO you have to have installed TickFence "
        "as administrator."
    ): (
        "Sin IFEO el bloqueo es mas suave: el vigilante de procesos lo remata "
        "si logra colarse. Con IFEO hace falta haber instalado TickFence como "
        "administrador."
    ),
    "Blocked domains": "Dominios bloqueados",
    "Allowed (exempt)": "Permitidos (exentos)",
    "Plain names work: typing 'youtube.com' is enough to cover www., m., music. and shorts.": (
        "Se aceptan nombres sueltos: escribir 'youtube.com' alcanza para "
        "www., m., music. y shorts."
    ),
    "Add": "Agregar",
    "Remove": "Quitar",
    "E.g: steam.exe": "Ej: steam.exe",
    "E.g: tiktok.com": "Ej: tiktok.com",
    "Refresh TickTick now": "Actualizar TickTick ahora",
}


def set_lang(lang: str) -> str:
    """Fija el idioma global. Devuelve el que quedo, no el que se pidio.

    Un idioma desconocido cae en ingles en vez de romper: una config editada a
    mano con `language: "fr"` no puede dejar la ventana en blanco.
    """
    global _IDIOMA
    _IDIOMA = lang if lang in IDIOMAS else "en"
    return _IDIOMA


def lang() -> str:
    return _IDIOMA


def tr(texto: str) -> str:
    """Traduce un literal en ingles. Si no hay traduccion, lo devuelve igual.

    Devolver el original sin quejarse es a proposito: asi un texto nuevo
    aparece en ingles hasta que le agregan la entrada, en vez de desaparecer.
    """
    if _IDIOMA == "es":
        return ES.get(texto, texto)
    return texto


def faltantes(usados: set[str]) -> list[str]:
    """Traducciones que se usan pero no estan en la tabla ES.

    Lo usa test_i18n. Una cadena nueva sin traducir funciona (sale en ingles),
    pero es un olvido: esta lista lo vuelve visible.
    """
    return sorted(usados - set(ES))


def sobrantes(usados: set[str]) -> list[str]:
    """Entradas de la tabla que ya no usa nadie.

    Sobras por el camino no rompen nada, pero hacen que la tabla crezca sin
    que se note.
    """
    return sorted(set(ES) - usados)
