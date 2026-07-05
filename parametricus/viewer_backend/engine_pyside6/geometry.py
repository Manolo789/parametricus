"""
parametricus.viewer_backend.engine_pyside6.geometry
===================================================

Funções geométricas para preparação e análise de malhas.

Este módulo é totalmente independente de Qt e OpenGL.
"""

from __future__ import annotations

import numpy as np

EPSILON = 1e-12


# ==========================================================
# Validação
# ==========================================================

def validate_mesh(vertices, faces):
    """
    Valida os arrays de uma malha.

    Parameters
    ----------
    vertices : (N,3)
    faces : (M,3)
    """

    vertices = np.asarray(vertices, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.uint32)

    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("vertices deve possuir formato (N,3).")

    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("faces deve possuir formato (M,3).")

    if len(vertices) == 0:
        raise ValueError("Malha sem vértices.")

    if len(faces) == 0:
        raise ValueError("Malha sem faces.")

    if faces.max() >= len(vertices):
        raise ValueError("Índice de face inválido.")

    return vertices, faces


# ==========================================================
# Bounding Box
# ==========================================================
def bounding_box(vertices):

    vertices = np.asarray(vertices)

    return (
        vertices.min(axis=0),
        vertices.max(axis=0),
    )

def center(vertices):

    bmin, bmax = bounding_box(vertices)

    return (bmin + bmax) * 0.5

def radius(vertices):

    c = center(vertices)

    return np.linalg.norm(vertices - c, axis=1).max()


# ==========================================================
# Normais
# ==========================================================

def compute_face_normals(vertices, faces):
    """
    Calcula as normais das faces.
    """

    vertices, faces = validate_mesh(vertices, faces)

    p0 = vertices[faces[:, 0]]
    p1 = vertices[faces[:, 1]]
    p2 = vertices[faces[:, 2]]

    normals = np.cross(
        p1 - p0,
        p2 - p0,
    )

    lengths = np.linalg.norm(
        normals,
        axis=1,
        keepdims=True,
    )

    lengths[lengths < EPSILON] = 1.0

    normals /= lengths

    return normals.astype(np.float32)


def compute_vertex_normals(vertices, faces):
    """
    Calcula normais por vértice.
    """

    vertices, faces = validate_mesh(vertices, faces)

    normals = np.zeros_like(vertices)

    face_normals = compute_face_normals(
        vertices,
        faces,
    )

    np.add.at(
        normals,
        faces.ravel(),
        np.repeat(face_normals, 3, axis=0),
    )

    lengths = np.linalg.norm(
        normals,
        axis=1,
        keepdims=True,
    )

    lengths[lengths < EPSILON] = 1.0

    normals /= lengths

    return normals.astype(np.float32)


# ==========================================================
# Interleaving
# ==========================================================

def interleave(vertices, normals):
    """
    Produz um VBO no formato

        x y z nx ny nz
    """

    vertices = np.asarray(vertices, dtype=np.float32)
    normals = np.asarray(normals, dtype=np.float32)

    return np.hstack(
        (
            vertices,
            normals,
        )
    ).astype(np.float32)


# ==========================================================
# Índices
# ==========================================================

def flatten_indices(faces):
    """
    Converte (M,3) em vetor de índices.
    """

    return np.asarray(
        faces,
        dtype=np.uint32,
    ).ravel()


# ==========================================================
# Estatísticas
# ==========================================================
def triangle_count(faces):

    return len(faces)

def vertex_count(vertices):

    return len(vertices)


def edge_count(faces):
    """
    Número aproximado de arestas únicas.
    """

    edges = set()

    for a, b, c in faces:

        edges.add(tuple(sorted((a, b))))
        edges.add(tuple(sorted((b, c))))
        edges.add(tuple(sorted((c, a))))

    return len(edges)


# ==========================================================
# Cores
# ==========================================================

def vertex_colors(color, count):
    """
    Replica uma cor RGB para todos os vértices.
    """

    color = np.asarray(
        color,
        dtype=np.float32,
    )

    return np.tile(
        color,
        (count, 1),
    )


# ==========================================================
# Transformações
# ==========================================================

def transform(vertices, matrix):
    """
    Aplica uma matriz homogênea 4x4 aos vértices.
    """

    vertices = np.asarray(
        vertices,
        dtype=np.float32,
    )

    ones = np.ones(
        (len(vertices), 1),
        dtype=np.float32,
    )

    vh = np.hstack(
        (
            vertices,
            ones,
        )
    )

    vt = (matrix @ vh.T).T

    return vt[:, :3]


# ==========================================================
# Triangulação
# ==========================================================

def triangulate(faces):
    """
    Mantido para compatibilidade futura.

    Atualmente todas as faces já são triangulares.
    """

    return np.asarray(
        faces,
        dtype=np.uint32,
    )
