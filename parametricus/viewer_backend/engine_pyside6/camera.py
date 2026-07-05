"""
parametricus.viewer_backend.engine_pyside6.camera
================================================

Implementação de uma câmera orbital para navegação 3D.
"""

from __future__ import annotations

import numpy as np

from .math3d import (
    look_at,
    perspective,
    normalize,
)


class OrbitCamera:
    """
    Câmera orbital.

    A câmera gira em torno de um ponto focal (target).
    """

    def __init__(
        self,
        fov: float = 45.0,
        z_near: float = 0.01,
        z_far: float = 10000.0,
    ):

        self.fov = fov
        self.z_near = z_near
        self.z_far = z_far

        self.target = np.zeros(3, dtype=np.float32)

        self.distance = 5.0

        self.azimuth = np.radians(-45.0)
        self.elevation = np.radians(30.0)

        self.aspect = 1.0

        self.up = np.array(
            [0.0, 0.0, 1.0],
            dtype=np.float32,
        )

    # --------------------------------------------------------------
    # Matrizes
    # --------------------------------------------------------------

    @property
    def position(self) -> np.ndarray:
        """
        Posição da câmera no espaço.
        """

        ce = np.cos(self.elevation)
        se = np.sin(self.elevation)

        ca = np.cos(self.azimuth)
        sa = np.sin(self.azimuth)

        x = self.distance * ce * ca
        y = self.distance * ce * sa
        z = self.distance * se

        return self.target + np.array(
            [x, y, z],
            dtype=np.float32,
        )

    @property
    def view_matrix(self) -> np.ndarray:
        """Matriz View."""

        return look_at(
            self.position,
            self.target,
            self.up,
        )

    @property
    def projection_matrix(self) -> np.ndarray:
        """Matriz Projection."""

        return perspective(
            self.fov,
            self.aspect,
            self.z_near,
            self.z_far,
        )

    # --------------------------------------------------------------
    # Configuração
    # --------------------------------------------------------------

    def resize(
        self,
        width: int,
        height: int,
    ):
        """Atualiza a razão de aspecto."""

        if height <= 0:
            height = 1

        self.aspect = width / height

    # --------------------------------------------------------------
    # Navegação
    # --------------------------------------------------------------

    def orbit(
        self,
        dx: float,
        dy: float,
        sensitivity: float = 0.01,
    ):
        """
        Rotaciona a câmera ao redor do alvo.
        """

        self.azimuth -= dx * sensitivity
        self.elevation += dy * sensitivity

        limit = np.radians(89.0)

        self.elevation = np.clip(
            self.elevation,
            -limit,
            limit,
        )

    def zoom(
        self,
        delta: float,
        sensitivity: float = 0.15,
    ):
        """
        Aproxima ou afasta a câmera.
        """

        factor = np.exp(-delta * sensitivity)

        self.distance *= factor

        self.distance = max(
            self.distance,
            1e-3,
        )

    def pan(
        self,
        dx: float,
        dy: float,
        sensitivity: float = 0.002,
    ):
        """
        Move o ponto focal paralelamente ao plano da tela.
        """

        eye = self.position

        forward = normalize(self.target - eye)

        right = normalize(np.cross(forward, self.up))

        up = normalize(np.cross(right, forward))

        scale = self.distance * sensitivity

        self.target -= right * dx * scale
        self.target += up * dy * scale

    # --------------------------------------------------------------
    # Ajuste automático
    # --------------------------------------------------------------

    def fit(
        self,
        center: np.ndarray,
        radius: float,
    ):
        """
        Posiciona a câmera para visualizar toda a malha.
        """

        self.target = np.asarray(
            center,
            dtype=np.float32,
        )

        if radius <= 0:
            radius = 1.0

        fov = np.radians(self.fov)

        self.distance = (
            radius / np.sin(fov * 0.5)
        )

        self.distance *= 1.35

        self.z_near = max(
            self.distance / 1000.0,
            0.001,
        )

        self.z_far = self.distance * 100.0

    # --------------------------------------------------------------
    # Utilidades
    # --------------------------------------------------------------

    def reset(self):
        """
        Restaura a orientação padrão.
        """

        self.azimuth = np.radians(-45.0)
        self.elevation = np.radians(30.0)

    def set_angles(
        self,
        azimuth: float,
        elevation: float,
        degrees: bool = True,
    ):
        """
        Define a orientação da câmera.
        """

        if degrees:
            azimuth = np.radians(azimuth)
            elevation = np.radians(elevation)

        self.azimuth = azimuth
        self.elevation = elevation
