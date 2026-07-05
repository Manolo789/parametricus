"""
parametricus.viewer_backend.engine_pyside6.math3d
================================================

Funções matemáticas para a engine OpenGL.

Todas as matrizes são armazenadas em float32 para envio direto
ao OpenGL.
"""

from __future__ import annotations

import numpy as np
from .utils import normalize, identity

FloatArray = np.ndarray


# ---------------------------------------------------------------------
# Vetores
# ---------------------------------------------------------------------

def length(v: FloatArray) -> float:
    """Comprimento de um vetor."""
    return float(np.linalg.norm(v))


def cross(a: FloatArray, b: FloatArray) -> FloatArray:
    """Produto vetorial."""
    return np.cross(a, b)


def dot(a: FloatArray, b: FloatArray) -> float:
    """Produto escalar."""
    return float(np.dot(a, b))


# ---------------------------------------------------------------------
# Matrizes
# ---------------------------------------------------------------------

def translate(x: float, y: float, z: float) -> FloatArray:
    """Matriz de translação."""

    M = identity()

    M[0, 3] = x
    M[1, 3] = y
    M[2, 3] = z

    return M


def scale(sx: float, sy: float, sz: float) -> FloatArray:
    """Matriz de escala."""

    M = identity()

    M[0, 0] = sx
    M[1, 1] = sy
    M[2, 2] = sz

    return M


# ---------------------------------------------------------------------
# Rotações
# ---------------------------------------------------------------------

def rotation_x(angle: float) -> FloatArray:
    """Rotação em torno de X."""

    c = np.cos(angle)
    s = np.sin(angle)

    return np.array([
        [1, 0, 0, 0],
        [0, c,-s, 0],
        [0, s, c, 0],
        [0, 0, 0, 1]
    ], dtype=np.float32)


def rotation_y(angle: float) -> FloatArray:
    """Rotação em torno de Y."""

    c = np.cos(angle)
    s = np.sin(angle)

    return np.array([
        [ c,0,s,0],
        [ 0,1,0,0],
        [-s,0,c,0],
        [ 0,0,0,1]
    ], dtype=np.float32)


def rotation_z(angle: float) -> FloatArray:
    """Rotação em torno de Z."""

    c = np.cos(angle)
    s = np.sin(angle)

    return np.array([
        [c,-s,0,0],
        [s, c,0,0],
        [0, 0,1,0],
        [0, 0,0,1]
    ], dtype=np.float32)


# ---------------------------------------------------------------------
# Projeção
# ---------------------------------------------------------------------

def perspective(
    fovy: float,
    aspect: float,
    z_near: float,
    z_far: float,
) -> FloatArray:
    """
    Matriz de projeção perspectiva.

    Parameters
    ----------
    fovy : float
        Campo de visão em graus.
    aspect : float
        Razão largura/altura.
    z_near : float
    z_far : float
    """

    f = 1.0 / np.tan(np.radians(fovy) * 0.5)

    M = np.zeros((4, 4), dtype=np.float32)

    M[0, 0] = f / aspect
    M[1, 1] = f

    M[2, 2] = (z_far + z_near) / (z_near - z_far)
    M[2, 3] = (2.0 * z_far * z_near) / (z_near - z_far)

    M[3, 2] = -1.0

    return M


# ---------------------------------------------------------------------
# Câmera
# ---------------------------------------------------------------------

def look_at(
    eye: FloatArray,
    center: FloatArray,
    up: FloatArray,
) -> FloatArray:
    """
    Equivalente ao gluLookAt().
    """

    eye = np.asarray(eye, dtype=np.float32)
    center = np.asarray(center, dtype=np.float32)
    up = normalize(np.asarray(up, dtype=np.float32))

    forward = normalize(center - eye)

    side = normalize(np.cross(forward, up))

    up = np.cross(side, forward)

    M = identity()

    M[0, :3] = side
    M[1, :3] = up
    M[2, :3] = -forward

    M[0, 3] = -np.dot(side, eye)
    M[1, 3] = -np.dot(up, eye)
    M[2, 3] = np.dot(forward, eye)

    return M


# ---------------------------------------------------------------------
# Transformações
# ---------------------------------------------------------------------

def transform(
    vertices: FloatArray,
    matrix: FloatArray,
) -> FloatArray:
    """
    Aplica uma transformação homogênea a um conjunto de vértices.

    Parameters
    ----------
    vertices : (N,3)
    matrix : (4,4)

    Returns
    -------
    ndarray (N,3)
    """

    ones = np.ones((len(vertices), 1), dtype=np.float32)

    vh = np.hstack((vertices.astype(np.float32), ones))

    vt = (matrix @ vh.T).T

    return vt[:, :3]


# ---------------------------------------------------------------------
# Bounding Box
# ---------------------------------------------------------------------

def bounding_box(vertices: FloatArray):
    """
    Calcula a bounding box.

    Returns
    -------
    (bmin, bmax)
    """

    bmin = vertices.min(axis=0)

    bmax = vertices.max(axis=0)

    return bmin, bmax


def center(vertices: FloatArray):
    """
    Centro da bounding box.
    """

    bmin, bmax = bounding_box(vertices)

    return (bmin + bmax) * 0.5


def radius(vertices: FloatArray):
    """
    Raio da bounding sphere.
    """

    c = center(vertices)

    return np.linalg.norm(vertices - c, axis=1).max()
