"""
parametricus.viewer_backend.engine_pyside6.utils
================================================

Funções utilitárias da engine PySide6.

Este módulo não depende de Qt nem de OpenGL.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


# ==========================================================
# Constantes
# ==========================================================

EPSILON = 1e-9


# ==========================================================
# Matemática
# ==========================================================

def clamp(value, minimum, maximum):
    """
    Limita um valor ao intervalo [minimum, maximum].
    """
    return max(minimum, min(value, maximum))


def lerp(a, b, t):
    """
    Interpolação linear.
    """
    return (1.0 - t) * a + t * b


def almost_equal(a, b, eps=EPSILON):
    """
    Compara dois valores de ponto flutuante.
    """
    return abs(a - b) <= eps


# ==========================================================
# NumPy
# ==========================================================

def ensure_numpy(data, dtype=np.float32):
    """
    Converte um objeto para ndarray.
    """
    return np.asarray(data, dtype=dtype)


def ensure_contiguous(data, dtype=np.float32):
    """
    Retorna um ndarray contíguo em memória.
    """
    return np.ascontiguousarray(data, dtype=dtype)


# ==========================================================
# Cores
# ==========================================================

def hex_to_rgb(color: str):
    """
    '#4a90d9' -> array([0.29,0.56,0.85])
    """

    color = color.strip()

    if color.startswith("#"):
        color = color[1:]

    if len(color) != 6:
        raise ValueError("Cor hexadecimal inválida.")

    return np.array([
        int(color[0:2], 16),
        int(color[2:4], 16),
        int(color[4:6], 16),
    ], dtype=np.float32) / 255.0


def rgb255_to_float(rgb):
    """
    [74,144,217] -> [0.29,0.56,0.85]
    """
    rgb = np.asarray(rgb, dtype=np.float32)
    return rgb / 255.0


def float_to_rgb255(rgb):
    """
    [0.29,0.56,0.85] -> [74,144,217]
    """
    rgb = np.asarray(rgb)

    return np.clip(
        np.round(rgb * 255),
        0,
        255,
    ).astype(np.uint8)


# ==========================================================
# Arquivos
# ==========================================================

def load_text(path):
    """
    Carrega um arquivo texto.
    """

    path = Path(path)

    return path.read_text(
        encoding="utf-8"
    )


def save_text(path, text):
    """
    Salva um arquivo texto.
    """

    path = Path(path)

    path.write_text(
        text,
        encoding="utf-8"
    )


def resource_path(*parts):
    """
    Caminho absoluto para um recurso da engine.

    Exemplo
    --------
    resource_path("shaders", "phong.vert")
    """

    return Path(__file__).parent.joinpath(*parts)


# ==========================================================
# Vetores
# ==========================================================

def normalize(v):
    """
    Normaliza um vetor.
    """

    v = np.asarray(v, dtype=np.float32)

    n = np.linalg.norm(v)

    if n < EPSILON:
        return v.copy()

    return v / n


# ==========================================================
# Matrizes
# ==========================================================

def identity():
    """
    Matriz identidade 4x4.
    """

    return np.identity(
        4,
        dtype=np.float32,
    )


# ==========================================================
# Informações
# ==========================================================

def sizeof_mb(array):
    """
    Tamanho de um ndarray em MB.
    """

    return array.nbytes / (1024.0 * 1024.0)


def sizeof_kb(array):
    """
    Tamanho de um ndarray em KB.
    """

    return array.nbytes / 1024.0


# ==========================================================
# Tempo
# ==========================================================

def timestamp():
    """
    Timestamp ISO.
    """

    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")
