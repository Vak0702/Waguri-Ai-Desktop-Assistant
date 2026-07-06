"""
orb_widget.py — The glowing orb: Waguri's visual heartbeat.

Renders a soft, glowing circular orb with distinct animated states:
    idle       -> slow breathing pulse, muted teal
    listening  -> brighter cyan, faster pulse + outward ripple
    thinking   -> rotating shimmer / gradient sweep
    speaking   -> glow reacts to live audio amplitude
    error      -> brief red/orange flash

Pure PyQt6 (QPainter), no OpenGL dependency required, so it runs
anywhere PyQt6 runs without extra GPU driver setup.
"""

from __future__ import annotations

import math
from enum import Enum, auto

from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtProperty, QPropertyAnimation, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QRadialGradient, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class OrbState(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ERROR = auto()


# Color per state: (core color, glow color)
STATE_COLORS = {
    OrbState.IDLE:      (QColor(80, 200, 200), QColor(40, 120, 130)),
    OrbState.LISTENING: (QColor(60, 220, 255), QColor(30, 150, 210)),
    OrbState.THINKING:  (QColor(180, 120, 255), QColor(110, 60, 200)),
    OrbState.SPEAKING:  (QColor(90, 240, 190), QColor(40, 170, 140)),
    OrbState.ERROR:     (QColor(255, 90, 90), QColor(180, 40, 40)),
}


class OrbWidget(QWidget):
    """A self-animating glowing orb. Call set_state() to change behavior,
    and feed_amplitude() during SPEAKING/LISTENING to react to live audio."""

    stateChanged = pyqtSignal(OrbState)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(260, 260)

        self._state = OrbState.IDLE
        self._pulse_phase = 0.0      # drives breathing / pulse animation
        self._rotation = 0.0         # drives thinking shimmer rotation
        self._amplitude = 0.0        # live audio level, 0.0 - 1.0
        self._target_amplitude = 0.0
        self._error_flash_alpha = 0.0

        # Master animation clock, ~60fps
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(16)

        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(lambda: self.set_state(OrbState.IDLE))

    # ---------- public API ----------

    def set_state(self, state: OrbState):
        if state == self._state:
            return
        self._state = state
        self.stateChanged.emit(state)
        if state == OrbState.ERROR:
            self._error_flash_alpha = 1.0
            self._error_timer.start(1200)  # auto-return to idle after flash
        self.update()

    def state(self) -> OrbState:
        return self._state

    def feed_amplitude(self, level: float):
        """Feed a 0.0-1.0 audio amplitude value; smoothed internally."""
        self._target_amplitude = max(0.0, min(1.0, level))

    # ---------- animation tick ----------

    def _tick(self):
        # Smooth amplitude towards target (avoids jittery visuals)
        self._amplitude += (self._target_amplitude - self._amplitude) * 0.25

        speed = {
            OrbState.IDLE: 0.02,
            OrbState.LISTENING: 0.06,
            OrbState.THINKING: 0.08,
            OrbState.SPEAKING: 0.10,
            OrbState.ERROR: 0.05,
        }[self._state]
        self._pulse_phase += speed
        self._rotation = (self._rotation + (3.0 if self._state == OrbState.THINKING else 0.4)) % 360

        if self._error_flash_alpha > 0:
            self._error_flash_alpha = max(0.0, self._error_flash_alpha - 0.03)

        self.update()

    # ---------- painting ----------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        base_radius = min(w, h) * 0.28

        core_color, glow_color = STATE_COLORS[self._state]

        # --- breathing / pulse factor ---
        pulse = (math.sin(self._pulse_phase) + 1) / 2  # 0..1
        if self._state == OrbState.SPEAKING:
            # audio-reactive size on top of gentle base pulse
            radius = base_radius * (1.0 + 0.15 * pulse + 0.35 * self._amplitude)
        elif self._state == OrbState.LISTENING:
            radius = base_radius * (1.05 + 0.12 * pulse)
        else:
            radius = base_radius * (1.0 + 0.08 * pulse)

        # --- outer glow (soft radial gradient, large) ---
        glow_radius = radius * 2.6
        gradient = QRadialGradient(QPointF(cx, cy), glow_radius)
        outer = QColor(glow_color)
        outer.setAlpha(0)
        mid = QColor(glow_color)
        mid.setAlpha(90 if self._state != OrbState.IDLE else 55)
        gradient.setColorAt(0.0, mid)
        gradient.setColorAt(0.5, mid)
        gradient.setColorAt(1.0, outer)
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

        # --- listening ripple ring ---
        if self._state == OrbState.LISTENING:
            ripple_progress = (self._pulse_phase * 0.5) % 1.0
            ripple_radius = radius + ripple_progress * radius * 1.8
            ripple_alpha = max(0, int(120 * (1 - ripple_progress)))
            pen = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), ripple_alpha))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), ripple_radius, ripple_radius)

        # --- thinking shimmer: rotating gradient arc ---
        if self._state == OrbState.THINKING:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(self._rotation)
            shimmer_grad = QRadialGradient(QPointF(0, 0), radius * 1.3)
            c1 = QColor(core_color)
            c1.setAlpha(200)
            c2 = QColor(glow_color)
            c2.setAlpha(0)
            shimmer_grad.setColorAt(0.0, c1)
            shimmer_grad.setColorAt(1.0, c2)
            painter.setBrush(QBrush(shimmer_grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(int(-radius * 1.3), int(-radius * 1.3),
                             int(radius * 2.6), int(radius * 2.6), 0, 120 * 16)
            painter.restore()

        # --- core orb body ---
        core_grad = QRadialGradient(QPointF(cx - radius * 0.3, cy - radius * 0.3), radius * 1.4)
        bright = QColor(core_color).lighter(160)
        core_grad.setColorAt(0.0, bright)
        core_grad.setColorAt(0.55, core_color)
        edge = QColor(glow_color)
        core_grad.setColorAt(1.0, edge)
        painter.setBrush(QBrush(core_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # --- error flash overlay ---
        if self._error_flash_alpha > 0:
            flash = QColor(255, 60, 60, int(140 * self._error_flash_alpha))
            painter.setBrush(QBrush(flash))
            painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

        painter.end()
