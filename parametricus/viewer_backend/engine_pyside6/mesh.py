"""
parametricus.viewer_backend.engine_pyside6.mesh
===============================================

Representação de uma malha na GPU.

Responsabilidades
-----------------
- Calcular normais por vértice
- Criar VAO, VBO e EBO
- Enviar dados para a GPU
- Renderizar a malha
- Liberar recursos OpenGL
"""

from __future__ import annotations

import ctypes

import numpy as np

from OpenGL.GL import *

from . import geometry
from . import math3d
from .utils import ensure_contiguous

from ...mesher import Mesh


class GLMesh:
    """
    Representação OpenGL de uma Mesh.

    O layout do VBO é:

        position.xyz
        normal.xyz
    """

    def __init__(self, mesh: Mesh):

        self.mesh = mesh

        self.vertices, self.faces = geometry.validate_mesh(
            mesh.vertices,
            mesh.faces,
        )

        self.normals = geometry.compute_vertex_normals(
            self.vertices,
            self.faces,
        )

        self.vao = None
        self.vbo = None
        self.ebo = None

        self.index_count = self.faces.size

        # Bounding sphere (usada pelo ajuste de camera).
        self._center = math3d.center(self.vertices)
        self._radius = float(math3d.radius(self.vertices))


    # ---------------------------------------------------------
    # Propriedades
    # ---------------------------------------------------------

    @property
    def uploaded(self) -> bool:
        """Indica se a malha ja foi enviada para a GPU."""
        return self.vao is not None

    @property
    def center(self):
        """Centro da bounding box."""
        return self._center

    @property
    def radius(self) -> float:
        """Raio da bounding sphere."""
        return self._radius

    # ---------------------------------------------------------
    # Upload
    # ---------------------------------------------------------

    def upload(self):
        """
        Envia a malha para a GPU.
        """

        if self.vao is not None:
            return

        vertex_data = geometry.interleave(
            self.vertices,
            self.normals,
        )
        vertex_data = ensure_contiguous(vertex_data)

        indices = geometry.flatten_indices(self.faces)
        indices = ensure_contiguous(indices, np.uint32)

        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)
        self.ebo = glGenBuffers(1)

        glBindVertexArray(self.vao)

        # ---------------- VBO ----------------

        glBindBuffer(
            GL_ARRAY_BUFFER,
            self.vbo,
        )

        glBufferData(
            GL_ARRAY_BUFFER,
            vertex_data.nbytes,
            vertex_data,
            GL_STATIC_DRAW,
        )

        # ---------------- EBO ----------------

        glBindBuffer(
            GL_ELEMENT_ARRAY_BUFFER,
            self.ebo,
        )

        glBufferData(
            GL_ELEMENT_ARRAY_BUFFER,
            indices.nbytes,
            indices,
            GL_STATIC_DRAW,
        )

        stride = 6 * 4

        # posição
        glEnableVertexAttribArray(0)

        glVertexAttribPointer(
            0,
            3,
            GL_FLOAT,
            GL_FALSE,
            stride,
            ctypes.c_void_p(0),
        )

        # normal
        glEnableVertexAttribArray(1)

        glVertexAttribPointer(
            1,
            3,
            GL_FLOAT,
            GL_FALSE,
            stride,
            ctypes.c_void_p(12),
        )

        glBindVertexArray(0)

    # ---------------------------------------------------------
    # Renderização
    # ---------------------------------------------------------

    def draw(self):

        if self.vao is None:
            return

        glBindVertexArray(self.vao)

        glDrawElements(
            GL_TRIANGLES,
            self.index_count,
            GL_UNSIGNED_INT,
            None,
        )

        glBindVertexArray(0)

    # ---------------------------------------------------------
    # Recursos
    # ---------------------------------------------------------

    def destroy(self):

        if self.vbo is not None:
            glDeleteBuffers(
                1,
                [self.vbo],
            )
            self.vbo = None

        if self.ebo is not None:
            glDeleteBuffers(
                1,
                [self.ebo],
            )
            self.ebo = None

        if self.vao is not None:
            glDeleteVertexArrays(
                1,
                [self.vao],
            )
            self.vao = None

