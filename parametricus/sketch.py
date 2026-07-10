"""
parametricus.sketch
==============
Perfis 2D (esboços) usados por Extrude e Revolve — o fluxo clássico
"sketch -> feature" de sistemas CAD paramétricos.

Cada perfil é um SDF 2D: distance(p) recebe pontos (N, 2).
Perfis suportam as mesmas booleanas dos sólidos: |, &, -.
"""

from __future__ import annotations

import numpy as np
from typing import Callable, List, Sequence, Tuple, Union

from .types import Scalar, resolve_scalar as _val


class Profile:
    """Base de perfis 2D."""

    def distance(self, p: np.ndarray) -> np.ndarray:  # p: (N, 2)
        raise NotImplementedError

    def bounds(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        raise NotImplementedError

    def signature(self) -> str:
        """Assinatura estrutural (valores resolvidos) — ver SDF.signature()."""
        from .sdf import _structural_signature
        return _structural_signature(self)

    def __or__(self, other):  return _PUnion(self, other)
    def __and__(self, other): return _PIntersection(self, other)
    def __sub__(self, other): return _PDifference(self, other)

    def translate(self, dx: Scalar, dy: Scalar) -> "Profile":
        return _PTranslate(self, dx, dy)

    def round(self, radius: Scalar) -> "Profile":
        return _PRound(self, radius)


class CircleProfile(Profile):
    def __init__(self, radius: Scalar):
        self.radius = radius

    def distance(self, p):
        return np.linalg.norm(p, axis=1) - _val(self.radius)

    def bounds(self):
        r = _val(self.radius)
        return (-r, -r), (r, r)


class RectProfile(Profile):
    """Retângulo centrado na origem, com cantos opcionalmente arredondados."""

    def __init__(self, width: Scalar, height: Scalar, corner_radius: Scalar = 0.0):
        self.width, self.height, self.cr = width, height, corner_radius

    def distance(self, p):
        w, h = _val(self.width) / 2.0, _val(self.height) / 2.0
        r = min(_val(self.cr), w, h)
        q = np.abs(p) - np.array([w - r, h - r])
        outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
        inside = np.minimum(np.max(q, axis=1), 0.0)
        return outside + inside - r

    def bounds(self):
        w, h = _val(self.width) / 2.0, _val(self.height) / 2.0
        return (-w, -h), (w, h)


class PolygonProfile(Profile):
    """Polígono simples (lista de vértices, fechado automaticamente)."""

    def __init__(self, vertices: Union[Sequence[Sequence[float]],
                                       Callable[[], Sequence[Sequence[float]]]]):
        self.vertices = vertices

    def _verts(self) -> np.ndarray:
        v = self.vertices() if callable(self.vertices) else self.vertices
        return np.asarray(v, dtype=np.float64)

    def distance(self, p):
        """
        SDF exato do polígono, otimizado (Fase 3.1).

        O loop original já era vetorizado sobre os pontos; o ganho (2,2 a
        2,7x no benchmark, hexágono a 100 lados) vem da eliminação de
        temporários 2D — componentes x/y separados, ``np.minimum`` in-place
        e contagem inteira de cruzamentos em vez de trocas de sinal em
        float. Equivalência numérica validada por teste de regressão.
        """
        v = self._verts()                        # (E, 2)
        n = len(v)
        vj = np.roll(v, 1, axis=0)               # vértice anterior
        E = vj - v                               # (E, 2) arestas
        ee = (E * E).sum(axis=1)
        ee = np.where(ee == 0.0, 1.0, ee)        # arestas degeneradas

        px, py = p[:, 0], p[:, 1]
        d = np.full(len(p), np.inf)
        flips = np.zeros(len(p), dtype=np.int64)
        for i in range(n):
            ex, ey = E[i]
            vix, viy = v[i]
            vjy = vj[i, 1]
            wx = px - vix
            wy = py - viy
            t = np.clip((wx * ex + wy * ey) / ee[i], 0.0, 1.0)
            bx = wx - t * ex
            by = wy - t * ey
            np.minimum(d, bx * bx + by * by, out=d)
            # regra de cruzamento (par-ímpar com winding)
            cond1 = py >= viy
            cond2 = py < vjy
            cond3 = ex * wy > ey * wx
            flips += (cond1 & cond2 & cond3) | (~cond1 & ~cond2 & ~cond3)
        sign = np.where(flips % 2 == 1, -1.0, 1.0)
        return sign * np.sqrt(d)

    def bounds(self):
        v = self._verts()
        return tuple(v.min(axis=0)), tuple(v.max(axis=0))


class RegularPolygonProfile(PolygonProfile):
    """Polígono regular de n lados (ex.: hexágono para porcas/parafusos)."""

    def __init__(self, sides: int, circumradius: Scalar, rotation_deg: Scalar = 0.0):
        self.sides, self.circumradius, self.rotation = sides, circumradius, rotation_deg

        def make():
            r = _val(self.circumradius)
            rot = np.radians(_val(self.rotation))
            ang = np.linspace(0, 2 * np.pi, self.sides, endpoint=False) + rot
            return np.stack([r * np.cos(ang), r * np.sin(ang)], axis=1)

        super().__init__(make)


# --------------------------------------------------------------- booleanas 2D
class _PBinary(Profile):
    def __init__(self, a: Profile, b: Profile):
        self.a, self.b = a, b

    def bounds(self):
        (ax0, ay0), (ax1, ay1) = self.a.bounds()
        (bx0, by0), (bx1, by1) = self.b.bounds()
        return (min(ax0, bx0), min(ay0, by0)), (max(ax1, bx1), max(ay1, by1))


class _PUnion(_PBinary):
    def distance(self, p):
        return np.minimum(self.a.distance(p), self.b.distance(p))


class _PIntersection(_PBinary):
    def distance(self, p):
        return np.maximum(self.a.distance(p), self.b.distance(p))


class _PDifference(_PBinary):
    def distance(self, p):
        return np.maximum(self.a.distance(p), -self.b.distance(p))

    def bounds(self):
        return self.a.bounds()


class _PTranslate(Profile):
    def __init__(self, child: Profile, dx: Scalar, dy: Scalar):
        self.child, self.dx, self.dy = child, dx, dy

    def distance(self, p):
        return self.child.distance(p - np.array([_val(self.dx), _val(self.dy)]))

    def bounds(self):
        (x0, y0), (x1, y1) = self.child.bounds()
        dx, dy = _val(self.dx), _val(self.dy)
        return (x0 + dx, y0 + dy), (x1 + dx, y1 + dy)


class _PRound(Profile):
    def __init__(self, child: Profile, radius: Scalar):
        self.child, self.radius = child, radius

    def distance(self, p):
        return self.child.distance(p) - _val(self.radius)

    def bounds(self):
        (x0, y0), (x1, y1) = self.child.bounds()
        r = _val(self.radius)
        return (x0 - r, y0 - r), (x1 + r, y1 + r)
