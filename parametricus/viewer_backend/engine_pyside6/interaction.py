"""
parametricus.viewer_backend.engine_pyside6.interaction
======================================================

Controlador de interação do visualizador.

Responsável por:

    • órbita
    • pan
    • zoom
    • atalhos de teclado

Não depende de OpenGL.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import (
    QMouseEvent,
    QWheelEvent,
    QKeyEvent,
)

from .camera import OrbitCamera


class InteractionController:
    """
    Controlador de interação.

    Parameters
    ----------
    camera
        Instância de OrbitCamera.

    update_callback
        Função chamada sempre que a cena deve ser redesenhada.

    fit_callback
        Enquadra automaticamente a malha.

    reset_callback
        Reinicia a câmera.
    """

    def __init__(
        self,
        camera: OrbitCamera,
        update_callback,
        fit_callback=None,
        reset_callback=None,
    ):

        self.camera = camera

        self.update = update_callback

        self.fit = fit_callback

        self.reset = reset_callback

        self._last_pos = QPoint()

        self.left_pressed = False
        self.middle_pressed = False
        self.right_pressed = False

    # =====================================================
    # Mouse
    # =====================================================

    def mouse_press(self, event: QMouseEvent):

        self._last_pos = event.position().toPoint()

        if event.button() == Qt.LeftButton:
            self.left_pressed = True

        elif event.button() == Qt.MiddleButton:
            self.middle_pressed = True

        elif event.button() == Qt.RightButton:
            self.right_pressed = True

    def mouse_release(self, event: QMouseEvent):

        if event.button() == Qt.LeftButton:
            self.left_pressed = False

        elif event.button() == Qt.MiddleButton:
            self.middle_pressed = False

        elif event.button() == Qt.RightButton:
            self.right_pressed = False

    def mouse_move(self, event: QMouseEvent):

        pos = event.position().toPoint()

        dx = pos.x() - self._last_pos.x()
        dy = pos.y() - self._last_pos.y()

        self._last_pos = pos

        redraw = False

        # -----------------------------------------
        # Órbita
        # -----------------------------------------

        if self.left_pressed:

            self.camera.orbit(dx, dy)

            redraw = True

        # -----------------------------------------
        # Pan
        # -----------------------------------------

        elif self.middle_pressed or self.right_pressed:

            self.camera.pan(dx, dy)

            redraw = True

        if redraw:
            self.update()

    def wheel(self, event: QWheelEvent):

        delta = event.angleDelta().y() / 120.0

        self.camera.zoom(delta)

        self.update()

    # =====================================================
    # Teclado
    # =====================================================

    def key_press(self, event: QKeyEvent):

        key = event.key()

        if key == Qt.Key_F:

            if self.fit is not None:
                self.fit()

            return True

        if key == Qt.Key_R:

            if self.reset is not None:
                self.reset()

            return True

        return False

    # =====================================================
    # Estado
    # =====================================================

    def cancel(self):
        """
        Cancela qualquer interação em andamento.
        """

        self.left_pressed = False
        self.middle_pressed = False
        self.right_pressed = False

    def is_dragging(self):

        return (
            self.left_pressed
            or self.middle_pressed
            or self.right_pressed
        )
