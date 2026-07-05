"""
parametricus.viewer_backend.engine_pyside6
=========================================

Engine gráfica 3D do Parametricus baseada em:

    • PySide6
    • QOpenGLWidget
    • OpenGL 3.3 Core Profile
    • PyOpenGL
    • NumPy

A engine é responsável por:

    - criação da janela OpenGL;
    - gerenciamento do contexto gráfico;
    - renderização de malhas;
    - iluminação;
    - câmera orbital;
    - interação com o usuário;
    - captura de imagens.

A API pública desta engine é composta pelas classes abaixo.
"""

from .application import Application
from .window import MainWindow
from .viewer import GLViewer
from .camera import OrbitCamera
from .mesh import GLMesh
from .renderer import Renderer
from .shader import ShaderProgram

__all__ = [
    "Application",
    "MainWindow",
    "GLViewer",
    "OrbitCamera",
    "GLMesh",
    "Renderer",
    "ShaderProgram",
]
