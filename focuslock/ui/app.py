"""Interfaz gráfica: ventana principal + ícono en el área de notificación."""
from __future__ import annotations

import sys
import time
from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,        # el area de scroll de Ajustes va sin marco
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..i18n import tr
from ..ipc import IpcClient
from .emergency import EmergencyDialog

# Comando de instalación según SO. En Windows es install.ps1 con admin;
# en Linux es el propio CLI (systemd --user, sin sudo).
_ON_WIN = sys.platform.startswith("win")
_INSTALL_CMD = "install.ps1" if _ON_WIN else "python -m focuslock install"
_INSTALL_SHELL = (
    "powershell -ExecutionPolicy Bypass -File install.ps1"
    if _ON_WIN
    else "python -m focuslock install"
)

# Gris oscuro NEUTRO, sin tinte azul. Jerarquia de TickTick, contencion de
# Apple: un solo acento, y en tres lugares.
#
# Ratios medidos, no estimados a ojo:
#   texto   #eceef1 sobre fondo #1c1d20       14.50:1  (pide 4.5)
#   texto   #eceef1 sobre superficie #242629  13.05:1  (pide 4.5)
#   texto 2 #9ea3ab sobre fondo #1c1d20        6.65:1  (pide 4.5)
#   texto 2 #9ea3ab sobre sidebar #161719      7.07:1  (pide 4.5)
#   blanco  sobre acento  #2f6fe0              4.70:1  (pide 4.5)
#   blanco  sobre hover   #2560d8              6.29:1  (pide 4.5)
#   blanco  sobre peligro #b8503a              4.95:1  (pide 4.5)
#   borde   #6e737d sobre superficie #242629   3.19:1  (pide 3, borde de control)
#   borde   #6e737d sobre fondo #1c1d20        3.54:1  (pide 3, borde de control)
#
# DIVIDER no es un borde de control sino decorativo, por eso puede ser tenue.
# tests/test_ui.py::TestStyleContrast falla si alguno de estos numeros se mueve.
STYLE = """
QWidget { background:#1c1d20; color:#eceef1; font-size:13px; }

#sidebar      { background:#161719; border-right:1px solid #2b2d31; }
#sidebarInner { background:#161719; }
#sidebarTitle { font-size:20px; font-weight:600; }
#sidebarSub   { font-size:12px; color:#9ea3ab; }
#sidebarFoot  { font-size:12px; color:#9ea3ab; }
#pageTitle    { font-size:26px; font-weight:600; }

#nav { background:transparent; border:none; outline:none; }
#nav::item {
  color:#9ea3ab; padding:11px 12px; margin:2px 10px; border-radius:10px; }
#nav::item:hover    { background:#2c2e32; color:#eceef1; }
#nav::item:selected { background:#2f6fe0; color:#ffffff; }

QLabel#hint  { color:#9ea3ab; }
QLabel#count { color:#eceef1; font-size:14px; font-weight:600; }

/* El veredicto del servicio en el dialogo de emergencia. El rojo del boton
   de desbloquear, con contraste suficiente sobre la tarjeta oscura. */
QLabel#err   { color:#f2a6a0; }

/* Sin esto los QLabel heredan el fondo de QWidget y se pintan como parches
   negros sobre las tarjetas #242629. */
QLabel, QCheckBox { background:transparent; }

/* Etiquetas de los formularios (Token, Poll interval, Minimum words...).

   Sin regla propia caian en el QLabel generico de arriba: mismo color y mismo
   tamano que el texto de las tarjetas, y pegadas a dos pixeles del campo. Se
   leian como texto suelto, no como la etiqueta de algo.

   El color va apenas por debajo del texto normal (8.13:1 contra 13.05:1 sobre
   la tarjeta, los dos muy arriba de 4.5:1) para que el ojo vaya al campo y no
   a la etiqueta. El padding les da aire: sin el, "Token" parece pegado a la
   caja. */
QFormLayout QLabel {
  color:#b9bec7;
  padding-right:10px;
  background:transparent;
}

/* Contenedor de los botones que ocupan las dos columnas del formulario.

   El QWidget de arriba le pone fondo a TODO QWidget, y ese contenedor es un
   QWidget comun: quedaba como un rectangulo mas oscuro (#1c1d20) pegado
   sobre la tarjeta (#242629), que es el rectangulo raro que se veia al lado
   de "Test connection and save". Transparent lo saca. */
#formRow { background:transparent; }

#card { background:#242629; border-radius:14px; }
QLabel#cardTitle { font-size:15px; font-weight:600; color:#eceef1; }
#page { background:#1c1d20; }
#cuerpo { background:#1c1d20; }

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QListWidget {
  background:#242629; color:#eceef1;
  border:1px solid #6e737d; border-radius:8px; padding:7px;
  selection-background-color:#2f6fe0; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
  border:1px solid #2f6fe0; }

QPushButton {
  background:#2f6fe0; border:none; border-radius:10px;
  padding:11px 18px; color:#ffffff; font-size:14px; }
QPushButton:hover   { background:#2560d8; }
QPushButton:pressed { background:#1f52ba; }
QPushButton:disabled {
  background:#242629; color:#6c7078; border:1px solid #2b2d31; }
QPushButton#danger { background:#b8503a; }
QPushButton#danger:hover { background:#a84530; }
QPushButton#danger:disabled {
  background:#242629; color:#6c7078; border:1px solid #2b2d31; }
QPushButton#ghost {
  background:#242629; border:1px solid #6e737d; color:#eceef1; }
QPushButton#ghost:hover { background:#2c2e32; }
QPushButton#ghost:disabled {
  background:#1c1d20; color:#6c7078; border:1px solid #2b2d31; }

QProgressBar {
  border:none; border-radius:7px; text-align:center;
  background:#2c2e32; min-height:14px; max-height:14px; }
QProgressBar::chunk { background:#2f6fe0; border-radius:7px; }

QScrollBar:vertical { background:transparent; width:10px; margin:0; }
QScrollBar::handle:vertical {
  background:#3a3d42; border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#4a4e55; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
  background:transparent; }
"""


def make_icon(color: str = "#e5484d", unlocked: bool = False) -> QIcon:
    size = 64
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if unlocked:
        p.setBrush(QBrush(QColor("#30a46c")))
        p.setPen(QPen(QColor("#0d1a14"), 5))
        p.drawEllipse(6, 6, size - 12, size - 12)
        p.setPen(QPen(QColor("#ffffff"), 7))
        p.drawLine(20, 33, 29, 43)
        p.drawLine(29, 43, 45, 23)
    else:
        p.setBrush(QBrush(QColor(color)))
        p.setPen(QPen(QColor("#2a0f10"), 5))
        p.drawEllipse(6, 6, size - 12, size - 12)
        p.setPen(QPen(QColor("#ffffff"), 5))
        p.drawRoundedRect(24, 28, 16, 20, 3, 3)
        p.drawArc(16, 10, 32, 32, 0, 180 * 16)
    p.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client
        self._data: dict = {}
        self.setWindowTitle("TickFence")
        self.resize(880, 640)
        self.setWindowIcon(make_icon())

        # El idioma se fija ANTES de construir nada: los textos van hardcodeados
        # en los constructores, no se recalculan despues. Si se hiciera aca
        # abajo, habria que reconstruir la ventana entera para cambiar el
        # idioma. Por eso el cambio de idioma reinicia la ventana.
        self._set_language_from_client()

    def _set_language_from_client(self) -> None:
        """Lee el idioma de la config. Si no puede, se queda en ingles.

        El default de i18n ya es ingles, asi que un servicio caido no rompe la
        ventana: se abre en ingles y listo.
        """
        try:
            cfg = self.client.call("config_get").get("config", {})
        except Exception:  # noqa: BLE001
            return
        self._idioma = i18n.set_lang(
            (cfg.get("general") or {}).get("language", "en")
        )

        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- barra de estado a lo ancho, arriba de todo ------------------------
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        # El estado ya esta en la barra de progreso y en el titulo de la
        # pagina. Este aviso es solo para lo que no se ve en ningun otro
        # lado: que el servicio murio, o que TickTick no contesta. Cuando
        # no hay nada que avisar no ocupa nada.
        self.banner.setMinimumHeight(0)
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setContentsMargins(24, 10, 24, 10)
        self.banner.hide()
        shell_layout.addWidget(self.banner)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # --- menu lateral ----------------------------------------------------
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(244)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 26, 0, 18)
        side.setSpacing(0)

        brand = QVBoxLayout()
        brand.setContentsMargins(28, 0, 24, 0)
        brand.setSpacing(0)
        # El nombre va con su icono, en una sola fila. Solo el texto, con todo
        # el aire de la barra alrededor, se leia como un titulo suelto.
        linea = QHBoxLayout()
        linea.setContentsMargins(0, 0, 0, 0)
        linea.setSpacing(9)
        marca = QLabel()
        marca.setPixmap(make_icon(unlocked=True).pixmap(26, 26))
        linea.addWidget(marca)
        title = QLabel("TickFence")
        title.setObjectName("sidebarTitle")
        linea.addWidget(title)
        linea.addStretch(1)
        brand.addLayout(linea)
        brand.addSpacing(3)
        sub = QLabel(tr("Stop the things you picked, until you work"))
        sub.setObjectName("sidebarSub")
        sub.setWordWrap(True)
        brand.addWidget(sub)
        wrapper = QWidget()
        wrapper.setObjectName("sidebarInner")
        wrapper.setLayout(brand)
        wrapper.setContentsMargins(0, 0, 0, 0)
        side.addWidget(wrapper)

        side.addSpacing(28)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFocusPolicy(Qt.StrongFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for etiqueta in self.PAGINAS:
            self.nav.addItem(tr(self.ETIQUETAS[etiqueta]))
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._ir_a)
        side.addWidget(self.nav, 1)

        foot = QLabel(tr("Service: LocalSystem") if _ON_WIN else tr("Service: systemd user"))
        foot.setObjectName("sidebarFoot")
        foot.setContentsMargins(28, 0, 0, 0)
        side.addWidget(foot)

        body_layout.addWidget(sidebar)

        # --- contenido -------------------------------------------------------
        self.stack = QStackedWidget()
        for etiqueta in self.PAGINAS:
            self.stack.addWidget(self._pagina(etiqueta))
        body_layout.addWidget(self.stack, 1)

        shell_layout.addWidget(body, 1)
        outer.addWidget(shell)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(8000)

        # Atajos: la app se usa en un momento de tension, y buscar el boton
        # con el mouse en ese momento es un paso de mas.
        for secuencia, destino in (("Ctrl+L", self._toggle_lock),
                                   ("Ctrl+E", self._emergency)):
            atajo = QShortcut(QKeySequence(secuencia), self)
            atajo.activated.connect(destino)

        self.quit_action = QAction(tr("Quit"), self)
        self.quit_action.triggered.connect(self._quit)

    # ------------------------------------------------------------- navegacion
    # Las claves son IDs estables, NO las etiquetas visibles. Antes la etiqueta
    # hacia doble trabajo: era el nombre del menu y la clave de los diccionarios
    # de arriba. Traducirla rompia el indexado, y un typo en el menu rompia el
    # lookup en silencio. Ahora el ID no se traduce y la etiqueta si.
    PAGINAS = ("estado", "programas", "sitios", "ajustes", "bitacora")

    ETIQUETAS = {
        "estado": "Status",
        "programas": "Programs",
        "sitios": "Sites",
        "ajustes": "Settings",
        "bitacora": "Log",
    }

    SUBTITULOS = {
        "estado": "The lock is off. Turn it on when you are ready to study.",
        "programas": "Programs that will not start while the lock is active.",
        "sitios": "Domains that will not load, and the ones that always pass.",
        "ajustes": "Your TickTick token, what it costs to unlock, the extension.",
        "bitacora": "Every emergency unlock and every blocked process.",
    }

    def _change_language(self, _indice: int) -> None:
        """Cambia el idioma y reinicia la ventana.

        Se guarda primero, y recien despues se reinicia: si el guardado falla
        el servicio esta caido, la ventana queda en el idioma nuevo pero el
        proximo arranque vuelve al viejo, y no hay nada que explicar.

        La ventana se reconstruye en vez de re-etiquetar porque los textos van
        en los constructores. Recorrer el arbol cambiando textos es mas
        codigo del que vale, y es el tipo de cosa que se olvida actualizar.
        """
        codigo = self.lang_combo.currentData()
        if not codigo or codigo == getattr(self, "_idioma", "en"):
            return
        try:
            self.client.call("config_set", section="general", values={"language": codigo})
        except Exception:  # noqa: BLE001
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(
                self.lang_combo.findData(getattr(self, "_idioma", "en"))
            )
            self.lang_combo.blockSignals(False)
            return
        i18n.set_lang(codigo)
        self.rebuild_for_language()

    def rebuild_for_language(self) -> None:
        """Cierra la ventana y abre otra en el idioma actual.

        Se pierde el texto a medio escribir de la emergencia, si lo hubiera:
        el dialogo es modal, asi que desde Ajustes no puede estar abierto a la
        vez. La sesion de escritura vive en un modulo, no en la ventana, asi
        que sobrevive igual.
        """
        from PySide6.QtWidgets import QApplication

        QApplication.instance().processEvents()
        pos = self.pos()
        self.close()
        nueva = MainWindow(self.client)
        nueva.resize(self.size())
        nueva.move(pos)
        nueva.show()
        self._replacement = nueva  # evitar que se recolecte
        self.deleteLater()

    def _pagina(self, etiqueta: str) -> QWidget:
        """Envuelve cada pagina con su titulo y su margen.

        El titulo se agrega aca y no en cada constructor: son cinco paginas y
        el titulo es una regla del diseno, no algo de cada pantalla.
        """
        constructor = {
            "estado": self._tab_status,
            "programas": self._tab_programs,
            "sitios": self._tab_sites,
            "ajustes": self._tab_settings,
            "bitacora": self._tab_history,
        }[etiqueta]

        # Estado ya trae su propio titulo y su propio margen: se usa tal cual.
        if etiqueta == "estado":
            page = constructor()
            page.setObjectName("page")
            return page

        cont = QWidget()
        cont.setObjectName("page")
        v = QVBoxLayout(cont)
        v.setContentsMargins(36, 32, 36, 32)
        v.setSpacing(18)

        # Titulo y subtitulo van juntos en su propio bloque, con espaciado
        # corto. Con el espaciado general de la pagina quedaban a doble de
        # distancia y los dos parecian textos sueltos. Margenes negativos
        # parecian la solucion y recortaban el subtitulo: no lo son.
        cabecera = QVBoxLayout()
        cabecera.setContentsMargins(0, 0, 0, 0)
        cabecera.setSpacing(1)
        titulo = QLabel(tr(self.ETIQUETAS[etiqueta]))
        titulo.setObjectName("pageTitle")
        cabecera.addWidget(titulo)
        sub = QLabel(tr(self.SUBTITULOS[etiqueta]))
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        cabecera.addWidget(sub)
        v.addLayout(cabecera)

        # El contenido de cada pagina no lleva margenes propios.
        cuerpo = constructor()
        cuerpo.setObjectName("cuerpo")
        cuerpo.layout().setContentsMargins(0, 8, 0, 0)
        v.addWidget(cuerpo, 1)
        return cont

    def _ir_a(self, fila: int) -> None:
        if 0 <= fila < self.stack.count():
            self.stack.setCurrentIndex(fila)

    # ------------------------------------------------------------------ Estado
    def _tab_status(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(36, 32, 36, 32)
        v.setSpacing(18)

        # Titulo y refresco en la misma fila: "Actualizar" es una accion
        # secundaria y al lado del titulo deja de competir con las dos
        # acciones de verdad. Titulo y subtitulo van en un bloque propio para
        # que el subtitulo quede pegado al titulo.
        cabecera = QVBoxLayout()
        cabecera.setContentsMargins(0, 0, 0, 0)
        cabecera.setSpacing(1)
        fila_titulo = QHBoxLayout()
        fila_titulo.setContentsMargins(0, 0, 0, 0)
        titulo = QLabel(tr("Status"))
        titulo.setObjectName("pageTitle")
        self.btn_poll = QPushButton(tr("Refresh TickTick now"))
        self.btn_poll.setObjectName("ghost")
        self.btn_poll.setToolTip("Consultar TickTick ahora (no espera el intervalo)")
        self.btn_poll.clicked.connect(lambda: self.refresh(force=True))
        fila_titulo.addWidget(titulo)
        fila_titulo.addStretch(1)
        fila_titulo.addWidget(self.btn_poll)
        cabecera.addLayout(fila_titulo)

        self.estado_sub = QLabel()
        self.estado_sub.setObjectName("hint")
        self.estado_sub.setWordWrap(True)
        cabecera.addWidget(self.estado_sub)
        v.addLayout(cabecera)

        prog_box = QWidget()
        prog_box.setObjectName("card")
        pv = QVBoxLayout(prog_box)
        pv.setContentsMargins(26, 20, 26, 22)
        pv.setSpacing(10)

        # Titulo del grupo y contador en la misma fila: el numero va arriba a
        # la derecha, no encima de la barra, donde compite con el color.
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        etiqueta = QLabel(tr("Progress toward unlocking"))
        etiqueta.setObjectName("cardTitle")
        self.count = QLabel()
        self.count.setObjectName("count")
        head.addWidget(etiqueta)
        head.addStretch(1)
        head.addWidget(self.count)
        pv.addLayout(head)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumHeight(14)
        self.progress.setMaximumHeight(14)
        self.progress.setTextVisible(False)
        self.progress.setFormat("")  # el contador vive en self.count
        pv.addWidget(self.progress)

        self.modules = QLabel()
        self.modules.setWordWrap(True)
        self.modules.setObjectName("hint")
        pv.addWidget(self.modules)
        v.addWidget(prog_box)

        # Un solo boton primario. "Actualizar" vive arriba con el titulo, asi
        # que aca solo quedan las dos acciones de verdad.
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_toggle = QPushButton(tr("Turn on the lock"))
        self.btn_toggle.clicked.connect(self._toggle_lock)
        self.btn_emergency = QPushButton(tr("Emergency unlock"))
        self.btn_emergency.setObjectName("danger")
        self.btn_emergency.setToolTip("Ctrl+E")
        self.btn_emergency.clicked.connect(self._emergency)
        row.addWidget(self.btn_toggle)
        row.addWidget(self.btn_emergency)
        row.addStretch(1)
        v.addLayout(row)

        self.nota = QLabel(
            tr(
                "The lock is off by default. Turn it on when you want to study; "
                "you can get out of it with the Readings or with the emergency "
                "unlock."
            )
        )
        self.nota.setWordWrap(True)
        self.nota.setObjectName("hint")
        v.addWidget(self.nota)

        atajos = QWidget()
        atajos.setObjectName("card")
        av = QVBoxLayout(atajos)
        av.setContentsMargins(26, 18, 26, 20)
        av.setSpacing(4)
        at = QLabel(tr("Shortcuts"))
        at.setObjectName("cardTitle")
        av.addWidget(at)
        lista = QLabel(
            f"Ctrl+L  {tr('turn on the lock')}"
            f"        Ctrl+E  {tr('emergency unlock')}"
        )
        lista.setObjectName("hint")
        av.addWidget(lista)
        v.addWidget(atajos)

        v.addStretch(1)
        return page

    # --------------------------------------------------------------- Programas
    def _tab_programs(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        split = QSplitter()
        self.prog_blocked = self._rule_list(tr("Blocked"), "programs", "blocked")
        self.prog_allowed = self._rule_list(
            tr("Allowed (never blocked)"), "programs", "allowed"
        )
        split.addWidget(self.prog_blocked["holder"])
        split.addWidget(self.prog_allowed["holder"])
        v.addWidget(split, 1)

        # La explicacion de IFEO va aca y no arriba: es una nota del control,
        # no un subtitulo de la pagina (que ya dice que elegiste que bloquear).
        self.ifeo_check = QCheckBox(
            tr("Use IFEO — the program never even gets to start")
        )
        v.addWidget(self.ifeo_check)
        self.ifeo_note = QLabel(
            tr(
                "Without IFEO the block is softer: the process guard finishes it "
                "off if it slips through. With IFEO you have to have installed "
                "TickFence as administrator."
            )
        )
        self.ifeo_note.setWordWrap(True)
        self.ifeo_note.setObjectName("hint")
        v.addWidget(self.ifeo_note)
        return page

    # ------------------------------------------------------------------ Sitios
    def _tab_sites(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        split = QSplitter()
        self.site_blocked = self._rule_list(tr("Blocked domains"), "sites", "blocked")
        self.site_allowed = self._rule_list(tr("Allowed (exempt)"), "sites", "allowed")
        split.addWidget(self.site_blocked["holder"])
        split.addWidget(self.site_allowed["holder"])
        v.addWidget(split, 1)

        # Nota util, no subtitulo: el ejemplo de como escribir el dominio.
        info = QLabel(
            tr(
                "Plain names work: typing 'youtube.com' is enough to cover "
                "www., m., music. and shorts."
            )
        )
        info.setObjectName("hint")
        info.setWordWrap(True)
        self.site_info = info
        v.addWidget(info)
        return page

    def _rule_list(self, title: str, section: str, field: str) -> dict:
        # Tarjeta: el titulo va DENTRO del marco. Afuera quedaba suelto, como
        # un texto flotando sobre una caja que no le pertenece.
        holder = QWidget()
        holder.setObjectName("card")
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(22, 18, 22, 20)
        lay.setSpacing(10)
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        lay.addWidget(lbl)

        listing = QListWidget()
        lay.addWidget(listing, 1)

        entry = QLineEdit()
        entry.setPlaceholderText(
            tr("E.g: steam.exe") if section == "programs" else tr("E.g: tiktok.com")
        )
        entry.returnPressed.connect(
            lambda: self._rule_add(section, field, listing, entry, False)
        )
        lay.addWidget(entry)

        row = QHBoxLayout()
        row.setSpacing(8)
        add = QPushButton(tr("Add"))
        add.clicked.connect(lambda: self._rule_add(section, field, listing, entry, False))
        add.setObjectName("ghost")
        remove = QPushButton(tr("Remove"))
        remove.setObjectName("ghost")
        remove.clicked.connect(lambda: self._rule_del(section, field, listing))
        row.addWidget(add)
        row.addWidget(remove)
        lay.addLayout(row)

        return {
            "holder": holder,
            "list": listing,
            "entry": entry,
            "section": section,
            "field": field,
        }

    # ----------------------------------------------------------------- Ajustes
    #: Separacion entre el fin del texto de la etiqueta y el borde del campo.
    #: Con las etiquetas a la derecha TODAS terminan en el mismo x, asi que esta
    #: distancia es la misma en cada fila: no hace falta rellenar la columna.
    GAP_ETIQUETA = 14
    #: Ancho de los campos editables. Sin tope, QFormLayout los estira a lo que
    #: sobra de la tarjeta y un spinbox de "45 s" queda de 1400 px de ancho.
    ANCHO_CAMPO = 340
    #: La direccion del servidor es larga y solo se copia; angostarla obliga a
    #: hacer scroll horizontal para leerla.
    ANCHO_CAMPO_LARGO = 560

    @staticmethod
    def _form_alineado(form, espacio: int) -> QFormLayout:
        """Deja el form con margenes y ritmo vertical consistentes.

        El ancho de la columna NO se decide aca: eso lo mide _alinear_ajustes
        con las etiquetas ya en pantalla. Fijarlo aca fue el error anterior,
        porque en este punto la hoja de estilos todavia no resolvio la fuente
        y la medicion salia con la tipografia equivocada.
        """
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(espacio)
        form.setHorizontalSpacing(MainWindow.GAP_ETIQUETA)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        return form

    @staticmethod
    def _etiquetas_de_columna(form) -> list:
        """Solo las etiquetas que van en la columna, junto a un campo.

        Las de SpanningRole quedan fuera a proposito: ocupan la fila entera y
        son los textos de ayuda, que llevan saltos de linea. Medidos como si
        fueran una sola linea dan miles de pixeles de ancho, y la columna se
        comia la tarjeta entera dejando los campos sin espacio.
        """
        etiquetas = []
        for fila in range(form.rowCount()):
            item = form.itemAt(fila, QFormLayout.LabelRole)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QLabel):
                etiquetas.append(widget)
        return etiquetas

    def _alinear_ajustes(self, forms) -> None:
        """Una sola columna de etiquetas y un tope de ancho para los campos.

        Se mide con las etiquetas YA EXISTENTES y con SU tipografia ya
        resuelta, y se toma el maximo de las cuatro tarjetas juntas. Medir
        tarjeta por tarjeta devuelve cuatro columnas distintas; medir antes de
        que la hoja de estilos aplique la fuente devuelve un numero falso.
        """
        todos = []
        for form in forms:
            todos.extend(self._etiquetas_de_columna(form))
        if not todos:
            return

        # ensurePolished() fuerza a Qt a aplicar la hoja de estilos al widget
        # antes de medir. Sin esto, fontMetrics() devuelve la fuente por
        # defecto, que es mas chica que los 13px que impone el QSS.
        ancho_texto = 0
        for widget in todos:
            widget.ensurePolished()
            ancho_texto = max(
                ancho_texto, widget.fontMetrics().horizontalAdvance(widget.text())
            )
        if ancho_texto <= 0:
            return
        # Sin relleno extra. La etiqueta va alineada a la derecha, asi que
        # todas terminan en el mismo x y la separacion la da el
        # horizontalSpacing del form, no el ancho de la columna.
        ancho_columna = ancho_texto

        for form in forms:
            for widget in self._etiquetas_de_columna(form):
                widget.setFixedWidth(ancho_columna)
                widget.setWordWrap(False)
                # Que se estire a toda la altura de la celda. Con la politica
                # Preferred el QLabel mide lo que mide el texto (19 px) dentro
                # de una celda de 32 px, y el texto queda 6 px por encima del
                # centro del campo. estirandolo, el alignment de abajo lo
                # centra de verdad.
                widget.setSizePolicy(
                    QSizePolicy.Preferred, QSizePolicy.MinimumExpanding
                )
                # A la derecha: asi todas las etiquetas terminan en el mismo
                # x y la separacion con el campo es igual en cada fila. A la
                # izquierda quedaba un borde prolijo pero la distancia
                # variaba de 36 a 257 px, que es lo que mas se notaba.
                widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for fila in range(form.rowCount()):
                item = form.itemAt(fila, QFormLayout.FieldRole)
                campo = item.widget() if item is not None else None
                # En una fila spanning, itemAt(..., FieldRole) devuelve la
                # etiqueta de ayuda, no un campo editable. Sin esta guarda se
                # le fijaba el ancho de un campo y el texto se cortaba.
                if campo is None or isinstance(campo, QLabel):
                    continue
                # Ancho FIJO, no un tope. Con un tope cada campo toma su
                # sizeHint y quedan de 95, 134 y 241 px: el borde derecho
                # sale irregular, que es el problema que se vino a arreglar.
                largo = getattr(campo, "isReadOnly", None)
                if largo is not None and largo():
                    campo.setFixedWidth(self.ANCHO_CAMPO_LARGO)
                else:
                    campo.setFixedWidth(self.ANCHO_CAMPO)

    def _card(self, titulo_texto: str) -> tuple:
        """Tarjeta con su titulo DENTRO. Devuelve (tarjeta, layout del cuerpo).

        El QGroupBox anterior dibujaba el titulo sobre el borde, que se leia
        como una etiqueta suelta arriba de otra caja. Ademas cada pagina
        usaba un contenedor distinto; ahora todas usan el mismo.
        """
        card = QWidget()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(22, 18, 22, 20)
        outer.setSpacing(14)
        t = QLabel(titulo_texto)
        t.setObjectName("cardTitle")
        outer.addWidget(t)
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        outer.addLayout(body)
        return card, body

    def _tab_settings(self) -> QWidget:
        # TODO el cuerpo va dentro de un area de scroll. Sin esto, la pagina
        # necesita 1154 px de alto: en una ventana de 1080 (que es lo que
        # tiene cualquier pantalla de 1080p con la barra de tareas) el
        # contenido no entra y Qt comprime la fila mas debil hasta turning los
        # campos en una raya de dos pixeles. Se vio al sumar la tarjeta de
        # idioma, que cruzo el limite. Con scroll no depende del tamano.
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll)

        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(16)

        ESPACIO_VERTICAL = 14

        tt, tt_body = self._card("TickTick")
        tf = QFormLayout()
        self._form_alineado(tf, ESPACIO_VERTICAL)
        tt_body.addLayout(tf)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText(
            tr("Token tp_…  (stored encrypted with DPAPI)")
        )
        tf.addRow(tr("Token"), self.token)
        row = QHBoxLayout()
        self.btn_token = QPushButton(tr("Test connection and save"))
        self.btn_token.setObjectName("ghost")
        self.btn_token.clicked.connect(self._test_token)
        clear = QPushButton(tr("Clear token"))
        clear.setObjectName("ghost")
        clear.clicked.connect(self._clear_token)
        row.addWidget(self.btn_token)
        row.addWidget(clear)
        row.addStretch(1)
        row.setContentsMargins(0, 0, 0, 0)
        # `addRow(layout)` a secas mete la fila en la sola columna de los
        # campos y los botones quedan estrujados contra el borde. Con un
        # widget contenedor que ocupa las dos columnas, cada boton conserva
        # su ancho. (SpanningRole no sirve: PySide6 expone insertRow, no setRow.)
        # El objectName es lo que le saca el fondo: el QWidget universal del
        # stylesheet le pone #1c1d20 y quedaba como un parche oscuro pegado
        # sobre la tarjeta.
        fila = QWidget()
        fila.setObjectName("formRow")
        fila.setLayout(row)
        fila.setContentsMargins(0, 0, 0, 0)
        tf.addRow(fila)

        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText(tr("E.g: Studies"))
        tf.addRow(tr("TickTick project"), self.project_name)

        hint = QLabel(
            tr(
                "Any task in the project counts; the name is not looked at. "
                "Tick off 2 tasks in TickTick and it unlocks."
            )
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        tf.addRow(hint)

        self.required = QSpinBox()
        self.required.setRange(1, 50)
        tf.addRow(tr("Readings needed"), self.required)
        self.poll_secs = QSpinBox()
        self.poll_secs.setRange(15, 600)
        self.poll_secs.setSingleStep(15)
        self.poll_secs.setSuffix(" s")
        tf.addRow(tr("Poll interval"), self.poll_secs)

        # El idioma NO se guarda con "Guardar ajustes". Cambiarlo reinicia la
        # ventana entera, porque los textos van hardcodeados en los
        # constructores: no alcanza con volver a pintar. Va aparte y con su
        # propio boton, y el aviso lo dice.
        lang_box, lang_body = self._card(tr("Language"))
        lf = QFormLayout()
        self._form_alineado(lf, ESPACIO_VERTICAL)
        lang_body.addLayout(lf)
        self.lang_combo = QComboBox()
        for code in i18n.IDIOMAS:
            self.lang_combo.addItem(i18n.NOMBRES[code], code)
        idx = self.lang_combo.findData(getattr(self, "_idioma", "en"))
        self.lang_combo.setCurrentIndex(max(0, idx))
        self.lang_combo.currentIndexChanged.connect(self._change_language)
        lf.addRow(tr("Interface language"), self.lang_combo)
        lang_hint = QLabel(
            tr("Changing this restarts the window. Your token and settings stay.")
        )
        lang_hint.setWordWrap(True)
        lang_hint.setObjectName("hint")
        lf.addRow(lang_hint)
        v.addWidget(lang_box)
        v.addWidget(tt)

        em_box, em_body = self._card(tr("Emergency"))
        ef = QFormLayout()
        self._form_alineado(ef, ESPACIO_VERTICAL)
        em_body.addLayout(ef)
        self.em_words = QSpinBox()
        self.em_words.setRange(50, 5000)
        self.em_words.setSingleStep(50)
        ef.addRow(tr("Minimum words"), self.em_words)
        self.em_minutes = QSpinBox()
        self.em_minutes.setRange(1, 120)
        ef.addRow(tr("Writing minutes"), self.em_minutes)
        self.em_unlock = QSpinBox()
        self.em_unlock.setRange(1, 480)
        ef.addRow(tr("Minutes it unlocks for"), self.em_unlock)
        v.addWidget(em_box)

        ext, ext_body = self._card(tr("Browser extension"))
        xf = QFormLayout()
        self._form_alineado(xf, ESPACIO_VERTICAL)
        ext_body.addLayout(xf)
        ext_hint = QLabel(
            tr(
                "Paste this address into the extension's options page.\n"
                "Chrome: chrome://extensions → Developer mode → Load unpacked "
                "→ the extension/chrome folder.\n"
                "Firefox: about:debugging#/runtime/this-firefox → Load Temporary "
                "Add-on → extension/firefox/manifest.json"
            )
        )
        ext_hint.setWordWrap(True)
        ext_hint.setObjectName("hint")
        xf.addRow(ext_hint)
        self.ext_url = QLineEdit()
        self.ext_url.setReadOnly(True)
        xf.addRow(tr("Address"), self.ext_url)
        row = QHBoxLayout()
        copy = QPushButton(tr("Copy address"))
        copy.setObjectName("ghost")
        copy.clicked.connect(self._copy_endpoint)
        open_dir = QPushButton(tr("Open extension folder"))
        open_dir.setObjectName("ghost")
        open_dir.clicked.connect(self._open_ext_dir)
        row.addWidget(copy)
        row.addWidget(open_dir)
        row.addStretch(1)
        xf.addRow(row)
        v.addWidget(ext)

        save = QPushButton(tr("Save settings"))
        save.clicked.connect(self._save_settings)
        # A la derecha y de ancho natural: estirado a todo el ancho el boton
        # primario de la pagina parece un banner, no una accion.
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(save)
        v.addLayout(fila)
        v.addStretch(1)

        # Al final, con los textos ya puestos: las etiquetas se arman con tr() y
        # hasta que existen no se les puede medir nada.
        self._forms_ajustes = (tf, lf, ef, xf)
        self._alinear_ajustes(self._forms_ajustes)
        return page

    # --------------------------------------------------------------- Bitácora
    def _tab_history(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        def bloque(titulo_texto, attr) -> None:
            card = QWidget()
            card.setObjectName("card")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(22, 18, 22, 20)
            cv.setSpacing(10)
            t = QLabel(titulo_texto)
            t.setObjectName("cardTitle")
            cv.addWidget(t)
            area = QPlainTextEdit()
            area.setReadOnly(True)
            cv.addWidget(area, 1)
            setattr(self, attr, area)
            v.addWidget(card, 1)

        bloque(tr("Emergency unlocks"), "hist_em")
        bloque(tr("Blocked process attempts"), "hist_blocks")

        refresh = QPushButton(tr("Refresh log"))
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self._load_history)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(refresh)
        v.addLayout(fila)
        return page

    # =================================================================== Datos
    def refresh(self, force: bool = False) -> None:
        try:
            data = self.client.call("poll" if force else "status")
        except Exception as exc:  # noqa: BLE001
            self._data = {}
            self._apply_banner(locked=True, offline=str(exc))
            return
        self._data = data
        self._render(data)
        self._update_endpoint(data)

    def _render(self, data: dict) -> None:
        locked = bool(data.get("locked"))
        self._apply_banner(locked)

        required = max(1, int(data.get("required", 2)))
        credits = int(data.get("credits", 0))
        if locked:
            self.progress.setValue(int(min(1.0, credits / required) * 100))
            self.count.setText(
                tr("{a} of {b} tasks").format(a=credits, b=required)
            )
            faltan = max(0, required - credits)
            self.estado_sub.setText(
                tr("{n} task left to unlock.").format(n=faltan)
                if faltan == 1
                else tr("{n} tasks left to unlock.").format(n=faltan)
            )
        else:
            self.progress.setValue(100)
            self.count.setText(tr("Unlocked"))
            self.estado_sub.setText(
                tr("No lock is active. Use whatever you want.")
            )

        checked = float(data.get("checked_at") or 0)
        fresh = checked > 0

        mods = data.get("modules") or {}
        if not fresh:
            # Todavía no se consultó TickTick. Decir "no hay Lecturas
            # pendientes" sería inventar: lo correcto es decir que no sabe.
            self.modules.setText(tr("Asking TickTick…"))
        elif mods:
            self.modules.setText(
                tr("Pending by module: ")
                + " · ".join(f"{name} ({n})" for name, n in mods.items())
            )
        else:
            self.modules.setText(tr("No Readings pending in TickTick."))

        if data.get("error"):
            self.modules.setText(f"TickTick: {data['error']}")
            # Un fallo de polling silencioso es como worse el bug de creditos:
            # el contador se queda en 0 y no se explica por que.
            self.banner.setStyleSheet(self._ERROR_STYLE)
            self._aviso(
                tr("<b style='color:#e5484d'>Error asking TickTick</b><br>")
                + f"{data['error']}<br>"
                + tr("The Reading count is not being updated.")
            )

        # El boton solo activa; no hay forma de desactivar desde la UI.
        if hasattr(self, "btn_toggle"):
            if locked:
                self.btn_toggle.setText(tr("Lock active"))
                self.btn_toggle.setEnabled(False)
            else:
                self.btn_toggle.setText(tr("Turn on the lock"))
                self.btn_toggle.setEnabled(True)

        # La emergencia solo tiene sentido con un bloqueo activo: sin bloqueo
        # no hay nada que desbloquear.
        if hasattr(self, "btn_emergency"):
            self.btn_emergency.setEnabled(locked)
            self.btn_emergency.setToolTip(
                "" if locked else tr("Only usable while the lock is active.")
            )

        self.site_info.setText(
            tr("Extension connected to")
            + f" http://127.0.0.1:{data.get('port', 0)}/state · "
            + tr("IFEO active on {n} executables").format(
                n=len(data.get("ifeo", [])
            ))
            + " · "
            + tr("{a} scans, {b} stops").format(
                a=data.get("guard", {}).get("scans", 0),
                b=data.get("guard", {}).get("kills", 0),
            )
        )

    def _update_endpoint(self, data: dict) -> None:
        if not hasattr(self, "ext_url"):
            return
        port, token = data.get("port", 0), data.get("token", "")
        if port and token:
            self.ext_url.setText(f"http://127.0.0.1:{port}/state?token={token}")

    def _copy_endpoint(self) -> None:
        QApplication.clipboard().setText(self.ext_url.text())
        QMessageBox.information(
            self, tr("Copied"),
            tr("Address copied. Open the extension's options page and paste it."),
        )

    def _open_ext_dir(self) -> None:
        import os
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "extension"
        if not root.exists():
            QMessageBox.warning(self, tr("Not found"), tr("It does not exist:") + f" {root}")
            return
        os.startfile(str(root))  # noqa: S606
        QMessageBox.information(
            self, tr("Extensions"), tr("Folder opened:") + f"\n{root}"
        )

    _ERROR_STYLE = ("background:#2a0f10;border:1px solid #e5484d;"
                    "border-radius:0px;padding:8px 24px;")

    def _aviso(self, texto: str) -> None:
        """Muestra el banner solo si hay algo que avisar."""
        if texto:
            self.banner.setText(texto)
            self.banner.show()
        else:
            self.banner.clear()
            self.banner.hide()

    def _apply_banner(self, locked: bool, offline: str = "") -> None:
        # El estado normal NO va en el banner. Bloqueado o no se lee en el
        # titulo de la pagina, en la barra de progreso y en el boton. Este
        # espacio queda para lo que no se ve en ningun otro lado: que el
        # servicio no responde o que TickTick fallo. Repetir "DESBLOQUEADO"
        # arriba de una pagina que ya lo dice era ruido.
        if offline:
            # Sin servicio no se sabe el estado real: se avisa, no se afirma.
            self.banner.setStyleSheet(self._ERROR_STYLE)
            self._aviso(
                "<b style='color:#e5484d'>SIN SERVICIO</b> — no se puede "
                f"consultar el estado.<br>{offline}<br>"
                + (
                    "Instalalo con administrador: <code>install.ps1</code>"
                    if _ON_WIN
                    else "Instalalo sin sudo: <code>python -m focuslock install</code>"
                )
            )
            return
        self._aviso("")

    # ================================================================= Acciones
    def _toggle_lock(self) -> None:
        """Activa el bloqueo.

        No hay botón para desactivarlo a propósito: si activaste el bloqueo es
        porque querés concentrarte y hacer las Lecturas. La única salida es
        completarlas o el desbloqueo de emergencia. Si un día no querés
        trabajar, no lo actives.
        """
        if self._data.get("locked", False):
            QMessageBox.information(
                self,
                tr("Already locked"),
                tr("The lock is already active.\n\n")
                + tr(
                    "Finish the Readings in TickTick, or use the emergency "
                    "unlock if you need to get out."
                ),
            )
            return

        enforcement = self._data.get("enforcement", True)
        if not enforcement:
            QMessageBox.information(
                self,
                tr("Not enforcing"),
                tr(
                    "The TickFence service is not running, so turning the lock on "
                    "only resets the Reading counter. To really block, install "
                    "the service:"
                )
                + f"\n    {_INSTALL_SHELL}",
            )

        blocked = self._data.get("ifeo") or []
        if not blocked:
            answer = QMessageBox.question(
                self,
                tr("Turn on the lock"),
                tr(
                    "There is no program in the blocked list, so this will not "
                    "lock you out of anything.\n\n"
                )
                + tr("It will still count your Readings.\n\n")
                + tr("Turn it on anyway?"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        else:
            answer = QMessageBox.question(
                self,
                tr("Turn on the lock"),
                tr("{n} program(s) will be blocked until you finish the "
                   "Readings:").format(n=len(blocked))
                + "\n\n"
                + "\n".join(f"  · {name}" for name in blocked)
                + "\n\n"
                + tr("The only way out is the Readings or the emergency unlock.")
                + "\n\n"
                + tr("Turn it on?"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            result = self.client.call("lock")
            self.refresh(force=True)
            message = result.get("message")
            if message:
                QMessageBox.information(self, tr("Done"), message)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("Could not turn the lock on"), str(exc))

    def _emergency(self) -> None:
        try:
            cfg = self.client.call("config_get")["config"]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("Could not read the settings"), str(exc))
            return
        dlg = EmergencyDialog(cfg, self.client, self)
        dlg.exec()
        result = dlg.granted
        if not result:
            return
        if result.get("granted"):
            QMessageBox.information(
                self, "Desbloqueado", result.get("message", "Desbloqueado por emergencia.")
            )
        else:
            # Cumple los requisitos pero no hay enforcement: se registra igual.
            QMessageBox.information(
                self,
                "Compromiso registrado",
                "\n\n".join(result.get("errors", [])),
            )
        self.refresh(force=True)

    def _rule_add(
        self,
        section: str,
        field: str,
        listing: QListWidget,
        entry: QLineEdit,
        force: bool,
    ) -> None:
        value = entry.text().strip()
        if not value:
            return
        try:
            res = self.client.call(f"{section}_{field}_add", value=value, force=force)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("Could not add"), str(exc))
            return

        if res.get("immutable"):
            QMessageBox.information(
                self, tr("Protected process"), res.get("message", "")
            )
            return

        if res.get("needs_confirm"):
            answer = QMessageBox.warning(
                self,
                tr("This can break Windows"),
                res.get("message", tr("The process is critical.")),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self._rule_add(section, field, listing, entry, True)
                return
            return

        entry.clear()
        self._fill_rules()

    def _rule_del(self, section: str, field: str, listing: QListWidget) -> None:
        item = listing.currentItem()
        if not item:
            return
        try:
            self.client.call(f"{section}_{field}_del", value=item.text())
            self._fill_rules()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("Could not remove"), str(exc))

    def _fill_rules(self) -> None:
        try:
            cfg = self.client.call("config_get")["config"]
        except Exception:
            return
        for holder, path in (
            (self.prog_blocked, ("programs", "blocked")),
            (self.prog_allowed, ("programs", "allowed")),
            (self.site_blocked, ("sites", "blocked")),
            (self.site_allowed, ("sites", "allowed")),
        ):
            holder["list"].clear()
            holder["list"].addItems(cfg.get(path[0], {}).get(path[1], []) or [])
        self.ifeo_check.setChecked(bool(cfg.get("programs", {}).get("use_ifeo", True)))
        tt = cfg.get("ticktick", {})
        self.project_name.setText(tt.get("project_name", ""))
        self.required.setValue(int(tt.get("required", 2)))
        self.poll_secs.setValue(int(tt.get("poll_seconds", 45)))
        e = cfg.get("emergency", {})
        self.em_words.setValue(int(e.get("min_words", 300)))
        self.em_minutes.setValue(int(e.get("min_minutes", 5)))
        self.em_unlock.setValue(int(e.get("unlock_minutes", 20)))
        # Se reaplica por si la pagina se reconstruyo con otro idioma: sin
        # esto, cambiar de idioma y volver a esta pagina dejaria las columnas
        # con el ancho del idioma anterior.
        self._alinear_ajustes(getattr(self, "_forms_ajustes", ()))

    def _test_token(self) -> None:
        """Guarda el token y consulta TickTick.

        Distingue tres casos que antes se confundian en un unico error:
        el token esta mal, la red fallo, o no hay servicio.
        """
        token = self.token.text().strip()
        if not token:
            QMessageBox.warning(
                self, tr("Missing token"), tr("Paste your TickTick token.")
            )
            return

        self.btn_token.setEnabled(False)
        self.btn_token.setText(tr("Testing…"))
        try:
            res = self.client.call("ticktick_set_token", token=token)
        except Exception as exc:  # noqa: BLE001
            self.btn_token.setEnabled(True)
            self.btn_token.setText(tr("Test connection"))
            self._show_token_error(str(exc))
            return

        self.btn_token.setEnabled(True)
        self.btn_token.setText(tr("Test connection"))

        # A veces el backend devuelve (ok, error) en vez de lanzar.
        if not res.get("ok", False):
            detail = res.get("error", tr("The token was rejected."))
            self._show_token_error(detail, rejected=True)
            return

        self.token.clear()
        self._save_ticktick_settings()
        names = "\n".join(str(n) for n in (res.get("names") or []) if n)
        extra = ""
        if res.get("enforcement") is False:
            extra = (
                "\n\n"
                + tr(
                    "Heads up: the service is not running, so the token was "
                    "saved but nothing is being blocked yet.\n"
                )
                + (tr("Install it as administrator:") if _ON_WIN else tr("Install it (no admin needed):")) + f" {_INSTALL_CMD}"
            )
        QMessageBox.information(
            self,
            tr("Connected"),
            tr("Token saved and encrypted.")
            + "\n"
            + tr("Visible projects:") + f" {res.get('projects')}\n{names}{extra}",
        )
        self.refresh(force=True)

    def _show_token_error(self, detail: str, rejected: bool = False) -> None:
        """El error que mas confunde es 'no hay servicio': no es el token."""
        lowered = (detail or "").lower()
        # OJO: estas palabras tienen que estar en los DOS idiomas. El mensaje
        # lo arma el servicio, que ya contesta en el idioma del usuario, asi
        # que buscando solo en español el chequeo dejaba de funcionar apenas
        # alguien elegía inglés: el error se leia como "token malo" y el
        # consejo de instalar el servicio no aparecia nunca.
        looks_like_missing_service = any(
            word in lowered
            for word in (
                "servicio", "service",
                "pipe", "socket", "systemctl",
                "contactar", "contact",
                "conectar", "connect",
            )
        )
        if not rejected and looks_like_missing_service:
            QMessageBox.warning(
                self,
                tr("No service running"),
                tr(
                    "The token could not be saved because the TickFence service "
                    "is not running.\n\n"
                )
                + (tr("Install it as administrator:") if _ON_WIN else tr("Install it (no admin needed):"))
                + f"\n    {_INSTALL_SHELL}\n\n"
                + tr("Technical detail:") + f" {detail}",
            )
            return
        QMessageBox.warning(
            self, tr("Token rejected"), detail or tr("Check the token.")
        )

    def _save_ticktick_settings(self) -> None:
        """Guarda proyecto/prefijo/cantidad sin depender del servicio."""
        try:
            self.client.call("config_set", section="ticktick", values={
                "project_name": self.project_name.text().strip(),
                "project_id": "",
                "required": self.required.value(),
                "poll_seconds": self.poll_secs.value(),
            })
        except Exception:  # noqa: BLE001
            pass

    def _clear_token(self) -> None:
        try:
            self.client.call("ticktick_set_token", token="")
            self.token.clear()
            self.refresh(force=True)
        except Exception as exc:  # noqa: BLE001
            self._show_token_error(str(exc))

    def _save_settings(self) -> None:
        try:
            self._save_ticktick_settings()
            self.client.call("config_set", section="emergency", values={
                "min_words": self.em_words.value(),
                "min_minutes": self.em_minutes.value(),
                "unlock_minutes": self.em_unlock.value(),
            })
            self.client.call("config_set", section="programs", values={
                "use_ifeo": self.ifeo_check.isChecked(),
            })
            QMessageBox.information(self, "Guardado", "Ajustes guardados.")
            self.refresh(force=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo guardar", str(exc))

    def _load_history(self) -> None:
        try:
            data = self.client.call("history")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo", str(exc))
            return
        em = data.get("emergencies", [])
        if em:
            lines = []
            for e in reversed(em):
                when = datetime.fromtimestamp(e.get("at", 0)).strftime("%Y-%m-%d %H:%M")
                lines.append(
                    f"── {when} · "
                    + tr("{w} words · {m} min").format(
                        w=e.get("words", 0), m=int(e.get("seconds", 0) // 60)
                    )
                    + f"\n{e.get('commitment', '')}\n"
                )
            self.hist_em.setPlainText("\n".join(lines))
        else:
            self.hist_em.setPlainText(tr("No emergency unlocks recorded."))

        blocks = data.get("blocks", [])
        if blocks:
            rows = [
                f"{datetime.fromtimestamp(b.get('at', 0)).strftime('%m-%d %H:%M:%S')}  "
                f"{b.get('process', '?'):<24} pid={b.get('pid', '?'):<7} {b.get('method', '')}"
                for b in reversed(blocks)
            ]
            self.hist_blocks.setPlainText("\n".join(rows))
        else:
            self.hist_blocks.setPlainText(tr("No process was stopped."))

    # ------------------------------------------------------------------ cierre
    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def _quit(self) -> None:
        QApplication.quit()


class TrayApp:
    """Arranca la GUI y elige backend: servicio de Windows o modo local.

    El servicio es preferible (es el que bloquea de verdad), pero si no esta
    instalado la app tiene que seguir siendo utilizable: se ve el estado, se
    guarda el token, se editan las listas. Lo que no se puede es bloquear, y
    la UI lo dice.
    """

    def __init__(self, force_local: bool = False) -> None:
        # Reutiliza la instancia existente: Qt solo admite un QApplication por
        # proceso y crear un segundo lanza RuntimeError.
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setStyleSheet(STYLE)

        self.client = IpcClient()
        self.local = None
        self.using_service = False

        if not force_local:
            try:
                self.client.call("status", retries=0)
                self.using_service = True
            except Exception:
                self.using_service = False

        if not self.using_service:
            from ..local import LocalBackend

            self.local = LocalBackend()
            self.client = self.local

        self.window = MainWindow(self.client)
        self.tray = QSystemTrayIcon(make_icon(), self.qt)
        menu = QMenu()
        menu.addAction("Abrir TickFence", self.window.show)
        menu.addAction("Actualizar ahora", lambda: self.window.refresh(force=True))
        menu.addSeparator()
        menu.addAction(self.window.quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray)
        self.tray.show()

    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()

    def run(self) -> int:
        self._sync_dev_shortcut()
        self.window.show()
        self.window._fill_rules()
        self.window._load_history()
        self.window.refresh()
        if not self.using_service:
            self._show_standalone_notice()
        return self.qt.exec()

    @staticmethod
    def _sync_dev_shortcut() -> None:
        """Mantiene el acceso de desarrollo al dia al abrir la app.

        Solo cuando se esta corriendo desde el codigo fuente. En una
        instalacion normal no hay proyecto que apuntar y el acceso sobra, asi
        que se borra: un ícono que no abre nada es peor que no tenerlo.
        """
        try:
            from ..shortcuts import (
                _project_dir,
                create_dev_shortcut,
                remove_dev_shortcuts,
            )

            if _project_dir() is None:
                remove_dev_shortcuts()
            else:
                create_dev_shortcut()
        except Exception:  # noqa: BLE001
            pass  # un ícono de mas no puede impedir abrir la app

    def _show_standalone_notice(self) -> None:
        """Sin servicio la app funciona, pero no bloquea. Hay que decirlo."""
        QMessageBox.information(
            self.window,
            tr("TickFence in no-lock mode"),
            tr(
                "The TickFence service is not running, so TickFence will show "
                "your Reading status and save your settings, but it will NOT "
                "block any program.\n\n"
            )
            + (tr("To make it really block, install it once as administrator:\n\n") if _ON_WIN else tr("To make it really block, install it once (no admin needed):\n\n"))
            + f"    {_INSTALL_SHELL}\n\n"
            + tr("Meanwhile you can paste the token in Settings and watch it work."),
        )


def main(force_local: bool = False) -> int:
    return TrayApp(force_local=force_local).run()


if __name__ == "__main__":
    sys.exit(main())
