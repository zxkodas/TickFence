r"""Deja el paquete importable para el servicio de Windows.

El problema: `pythonservice.exe` arranca con el directorio de trabajo en
`C:\Windows\System32` y sin PYTHONPATH. Si focuslock vive en Documentos, el
servicio no lo encuentra, arranca y muere al instante.

La salida es instalar el paquete en site-packages, donde cualquier interprete
lo encuentra sin depender del directorio de trabajo ni de variables de entorno.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def install() -> int:
    if getattr(sys, "frozen", False):
        print("  ya esta empaquetado como ejecutable, no hace falta instalar")
        return 0

    print(f"  proyecto: {PROJECT}")
    print(f"  python  : {sys.executable}")

    if not (PROJECT / "pyproject.toml").exists():
        # Ya corre desde site-packages (p. ej. reinstalación desde el venv):
        # no hay nada que copiar, solo verificar que se importa.
        print("  ya corre desde site-packages, no hace falta reinstalar")
    else:
        # 1) Instalacion real en site-packages: es lo que encuentra el servicio.
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", str(PROJECT)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  FALLO pip install:\n{result.stdout}\n{result.stderr}")
            return 1
        print("  TickFence instalado en site-packages")

    # 2) Verificar que un interprete limpio lo encuentre desde otro directorio.
    probe_dir = r"C:\Windows\System32" if sys.platform.startswith("win") else "/"
    check = subprocess.run(
        [sys.executable, "-c", "import focuslock.service as s; print(s.__file__)"],
        capture_output=True,
        text=True,
        cwd=probe_dir,
    )
    if check.returncode != 0:
        print(f"  FALLO la verificacion: {check.stderr.strip()}")
        return 1
    print(f"  verificado desde {probe_dir}: {check.stdout.strip()}")

    # 3) Limpiar una copia vieja si el proyecto se movio, para no confundir.
    site = Path(check.stdout.strip()).parent
    print(f"  ubicacion efectiva: {site}")
    return 0


if __name__ == "__main__":
    sys.exit(install())
