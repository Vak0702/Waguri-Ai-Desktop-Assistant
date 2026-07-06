"""
main_window.py — Frameless floating HUD window that hosts the orb,
a collapsible transcript log, and quick controls (mute / settings / quit).
Also wires up a system tray icon so Waguri can live minimized.

Supports a "minimal mode" that hides all buttons/log and leaves only the
glowing orb floating on screen — toggleable by voice command or the tray
menu (which always stays available as a guaranteed way back to the full
controls, even in minimal mode).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QSystemTrayIcon, QMenu, QApplication, QGraphicsDropShadowEffect
)

from gui.orb_widget import OrbWidget, OrbState


def _make_tray_icon() -> QIcon:
    """Generate a simple glowing-dot tray icon programmatically (no asset files needed)."""
    size = 64
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(60, 220, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(8, 8, size - 16, size - 16)
    p.end()
    return QIcon(pix)


class MainWindow(QWidget):
    micToggled = pyqtSignal(bool)     # True = muted
    settingsRequested = pyqtSignal()
    quitRequested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._drag_pos: QPoint | None = None
        self._muted = False
        self._log_visible = False
        self._is_fullscreen = False
        self._pre_fullscreen_geometry = None  # restores position/size on exit
        self._controls_visible = True
        self._pre_minimal_size: QSize | None = None

        self._build_ui()
        self._build_tray()

    # ---------- UI construction ----------

    def _build_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(300, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        # --- top control bar, wrapped in its own widget so the whole
        #     group can be hidden/shown as one unit for minimal mode ---
        self.top_bar_widget = QWidget()
        bar = QHBoxLayout(self.top_bar_widget)
        bar.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("Waguri — idle")
        self.status_label.setStyleSheet("color: #cfe8ea; font-size: 11px;")
        bar.addWidget(self.status_label)
        bar.addStretch()

        self.mute_btn = QPushButton("🎤")
        self.log_btn = QPushButton("≡")
        self.fullscreen_btn = QPushButton("⛶")
        self.minimize_btn = QPushButton("—")
        self.settings_btn = QPushButton("⚙")
        self.quit_btn = QPushButton("✕")
        for b in (self.mute_btn, self.log_btn, self.fullscreen_btn,
                  self.minimize_btn, self.settings_btn, self.quit_btn):
            b.setFixedSize(26, 26)
            b.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,20); color: white; "
                "border: none; border-radius: 13px; font-size: 12px; }"
                "QPushButton:hover { background: rgba(255,255,255,50); }"
            )
            bar.addWidget(b)

        self.mute_btn.clicked.connect(self._toggle_mute)
        self.log_btn.clicked.connect(self._toggle_log)
        self.fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        self.minimize_btn.clicked.connect(self._minimize_to_tray)
        self.settings_btn.clicked.connect(self.settingsRequested.emit)
        self.quit_btn.clicked.connect(self.quitRequested.emit)

        root.addWidget(self.top_bar_widget)

        # --- orb, centered. Double-click toggles minimal mode, so there's
        #     always a mouse-only way to bring controls back even if voice
        #     control isn't available. ---
        orb_row = QHBoxLayout()
        orb_row.addStretch()
        self.orb = OrbWidget()
        orb_row.addWidget(self.orb)
        orb_row.addStretch()
        root.addLayout(orb_row)
        root.addStretch()

        # --- collapsible transcript log ---
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        self.log.setStyleSheet(
            "QTextEdit { background: rgba(15,20,25,180); color: #d8f0f2; "
            "border-radius: 10px; padding: 8px; font-size: 11px; border: none; }"
        )
        self.log.hide()
        root.addWidget(self.log)

        # subtle drop shadow on the whole window for a floating HUD feel
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(_make_tray_icon(), self)
        self.tray.setToolTip("Waguri")
        menu = QMenu()

        show_action = QAction("Show Waguri", self)
        show_action.triggered.connect(self._restore_from_tray)
        menu.addAction(show_action)

        # Guaranteed fallback: always available from the tray regardless of
        # minimal mode, so voice control isn't the only way back to full UI.
        controls_action = QAction("Show Controls", self)
        controls_action.triggered.connect(self.show_controls)
        menu.addAction(controls_action)

        mute_action = QAction("Mute / Unmute", self)
        mute_action.triggered.connect(self._toggle_mute)
        menu.addAction(mute_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quitRequested.emit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._restore_from_tray()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()

    # ---------- behavior ----------

    def _toggle_mute(self):
        self.set_muted_ui(not self._muted)
        self.micToggled.emit(self._muted)

    def set_muted_ui(self, muted: bool):
        """Updates the mute button/icon state without emitting micToggled —
        used when mute is triggered by voice (worker already knows its own
        state) so we don't create a signal feedback loop."""
        self._muted = muted
        self.mute_btn.setText("🔇" if muted else "🎤")

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        self.log.setVisible(self._log_visible)
        self.resize(self.width(), 420 if self._log_visible else 280)

    def enter_fullscreen(self):
        if self._is_fullscreen:
            return
        self._pre_fullscreen_geometry = self.geometry()
        self.showFullScreen()
        self.fullscreen_btn.setText("🗗")
        self._is_fullscreen = True

    def exit_fullscreen(self):
        if not self._is_fullscreen:
            return
        self.showNormal()
        if self._pre_fullscreen_geometry is not None:
            self.setGeometry(self._pre_fullscreen_geometry)
        self.fullscreen_btn.setText("⛶")
        self._is_fullscreen = False

    def _toggle_fullscreen(self):
        self.exit_fullscreen() if self._is_fullscreen else self.enter_fullscreen()

    def hide_controls(self):
        """Minimal mode: hide the button bar and log, leaving only the
        floating orb visible. Always recoverable via voice ('show controls'),
        double-clicking the orb, or the tray menu's 'Show Controls' action."""
        if not self._controls_visible:
            return
        self._pre_minimal_size = self.size()
        self.top_bar_widget.hide()
        self.log.hide()
        self.resize(self.width(), 160)
        self._controls_visible = False

    def show_controls(self):
        if self._controls_visible:
            return
        self.top_bar_widget.show()
        if self._log_visible:
            self.log.show()
        if self._pre_minimal_size is not None:
            self.resize(self._pre_minimal_size)
        self._controls_visible = True
        # make sure it's actually on screen if this was triggered from tray
        # while the window was hidden
        self.show()
        self.raise_()

    def _toggle_minimal_mode(self):
        self.show_controls() if not self._controls_visible else self.hide_controls()

    def _minimize_to_tray(self):
        # Frameless "Tool" windows don't reliably support real taskbar
        # minimizing on Windows, so this hides to the tray instead —
        # the same, already-working pattern used by the close button.
        self.hide()
        self.tray.showMessage("Waguri", "Minimized — click the tray icon to reopen.",
                               QSystemTrayIcon.MessageIcon.Information, 1500)

    def _restore_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def append_log(self, speaker: str, text: str):
        color = "#7fe7ff" if speaker == "Waguri" else "#ffffff"
        self.log.append(f'<span style="color:{color}"><b>{speaker}:</b></span> {text}')

    def set_status_text(self, text: str):
        self.status_label.setText(f"Waguri — {text}")

    def set_orb_state(self, state: OrbState):
        self.orb.set_state(state)
        self.set_status_text(state.name.lower())

    # ---------- window dragging (frameless windows need manual drag) ----------
    # Also used to detect a plain click (vs. drag) on the orb to toggle
    # minimal mode as a mouse-only fallback.

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_minimal_mode()
            event.accept()

    def closeEvent(self, event):
        # Minimize to tray instead of quitting outright
        event.ignore()
        self.hide()
        self.tray.showMessage("Waguri", "Still running in the background.",
                               QSystemTrayIcon.MessageIcon.Information, 2000)