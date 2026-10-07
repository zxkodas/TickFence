"""Normalización y reglas de coincidencia para programas, sitios y tareas."""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Iterable, Sequence

# --------------------------------------------------------------------------
# Normalización
# --------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002190-\U000021FF"
    "\U0001F1E6-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)
_WS_RE = re.compile(r"\s+")
_TRIM_RE = re.compile(r"^[^\w]+|[^\w]+$", flags=re.UNICODE)


def strip_decoration(text: str) -> str:
    """Quita emojis y Trim() tipo TickTick ("📖Estudios" -> "Estudios")."""
    return _TRIM_RE.sub("", _EMOJI_RE.sub("", text or "").strip())


def norm_key(text: str) -> str:
    """Clave de comparación: sin acentos, sin mayúsculas, espacios colapsados."""
    decomposed = unicodedata.normalize("NFKD", strip_decoration(text))
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _WS_RE.sub(" ", without_accents.strip().lower())


# --------------------------------------------------------------------------
# Tareas
# --------------------------------------------------------------------------


def title_matches_prefix(title: str, prefix: str) -> bool:
    """True si el título empieza con el prefijo configurado.

    "Lectura 3" + "Lectura"  -> True
    "Lecturas"     + "Lectura" -> True   (prefijo, no igualdad exacta)
    "TP 1"         + "Lectura" -> False
    "Parcial 2"    + "Lectura" -> False
    "Modulo 4"     + "Lectura" -> False
    """
    prefix_key = norm_key(prefix)
    if not prefix_key:
        return False
    return norm_key(title).startswith(prefix_key)


# --------------------------------------------------------------------------
# Programas
# --------------------------------------------------------------------------

# Procesos que nunca deben matarse: matarlos deja Windows inservible.
# Bloquear uno de estos requiere habilitarlo explícitamente en "dangerous".
# Procesos que TickFence jamas mata, sin excepcion y aunque el usuario los
# ponga en la lista de bloqueados. Matar cualquiera de estos deja Windows
# inservible o corta la sesion de escritorio.
#
# explorer.exe entra aqui a proposito: es el shell de Windows. Si muere, se
# caen el escritorio, la barra de tareas y todas las ventanas, y Windows lo
# reinicia en loop. NO va en la lista de permitidos, porque esa lista la puede
# editar el usuario; esto no.
NEVER_BLOCK = {
    # --- shell y sesion de escritorio ---
    "explorer.exe",
    "userinit.exe",
    "logonui.exe",
    "sihost.exe",
    "ctfmon.exe",
    "shellsync.exe",
    "startmenuexperiencehost.exe",
    "lockapp.exe",
    "searchhost.exe",
    "searchapp.exe",
    "textinputhost.exe",
    "peopleexperiencehost.exe",
    "werfault.exe",
    "wermgr.exe",

    # --- nucleo del sistema ---
    "system",
    "system idle process",
    "registry",
    "memory compression",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "lsm.exe",
    "spoolsv.exe",
    "dwm.exe",
    "conhost.exe",
    "fontdrvhost.exe",
    "wudfhost.exe",
    "runtimebroker.exe",
    "taskhostw.exe",
    "audiodg.exe",
    "dllhost.exe",
    "wmiprvse.exe",
    "tiworker.exe",
    "trustedinstaller.exe",

    # --- seguridad y antivirus ---
    "msmpeng.exe",
    "nissrv.exe",
    "mbamservice.exe",

    # --- TickFence mismo ---
    "TickFence.exe",
    "focuslock.exe",
    "focuslock_svc.exe",
    "opencode.exe",
    # --- intérpretes (el servicio/GUI son Python en ambas plataformas) ---
    "python.exe",
    "pythonw.exe",
    "pythonservice.exe",
    "python",
    "python3",
    "python3.11",
    "python3.12",
    "python3.13",
    # --- núcleo Linux: matarlos cuelga la sesión (equivalente a explorer.exe) ---
    "systemd",
    "dbus-daemon",
    "dbus-broker",
    "gnome-shell",
    "gnome-session",
    "gdm",
    "sddm",
    "lightdm",
    "Xorg",
    "Xwayland",
    "kwin_wayland",
    "kwin_x11",
    "mutter",
    "sway",
    "hyprland",
    "plasmashell",
    "xfwm4",
    "openbox",
    "i3",
    "picom",
    "pipewire",
    "wireplumber",
    "pulseaudio",
    "networkmanager",
    "sshd",
}

DEFAULT_DANGEROUS = {
    "taskmgr.exe", "regedit.exe", "cmd.exe", "powershell.exe",
    "mmc.exe", "control.exe", "msconfig.exe", "taskkill.exe", "shutdown.exe",
    "rundll32.exe", "mshta.exe", "wscript.exe", "cscript.exe",
    # Linux: herramientas para deshacer el bloqueo o apagar la máquina.
    "shutdown", "reboot", "poweroff", "halt",
    "systemctl", "kill", "killall", "pkill", "sudo", "su",
}


def norm_program(entry: str) -> str:
    """Normaliza una regla de programa a nombre de ejecutable en minúsculas."""
    entry = (entry or "").strip().strip('"')
    if not entry:
        return ""
    entry = entry.replace("\\", "/")
    base = os.path.basename(entry)
    if not base:
        return ""
    base = base.lower()
    if not base.endswith(".exe"):
        base += ".exe"
    return base


def _stem(name: str) -> str:
    """Nombre sin el .exe final, para comparar Windows <-> Linux.

    En Linux psutil reporta "firefox" y la regla puede venir como
    "firefox.exe" (o al revés). Sin esto nunca matchean y el bloqueo no
    funciona en Linux; con esto "firefox" == "firefox.exe" en ambas.
    """
    name = (name or "").lower()
    return name[:-4] if name.endswith(".exe") else name


def in_never_block(name: str) -> bool:
    """True si el proceso está protegido, con o sin .exe."""
    candidate = _stem(norm_program(name))
    return any(_stem(n) == candidate for n in NEVER_BLOCK)


def match_program(name: str, blocked: Sequence[str], allowed: Sequence[str]) -> bool:
    """Decide si un proceso debe bloquearse.

    La lista de permitidos gana siempre. Y por encima de ambas hay una capa
    que el usuario no puede desactivar: NEVER_BLOCK. Si el nombre esta ahi,
    la respuesta es False aunque este explicitamente en la lista de bloqueados.
    Protege en la regla, no solo en quien la aplica.
    """
    # Acepta nombre suelto o ruta completa: se compara siempre por basename.
    # Stems: "firefox" == "firefox.exe" para que las mismas reglas anden en ambos.
    candidate = _stem(norm_program(name))
    if not candidate:
        return False
    if any(_stem(n) == candidate for n in NEVER_BLOCK):
        return False
    allowed_set = {_stem(norm_program(a)) for a in allowed}
    if candidate in allowed_set:
        return False
    blocked_set = {_stem(norm_program(b)) for b in blocked}
    return candidate in blocked_set


# --------------------------------------------------------------------------
# Sitios
# --------------------------------------------------------------------------


def norm_site(entry: str) -> str:
    """Normaliza una regla de sitio a 'host[/prefijo]' en minúsculas.

    "https://www.YouTube.com/feed/" -> "youtube.com"
    "upt.edu.ar/inscripciones"      -> "upt.edu.ar/inscripciones"
    """
    entry = (entry or "").strip().lower()
    if not entry:
        return ""
    entry = re.sub(r"^[a-z][a-z0-9+.-]*://", "", entry)
    entry = entry.split("#", 1)[0].split("?", 1)[0]
    if not entry:
        return ""
    host, _, path = entry.partition("/")
    host = host.split("@")[-1].split(":")[0]
    host = re.sub(r"^www\.", "", host)
    if not host or "." not in host:
        return ""
    path = path.strip("/")
    return f"{host}/{path}" if path else host


def _host_matches(host: str, rule_host: str) -> bool:
    return host == rule_host or host.endswith("." + rule_host)


def match_host(host: str, blocked: Iterable[str], allowed: Iterable[str]) -> bool:
    """True si el host debe bloquearse. Allowed gana siempre.

    Soporta reglas con prefijo de path: "upt.edu.ar/x" solo bloquea ese path.
    """
    host = (host or "").lower()
    host = re.sub(r"^www\.", "", host.split(":")[0])
    if not host:
        return False
    for rule in allowed:
        norm = norm_site(rule)
        if not norm:
            continue
        r_host, _, r_path = norm.partition("/")
        if _host_matches(host, r_host) and (not r_path or r_path == "*"):
            return False
    for rule in blocked:
        norm = norm_site(rule)
        if not norm:
            continue
        r_host, _, r_path = norm.partition("/")
        if _host_matches(host, r_host):
            if r_path in ("", "*"):
                return True
            # Regla con path: se valida más abajo con la URL completa.
            return True
    return False


def match_url(url: str, blocked: Iterable[str], allowed: Iterable[str]) -> bool:
    """Versión con path-aware para reglas del tipo 'host/ruta'."""
    url = (url or "").strip().lower()
    url = re.sub(r"^[a-z][a-z0-9+.-]*://", "", url)
    host, _, rest = url.partition("/")
    host = re.sub(r"^www\.", "", host.split(":")[0])
    host = host.split("@")[-1]
    path = rest

    for rule in allowed:
        norm = norm_site(rule)
        if not norm:
            continue
        r_host, _, r_path = norm.partition("/")
        if _host_matches(host, r_host) and (not r_path or r_path in (path, "*")):
            return False

    for rule in blocked:
        norm = norm_site(rule)
        if not norm:
            continue
        r_host, _, r_path = norm.partition("/")
        if not _host_matches(host, r_host):
            continue
        if not r_path or r_path == "*":
            return True
        if r_path in path:
            return True
    return False
