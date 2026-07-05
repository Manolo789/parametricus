"""
parametricus.viewer_backend.engine_pyside6.shader
================================================

Gerenciamento de programas GLSL.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from OpenGL.GL import *

from OpenGL.GL.shaders import (
    compileProgram,
    compileShader,
)
from .utils import load_text


class ShaderError(RuntimeError):
    """Erro relacionado à compilação de shaders."""


class ShaderProgram:
    """
    Encapsula um programa GLSL.

    Parameters
    ----------
    vertex_source : str
        Código GLSL do vertex shader.

    fragment_source : str
        Código GLSL do fragment shader.
    """

    def __init__(
        self,
        vertex_source: str,
        fragment_source: str,
    ):

        self.program = compileProgram(
            compileShader(vertex_source, GL_VERTEX_SHADER),
            compileShader(fragment_source, GL_FRAGMENT_SHADER),
        )

        self._locations = {}

    # --------------------------------------------------------------
    # Construção
    # --------------------------------------------------------------

    @classmethod
    def from_files(
        cls,
        vertex_file: str | Path,
        fragment_file: str | Path,
    ):
        """
        Cria um programa a partir de arquivos GLSL.
        """

        vertex_file = Path(vertex_file)
        fragment_file = Path(fragment_file)

        if not vertex_file.exists():
            raise ShaderError(f"Arquivo inexistente: {vertex_file}")

        if not fragment_file.exists():
            raise ShaderError(f"Arquivo inexistente: {fragment_file}")

        vertex_source = load_text(vertex_file)

        fragment_source = load_text(fragment_file)

        return cls(
            vertex_source,
            fragment_source,
        )

    # --------------------------------------------------------------
    # Uso
    # --------------------------------------------------------------

    def bind(self):
        """Ativa o programa."""
        glUseProgram(self.program)

    def release(self):
        """Desativa o programa."""
        glUseProgram(0)

    # --------------------------------------------------------------
    # Uniforms
    # --------------------------------------------------------------

    def _location(self, name: str):

        if name not in self._locations:

            self._locations[name] = glGetUniformLocation(
                self.program,
                name,
            )

        return self._locations[name]

    def set_bool(
        self,
        name: str,
        value: bool,
    ):
        glUniform1i(
            self._location(name),
            int(value),
        )

    def set_int(
        self,
        name: str,
        value: int,
    ):
        glUniform1i(
            self._location(name),
            value,
        )

    def set_float(
        self,
        name: str,
        value: float,
    ):
        glUniform1f(
            self._location(name),
            value,
        )

    def set_vec3(
        self,
        name: str,
        value,
    ):

        value = np.asarray(
            value,
            dtype=np.float32,
        )

        glUniform3f(
            self._location(name),
            float(value[0]),
            float(value[1]),
            float(value[2]),
        )

    def set_vec4(
        self,
        name: str,
        value,
    ):

        value = np.asarray(
            value,
            dtype=np.float32,
        )

        glUniform4f(
            self._location(name),
            float(value[0]),
            float(value[1]),
            float(value[2]),
            float(value[3]),
        )

    def set_matrix4(
        self,
        name: str,
        matrix,
    ):

        matrix = np.asarray(
            matrix,
            dtype=np.float32,
        )

        glUniformMatrix4fv(
            self._location(name),
            1,
            GL_TRUE,
            matrix,
        )

    # --------------------------------------------------------------
    # Destruição
    # --------------------------------------------------------------

    def destroy(self):
        """Libera o programa GLSL."""

        if self.program:

            glDeleteProgram(
                self.program
            )

            self.program = None

