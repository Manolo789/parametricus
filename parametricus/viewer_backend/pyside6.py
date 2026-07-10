"""
parametricus.viewer_backend.pyside6
==================================

Backend de visualização utilizando PySide6 + OpenGL.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ..mesher import Mesh
from .engine_pyside6.window import MainWindow
from .engine_pyside6.viewer import configure_default_surface_format
from .engine_pyside6.utils import hex_to_rgb
from .._log import logger

# Install PySide6:
# pip install numpy PySide6 PyOpenGL


def show_pyside6(mesh: Mesh, title: str = "parametricus",
    color: str = "#4a90d9", save_path: str | None = None, show: bool = True) -> None:
    """
    Exibe uma malha utilizando a engine PySide6.

    Parameters
    ----------
    mesh
        Malha a ser exibida.

    title
        Título da janela.

    color
        Cor hexadecimal do modelo.

    save_path
        Caminho para salvar uma captura da tela.

    show
        Se False, apenas renderiza e salva a imagem.
    """

    app = QApplication.instance()

    owns_app = False

    if app is None:
        # O formato padrão precisa ser definido antes da QApplication
        # para que o contexto 3.3 Core seja aplicado em todas as
        # plataformas.
        configure_default_surface_format()

        app = QApplication(sys.argv)

        owns_app = True

    window = MainWindow()

    window.setWindowTitle(title)

    viewer = window.viewer

    if not show:
        # Renderiza sem exibir a janela na tela.
        window.setAttribute(Qt.WA_DontShowOnScreen, True)
        window.resize(1200, 900)

    window.show()

    app.processEvents()

    viewer.set_object_color(
        hex_to_rgb(color)
    )

    viewer.set_mesh(mesh)

    viewer.fit_camera()

    if show:

        # Executa o loop apenas se nós criamos a aplicação e
        # nenhum loop desta engine já está em andamento.
        if owns_app and not app.property("_parametricus_running"):

            app.setProperty("_parametricus_running", True)

            try:
                app.exec()
            finally:
                app.setProperty("_parametricus_running", False)

        return

    #
    # Renderização offscreen
    #

    app.processEvents()

    if save_path is not None:

        # grabFramebuffer() força uma renderização síncrona
        # antes de capturar o conteúdo.
        viewer.save_image(save_path)

        logger.info("Imagem salva em: %s", save_path)

    window.close()
