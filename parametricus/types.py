"""
parametricus.types
==================
Aliases de tipos compartilhados entre os módulos numéricos
(Fase 1.1 do roadmap — antes duplicados em ``sdf.py`` e ``sketch.py``).
"""

from __future__ import annotations

from typing import Callable, Sequence, Union

import numpy as np
from numpy.typing import NDArray

#: Escalar "preguiçoso": número literal ou callable sem argumentos que o produz
#: (tipicamente ``lambda: P["nome"]``, vinculando a dimensão a um parâmetro).
Scalar = Union[int, float, Callable[[], float]]

#: Vetor 3D preguiçoso: sequência de escalares (cada um possivelmente lazy)
#: ou callable que devolve a sequência inteira.
Vec3 = Union[Sequence[float], Sequence[Scalar], Callable[[], Sequence[float]]]

#: Arrays NumPy dos módulos numéricos.
FloatArray = NDArray[np.float64]
Float32Array = NDArray[np.float32]
IntArray = NDArray[np.int32]


def resolve_scalar(x: Scalar) -> float:
    """Resolve um escalar preguiçoso para ``float``."""
    return float(x()) if callable(x) else float(x)


def resolve_vec3(v: Vec3) -> FloatArray:
    """Resolve um vetor 3D preguiçoso para ``ndarray`` float64 de shape (3,)."""
    if callable(v):
        v = v()
    return np.asarray(
        [resolve_scalar(c) if callable(c) else float(c) for c in v],
        dtype=np.float64,
    )
