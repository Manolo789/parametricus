"""
parametricus.viewer_backend.engine_pyside6.renderer
==================================================

Renderizador OpenGL do Parametricus.
"""

from __future__ import annotations

import numpy as np

from OpenGL.GL import *

from .camera import OrbitCamera
from .mesh import GLMesh
from .shader import ShaderProgram
from .math3d import identity
from .utils import resource_path


class Renderer:
    """
    Renderizador OpenGL.
    """

    def __init__(self, camera: OrbitCamera):

        self.camera = camera

        self.mesh: GLMesh | None = None

        self.shader: ShaderProgram | None = None

        self.background = np.array(
            [0.97, 0.97, 0.98],
            dtype=np.float32,
        )

        self.model = identity()

        self.light_direction = np.array(
            [-0.4, -0.3, -1.0],
            dtype=np.float32,
        )

        self.light_color = np.array(
            [1.0, 1.0, 1.0],
            dtype=np.float32,
        )

        self.object_color = np.array(
            [0.29, 0.56, 0.85],
            dtype=np.float32,
        )

        self.ambient = 0.25
        self.specular = 0.35
        self.shininess = 64.0

        # Desative se a malha nao garantir winding CCW consistente.
        self.cull_backfaces = True

    # ---------------------------------------------------------
    # Inicialização
    # ---------------------------------------------------------

    def initialize(self):

        glEnable(GL_DEPTH_TEST)

        if self.cull_backfaces:
            glEnable(GL_CULL_FACE)
            glCullFace(GL_BACK)

        glEnable(GL_MULTISAMPLE)

        glClearColor(
            *self.background,
            1.0,
        )

        shader_dir = resource_path("shaders")

        self.shader = ShaderProgram.from_files(
            shader_dir / "phong.vert",
            shader_dir / "phong.frag",
        )

    # ---------------------------------------------------------
    # Configuração
    # ---------------------------------------------------------

    def set_mesh(self, mesh):

        if self.mesh is not None:
            self.mesh.destroy()

        self.mesh = GLMesh(mesh)

        self.camera.fit(
            self.mesh.center,
            self.mesh.radius,
        )
    
    def clear_mesh(self):
        """
        Remove a malha atualmente carregada.
        """

        if self.mesh is not None:
            self.mesh.destroy()
            self.mesh = None

    def set_background(self, color):
        self.background = np.asarray(
            color,
            dtype=np.float32,
        )

        glClearColor(
            *self.background,
            1.0,
        )

    def set_object_color(self, color):

        self.object_color = np.asarray(
            color,
            dtype=np.float32,
        )

    # ---------------------------------------------------------
    # Janela
    # ---------------------------------------------------------

    def resize(
        self,
        width,
        height,
    ):

        if height <= 0:
            height = 1

        glViewport(
            0,
            0,
            width,
            height,
        )

        self.camera.resize(
            width,
            height,
        )

    # ---------------------------------------------------------
    # Renderização
    # ---------------------------------------------------------

    def render(self):

        glClear(
            GL_COLOR_BUFFER_BIT |
            GL_DEPTH_BUFFER_BIT
        )

        if self.mesh is None or self.shader is None:
            return

        if not self.mesh.uploaded:
            self.mesh.upload()

        self.shader.bind()

        self.shader.set_matrix4(
            "model",
            self.model,
        )

        self.shader.set_matrix4(
            "view",
            self.camera.view_matrix,
        )

        self.shader.set_matrix4(
            "projection",
            self.camera.projection_matrix,
        )

        self.shader.set_vec3(
            "viewPos",
            self.camera.position,
        )

        self.shader.set_vec3(
            "light.direction",
            self.light_direction,
        )

        self.shader.set_vec3(
            "light.color",
            self.light_color,
        )

        self.shader.set_vec3(
            "material.color",
            self.object_color,
        )

        self.shader.set_float(
            "material.ambient",
            self.ambient,
        )

        self.shader.set_float(
            "material.specular",
            self.specular,
        )

        self.shader.set_float(
            "material.shininess",
            self.shininess,
        )

        self.mesh.draw()

        self.shader.release()

    # ---------------------------------------------------------
    # Recursos
    # ---------------------------------------------------------

    def destroy(self):

        if self.mesh is not None:
            self.mesh.destroy()
            self.mesh = None

        if self.shader is not None:
            self.shader.destroy()
            self.shader = None
