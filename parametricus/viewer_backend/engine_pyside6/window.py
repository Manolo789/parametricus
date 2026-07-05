"""
parametricus.viewer_backend.engine_pyside6.window
================================================

Janela principal da engine gráfica do Parametricus.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
)

from .viewer import GLViewer


class MainWindow(QMainWindow):
    """
    Janela principal do visualizador.

    Parameters
    ----------
    title : str
        Título da janela.
    width : int
        Largura inicial.
    height : int
        Altura inicial.
    """

    def __init__(
        self,
        title: str = "Parametricus",
        width: int = 1024,
        height: int = 768,
    ) -> None:

        super().__init__()

        self.setWindowTitle(title)
        self.resize(width, height)

        self._viewer = GLViewer(self)

        central = QWidget(self)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._viewer)

        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    @property
    def viewer(self) -> GLViewer:
        """
        Retorna o widget OpenGL.
        """
        return self._viewer

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def set_mesh(self, mesh) -> None:
        """
        Define a malha exibida.

        Parameters
        ----------
        mesh : Mesh
        """
        self._viewer.set_mesh(mesh)

    def clear(self) -> None:
        """
        Remove a malha atual.
        """
        self._viewer.clear()

    def fit_camera(self) -> None:
        """
        Ajusta automaticamente a câmera.
        """
        self._viewer.fit_camera()

    def save_image(self, filename: str) -> None:
        """
        Salva o framebuffer atual.

        Parameters
        ----------
        filename : str
        """
        self._viewer.save_image(filename)

    # ------------------------------------------------------------------
    # Eventos Qt
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """
        Libera recursos antes do encerramento.
        """

        try:
            self._viewer.cleanup()
        finally:
            event.accept()
