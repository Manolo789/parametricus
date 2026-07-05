"""
parametricus.viewer_backend.engine_pyside6.viewer
=================================================

Widget OpenGL responsável pela renderização da cena.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QSurfaceFormat,
    QMouseEvent,
    QWheelEvent,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from .renderer import Renderer
from .interaction import InteractionController
from .camera import OrbitCamera


def configure_default_surface_format() -> None:
    """
    Define o QSurfaceFormat padrao da aplicacao.

    Deve ser chamada ANTES da criacao da QApplication para
    garantir que o contexto OpenGL 3.3 Core Profile seja
    aplicado em todas as plataformas.
    """

    fmt = QSurfaceFormat()

    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(4)

    QSurfaceFormat.setDefaultFormat(fmt)


class GLViewer(QOpenGLWidget):
    """
    Widget OpenGL do Parametricus.

    Responsabilidades
    -----------------
    • criação do contexto OpenGL
    • gerenciamento da viewport
    • interação do usuário
    • renderização da cena
    """

    def __init__(self, parent=None):

        super().__init__(parent)

        # -------------------------------------------------------------
        # Renderizador
        # -------------------------------------------------------------

        self.camera = OrbitCamera()
        
        self.renderer = Renderer(
            camera=self.camera,
        )
        
        # -------------------------------------------------------------
        # Estado da interação
        # -------------------------------------------------------------

        self.interaction = InteractionController(
            camera=self.camera,
            update_callback=self.update,
            fit_callback=self.fit_camera,
            reset_callback=self.reset_camera,
        )

        # -------------------------------------------------------------
        # Configuração do widget
        # -------------------------------------------------------------

        self.setMouseTracking(True)

        self.setFocusPolicy(Qt.StrongFocus)

        self.setMinimumSize(400, 300)


    # =============================================================
    # OpenGL
    # =============================================================

    def initializeGL(self):
        """
        Inicializa o contexto OpenGL.

        Chamado automaticamente pelo Qt uma única vez.
        """

        self.renderer.initialize()

    def resizeGL(
        self,
        width: int,
        height: int,
    ):
        """
        Atualiza a viewport.
        """

        self.renderer.resize(width, height)

    # =============================================================
    # Renderização
    # =============================================================

    def paintGL(self):
        """
        Renderiza a cena.

        Chamado automaticamente pelo Qt sempre que o widget
        precisa ser redesenhado.
        """

        self.renderer.render()
        
    def render_now(self):
        """
        Forca uma renderizacao sincrona imediata.
        """
        self.repaint()

    # =============================================================
    # API pública
    # =============================================================

    def set_mesh(self, mesh):
        """
        Define a malha atualmente exibida.

        Parameters
        ----------
        mesh : Mesh
        """

        self.makeCurrent()

        self.renderer.set_mesh(mesh)

        self.doneCurrent()

        self.update()

    def clear(self):
        """
        Remove a malha atualmente carregada.
        """
        self.makeCurrent()

        self.renderer.clear_mesh()

        self.doneCurrent()

        self.update()

    def fit_camera(self):
        """
        Ajusta automaticamente a câmera para enquadrar
        toda a malha.
        """

        if self.renderer.mesh is None:
            return

        self.camera.fit(
            self.renderer.mesh.center,
            self.renderer.mesh.radius,
        )

        self.update()

    def set_background_color(self, color):
        """
        Define a cor de fundo.

        Parameters
        ----------
        color : iterable(float)
            RGB no intervalo [0,1].
        """

        self.makeCurrent()

        self.renderer.set_background(color)

        self.doneCurrent()

        self.update()

    def set_object_color(self, color):
        """
        Define a cor do objeto.

        Parameters
        ----------
        color : iterable(float)
            RGB no intervalo [0,1].
        """

        self.makeCurrent()

        self.renderer.set_object_color(color)

        self.doneCurrent()

        self.update()

    # =============================================================
    # Captura de tela
    # =============================================================

    def save_image(self, filename: str):
        """
        Salva o conteúdo atual do framebuffer.

        Parameters
        ----------
        filename : str
        """

        image = self.grabFramebuffer()

        image.save(filename)

    # =============================================================
    # Limpeza
    # =============================================================

    def cleanup(self):
        """
        Libera todos os recursos OpenGL.
        """

        self.makeCurrent()

        self.renderer.destroy()

        self.doneCurrent()
        
    # =============================================================
    # Eventos do mouse
    # =============================================================

    def mousePressEvent(self, event: QMouseEvent):
        """
        Início de uma interação com o mouse.
        """

        self.interaction.mouse_press(event)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """
        Finaliza uma interação.
        """

        self.interaction.mouse_release(event)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        """
        Trata movimentação do mouse.
        """

        self.interaction.mouse_move(event)
        event.accept()

    def wheelEvent(self, event: QWheelEvent):
        """
        Zoom através da roda do mouse.
        """

        self.interaction.wheel(event)
        event.accept()

    # =============================================================
    # Utilidades
    # =============================================================

    def reset_camera(self):
        """
        Restaura a orientação padrão da câmera.
        """

        self.camera.reset()

        if self.renderer.mesh is not None:

            self.camera.fit(
                self.renderer.mesh.center,
                self.renderer.mesh.radius,
            )

        self.update()
        
    # =============================================================
    # Eventos do teclado
    # =============================================================

    def keyPressEvent(self, event):
        """
        Atalhos do visualizador.

        F : enquadra o modelo
        R : reseta orientação
        Esc : limpa foco
        """

        if self.interaction.key_press(event):
            event.accept()
            return

        super().keyPressEvent(event)

    # =============================================================
    # Menu de contexto
    # =============================================================

    def contextMenuEvent(self, event):
        """
        Reservado para futuras ferramentas.

        A implementação permanece vazia para que a API
        possa evoluir sem alterar o restante da engine.
        """

        event.accept()

    # =============================================================
    # Eventos do widget
    # =============================================================

    def showEvent(self, event):
        """
        Atualiza a viewport quando o widget torna-se visível.
        """

        super().showEvent(event)

        self.update()

    def closeEvent(self, event):
        """
        Libera recursos OpenGL.
        """

        try:
            self.interaction.cancel()
            self.cleanup()
        finally:
            super().closeEvent(event)

    # =============================================================
    # Atualização
    # =============================================================

    def refresh(self):
        """
        Força uma nova renderização.
        """

        self.update()

    # =============================================================
    # Propriedades
    # =============================================================

    @property
    def mesh(self):
        """
        Retorna a malha atualmente carregada.
        """

        return self.renderer.mesh

    @property
    def has_mesh(self) -> bool:
        """
        Indica se existe uma malha carregada.
        """

        return self.renderer.mesh is not None
