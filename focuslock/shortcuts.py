"""Acceso a TickFence desde el menú y el Escritorio.

Windows: .lnk en Menú Inicio + Escritorio. Linux: .desktop en
~/.local/share/applications (+ Escritorio si existe).

Solo accesos directos. NO hay autoinicio: abrir la app es una decisión
del usuario.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    START_MENU = Path(os.environ.get("APPDATA", "")) / (
        "Microsoft/Windows/Start Menu/Programs"
    )
    DESKTOP = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
else:
    _XDG_DATA = Path(
        os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    )
    START_MENU = _XDG_DATA / "applications"
    _XDG_DESKTOP = Path(os.environ.get("XDG_DESKTOP_DIR") or str(Path.home() / "Desktop"))
    DESKTOP = _XDG_DESKTOP


def _project_dir() -> Path | None:
    """Carpeta del proyecto si se esta corriendo desde el codigo fuente.

    El acceso directo arranca con la carpeta del usuario como directorio de
    trabajo, y ahi `focuslock` resuelve desde site-packages, no desde el
    proyecto. Consecuencia: un cambio en el codigo no se ve en el acceso
    directo hasta reinstalar el paquete, y el sintoma es "arregle algo y no
    paso nada". Con el directorio de trabajo puesto en el proyecto, el acceso
    directo ve el codigo que se acaba de editar.
    """
    raiz = Path(__file__).resolve().parents[1]
    return raiz if (raiz / "pyproject.toml").exists() else None


def _icon_path() -> Path:
    """Donde vive el .ico de la app.

    Se busca en AppData y en la carpeta del proyecto, para que funcione tanto
    instalado como corriendo desde el codigo.
    """
    import os

    candidatos = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "TickFence" / "tickfence.ico",
        Path(__file__).resolve().parents[1] / "dist" / "tickfence.ico",
    ]
    for c in candidatos:
        if c.exists():
            return c
    return candidatos[0]


def _launcher() -> tuple[str, str]:
    """(ejecutable, argumentos) para abrir la GUI.

    Si estamos empaquetados, el .exe. Si no, el interprete con -m.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    return sys.executable, "-m focuslock gui"


def _project_dir() -> Path | None:
    """Carpeta del proyecto si estamos corriendo desde el codigo fuente.

    El servicio y la GUI comparten el mismo codigo instalado en
    site-packages, pero mientras se desarrolla conviene que el acceso directo
    apunte al proyecto: si no, cada cambio exige reinstalar el paquete a mano.
    """
    raiz = Path(__file__).resolve().parents[1]
    if (raiz / "pyproject.toml").exists():
        return raiz
    return None


# Nombres de acceso de versiones anteriores. Tras un rebrandeo quedan los
# viejos en el Escritorio y en el Menú Inicio, y Windows los sigue
# mostrando: se ven dos íconos y la búsqueda devuelve el nombre viejo.
NOMBRES_ANTIGUOS = ("FocusLock.lnk", "FocusLock.desktop")

# Acceso de DESARROLLO. Convive con el de la release a proposito.
DEV_NOMBRE = "TickFence (dev)"

_EXT = ".lnk" if sys.platform.startswith("win") else ".desktop"


def _dev_link_paths() -> list[Path]:
    return [carpeta / f"{DEV_NOMBRE}{_EXT}" for carpeta in (START_MENU, DESKTOP)]


def _link_paths() -> list[Path]:
    name = f"TickFence{_EXT}"
    paths = [START_MENU / name]
    # En Linux el Escritorio puede no existir (o ser otra ruta): solo si está.
    if DESKTOP.exists() or sys.platform.startswith("win"):
        paths.append(DESKTOP / name)
    return paths


def _stale_link_paths() -> list[Path]:
    """Accesos de nombres anteriores, que hay que borrar al desinstalar."""
    actuales = {p.name.lower() for p in _link_paths()}
    return [
        carpeta / nombre
        for carpeta in (START_MENU, DESKTOP)
        for nombre in NOMBRES_ANTIGUOS
        if nombre.lower() not in actuales
    ]


def _write_desktop(path: Path, workdir: str | None, description: str) -> None:
    """Escribe un .desktop que abre la GUI. Sin deps nuevas: texto plano."""
    target, args = _launcher()
    cmd = f"{target} {args}".strip()
    icono = _icon_path()
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=TickFence" if "dev" not in description.lower() else "TickFence (dev)",
        f"Comment={description}",
        f"Exec={cmd}",
        "Terminal=false",
        "Categories=Utility;",
    ]
    if workdir:
        lines.append(f"Path={workdir}")
    if icono.exists():
        lines.append(f"Icon={icono}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o755)
    except OSError:
        pass


def create_dev_shortcut() -> list[Path]:
    """Crea el acceso que abre la app desde la carpeta del proyecto.

    Devuelve lista vacia si no hay codigo fuente: en una instalacion normal
    este acceso no significa nada, y un ícono que no abre nada es peor que
    ningun ícono.
    """
    proyecto = _project_dir()
    if proyecto is None:
        return []

    if not sys.platform.startswith("win"):
        created: list[Path] = []
        for link_path in _dev_link_paths():
            try:
                _write_desktop(link_path, str(proyecto), "TickFence - desarrollo")
                created.append(link_path)
            except Exception:
                continue
        return created

    import pythoncom
    from win32com.shell import shell

    created = []
    target, args = _launcher()
    for link_path in _dev_link_paths():
        link_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink,
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                shell.IID_IShellLink,
            )
            link.SetPath(target)
            link.SetArguments(args)
            link.SetDescription("TickFence - desarrollo")
            # ACA ESTA TODO EL MECANISMO: el directorio de trabajo es el
            # proyecto, y eso hace que `python -m focuslock` importe el
            # paquete de aca y no el de site-packages.
            link.SetWorkingDirectory(str(proyecto))
            icono = _icon_path()
            if icono.exists():
                link.SetIconLocation(str(icono), 0)
            link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(link_path), 0)
            created.append(link_path)
        except Exception:
            continue
    return created


def remove_dev_shortcuts() -> list[str]:
    """Saca el acceso de desarrollo.

    Corre en cada arranque de la GUI desde el codigo fuente. Si moviste o
    borraste la carpeta del proyecto, el ícono tiene que irse solo, o queda
    apuntando a algo que no abre.
    """
    removed: list[str] = []
    for link_path in _dev_link_paths():
        if link_path.exists():
            try:
                link_path.unlink()
                removed.append(str(link_path))
            except OSError:
                pass
    return removed


def create_shortcuts() -> list[Path]:
    """Crea el acceso directo del menú Inicio y del Escritorio."""
    if not sys.platform.startswith("win"):
        created: list[Path] = []
        proyecto = _project_dir()
        for link_path in _link_paths():
            try:
                _write_desktop(
                    link_path,
                    str(proyecto) if proyecto is not None else None,
                    "TickFence - bloqueador de foco",
                )
                created.append(link_path)
            except Exception:
                continue
        return created
    import pythoncom
    from win32com.shell import shell

    created = []
    target, args = _launcher()

    for link_path in _link_paths():
        link_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink,
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                shell.IID_IShellLink,
            )
            link.SetPath(target)
            link.SetArguments(args)
            link.SetDescription("TickFence - bloqueador de foco")
            # El directorio de trabajo decide de que carpeta importa el paquete.
            # Con la carpeta del usuario, `python -m focuslock` carga la copia
            # de site-packages, que es la del ultimo install: los cambios del
            # proyecto no se verian hasta reinstalar.
            proyecto = _project_dir()
            link.SetWorkingDirectory(
                str(proyecto) if proyecto is not None else str(Path.home())
            )
            # Sin icono propio, Windows muestra el de python.exe: en el Menu
            # Inicio y en la busqueda se ve algo que no es la app.
            icono = _icon_path()
            if icono.exists():
                link.SetIconLocation(str(icono), 0)
            link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(link_path), 0)
            created.append(link_path)
        except Exception:
            continue
    return created


def remove_shortcuts() -> list[str]:
    removed: list[str] = []
    for link_path in _link_paths() + _stale_link_paths():
        if link_path.exists():
            try:
                link_path.unlink()
                removed.append(str(link_path))
            except OSError:
                pass
    return removed


def status() -> dict:
    return {
        "launcher": " ".join(_launcher()),
        "links": {str(p): p.exists() for p in _link_paths()},
        "autostart": False,
    }


def install() -> dict:
    created = create_shortcuts()
    return {"shortcuts": [str(p) for p in created], "autostart": False}


def uninstall() -> dict:
    return {"removed": remove_shortcuts(), "autostart": False}


if __name__ == "__main__":
    import json

    print(json.dumps(install(), indent=2))
