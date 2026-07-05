"""
parametricus.viewer_backend.engine_pyside6.application
======================================================

Gerenciamento da aplicação Qt.

Este módulo garante a existência de uma única instância de
QApplication e fornece uma interface simples para iniciar o
visualizador do Parametricus.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .window import MainWindow
from .viewer import configure_default_surface_format


class Application:
    """
    Gerencia o ciclo de vida da aplicação Qt.

    Parameters
    ----------
    title : str
        Título da janela.
    """

    def __init__(self, title: str = "Parametricus") -> None:

        self._owns_app = False

        app = QApplication.instance()

        if app is None:
            configure_default_surface_format()
            app = QApplication(sys.argv)
            self._owns_app = True

        self._app = app

        self.window = MainWindow(title=title)

    @property
    def qapp(self) -> QApplication:
        """Retorna a instância de QApplication."""
        return self._app

    def show(self) -> None:
        """Exibe a janela principal."""
        self.window.show()

    def close(self) -> None:
        """Fecha a janela principal."""
        self.window.close()

    def exec(self) -> int:
        """
        Inicia o loop de eventos Qt.

        Returns
        -------
        int
            Código de retorno da aplicação.
        """
        self.show()

        if self._owns_app:
            return self._app.exec()

        return 0

    def run(self) -> int:
        """
        Alias para exec().

        Returns
        -------
        int
        """
        return self.exec()
