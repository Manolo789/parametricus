"""
paracad.sdf
===========
Núcleo geométrico baseado em Campos de Distância Assinada (SDF).

Cada sólido é uma função f(p) -> distância, negativa dentro do sólido e
positiva fora. Isso torna operações booleanas, filetes, chanfros e cascas
triviais e numericamente robustas — ideal para modelagem paramétrica,
pois toda a árvore de construção é reavaliada a cada mudança de parâmetro.

Todas as dimensões são avaliadas de forma "preguiçosa": em vez de números,
os nós aceitam callables sem argumento (lambdas), permitindo vincular
parâmetros do ParameterSet diretamente à geometria.
"""

from __future__ import annotations

import numpy as np
from typing import Callable, List, Sequence, Tuple, Union

Scalar = Union[int, float, Callable[[], float]]
Vec3 = Union[Sequence[float], Callable[[], Sequence[float]]]


def _val(x: Scalar) -> float:
    """Resolve escalar preguiçoso."""
    return float(x()) if callable(x) else float(x)


def _vec(v: Vec3) -> np.ndarray:
    if callable(v):
        v = v()
    return np.asarray([_val(c) if callable(c) else c for c in v],
                      dtype=np.float64)


# ============================================================== classe base
class SDF:
    """Nó base da árvore de construção geométrica (CSG)."""

    name: str = "SDF"

    def distance(self, p: np.ndarray) -> np.ndarray:
        """p: array (N, 3) -> distâncias (N,)."""
        raise NotImplementedError

    def bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Caixa envolvente aproximada (min, max) — usada pelo mesher."""
        raise NotImplementedError

    # -------------------------------------------------- operadores Python
    def __or__(self, other: "SDF") -> "SDF":           # a | b  -> união
        return Union_(self, other)

    def __and__(self, other: "SDF") -> "SDF":          # a & b  -> interseção
        return Intersection(self, other)

    def __sub__(self, other: "SDF") -> "SDF":          # a - b  -> subtração
        return Difference(self, other)

    # -------------------------------------------------- transformações
    def translate(self, offset: Vec3) -> "SDF":
        return Translate(self, offset)

    def rotate(self, axis: Vec3, angle_deg: Scalar) -> "SDF":
        return Rotate(self, axis, angle_deg)

    def scale(self, factor: Scalar) -> "SDF":
        return Scale(self, factor)

    def mirror(self, normal: Vec3) -> "SDF":
        return Mirror(self, normal)

    # -------------------------------------------------- operações de eng.
    def shell(self, thickness: Scalar) -> "SDF":
        """Casca oca com espessura de parede dada."""
        return Shell(self, thickness)

    def fillet_union(self, other: "SDF", radius: Scalar) -> "SDF":
        """União com filete (blend suave) de raio dado."""
        return SmoothUnion(self, other, radius)

    def fillet_difference(self, other: "SDF", radius: Scalar) -> "SDF":
        """Subtração com filete côncavo."""
        return SmoothDifference(self, other, radius)

    def round(self, radius: Scalar) -> "SDF":
        """Arredonda todas as arestas (offset externo)."""
        return Round(self, radius)

    def array_linear(self, count: int, step: Vec3) -> "SDF":
        """Padrão linear: `count` cópias espaçadas por `step`."""
        result: SDF = self
        for i in range(1, count):
            k = i
            result = result | Translate(self, lambda k=k, s=step: _vec(s) * k)
        return result

    def array_polar(self, count: int, axis: Vec3 = (0, 0, 1)) -> "SDF":
        """Padrão polar: `count` cópias distribuídas em 360° ao redor do eixo."""
        result: SDF = self
        for i in range(1, count):
            ang = 360.0 * i / count
            result = result | Rotate(self, axis, ang)
        return result


# ================================================================ primitivas
class Sphere(SDF):
    name = "Esfera"

    def __init__(self, radius: Scalar):
        self.radius = radius

    def distance(self, p):
        return np.linalg.norm(p, axis=1) - _val(self.radius)

    def bounds(self):
        r = _val(self.radius)
        return np.array([-r] * 3), np.array([r] * 3)


class Box(SDF):
    """Paralelepípedo centrado na origem com dimensões (dx, dy, dz)."""
    name = "Caixa"

    def __init__(self, size: Vec3):
        self.size = size

    def distance(self, p):
        half = _vec(self.size) / 2.0
        q = np.abs(p) - half
        outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
        inside = np.minimum(np.max(q, axis=1), 0.0)
        return outside + inside

    def bounds(self):
        half = _vec(self.size) / 2.0
        return -half, half


class Cylinder(SDF):
    """Cilindro ao longo do eixo Z, centrado na origem."""
    name = "Cilindro"

    def __init__(self, radius: Scalar, height: Scalar):
        self.radius, self.height = radius, height

    def distance(self, p):
        r, h = _val(self.radius), _val(self.height) / 2.0
        d_r = np.linalg.norm(p[:, :2], axis=1) - r
        d_z = np.abs(p[:, 2]) - h
        d = np.stack([d_r, d_z], axis=1)
        outside = np.linalg.norm(np.maximum(d, 0.0), axis=1)
        inside = np.minimum(np.max(d, axis=1), 0.0)
        return outside + inside

    def bounds(self):
        r, h = _val(self.radius), _val(self.height) / 2.0
        return np.array([-r, -r, -h]), np.array([r, r, h])


class Cone(SDF):
    """Cone (ou tronco de cone) ao longo do eixo Z, base em z=-h/2."""
    name = "Cone"

    def __init__(self, radius_bottom: Scalar, radius_top: Scalar, height: Scalar):
        self.r1, self.r2, self.height = radius_bottom, radius_top, height

    def distance(self, p):
        r1, r2 = _val(self.r1), _val(self.r2)
        h = _val(self.height) / 2.0  # meia-altura
        # distância exata para cone truncado (Quilez, sdCappedCone)
        q = np.stack([np.linalg.norm(p[:, :2], axis=1), p[:, 2]], axis=1)
        k1 = np.array([r2, h])
        k2 = np.array([r2 - r1, 2.0 * h])
        ca_x = q[:, 0] - np.minimum(q[:, 0], np.where(q[:, 1] < 0.0, r1, r2))
        ca_y = np.abs(q[:, 1]) - h
        ca = np.stack([ca_x, ca_y], axis=1)
        t = np.clip(((k1 - q) @ k2) / np.dot(k2, k2), 0.0, 1.0)
        cb = q - k1 + np.outer(t, k2)
        s = np.where((cb[:, 0] < 0.0) & (ca[:, 1] < 0.0), -1.0, 1.0)
        d = np.minimum(np.sum(ca * ca, axis=1), np.sum(cb * cb, axis=1))
        return s * np.sqrt(d)

    def bounds(self):
        r = max(_val(self.r1), _val(self.r2))
        h = _val(self.height) / 2.0
        return np.array([-r, -r, -h]), np.array([r, r, h])


class Torus(SDF):
    """Toro no plano XY: raio maior R, raio do tubo r."""
    name = "Toro"

    def __init__(self, radius_major: Scalar, radius_minor: Scalar):
        self.R, self.r = radius_major, radius_minor

    def distance(self, p):
        R, r = _val(self.R), _val(self.r)
        q = np.stack([np.linalg.norm(p[:, :2], axis=1) - R, p[:, 2]], axis=1)
        return np.linalg.norm(q, axis=1) - r

    def bounds(self):
        R, r = _val(self.R), _val(self.r)
        m = R + r
        return np.array([-m, -m, -r]), np.array([m, m, r])


class Capsule(SDF):
    """Cápsula entre os pontos a e b com raio r."""
    name = "Cápsula"

    def __init__(self, a: Vec3, b: Vec3, radius: Scalar):
        self.a, self.b, self.radius = a, b, radius

    def distance(self, p):
        a, b, r = _vec(self.a), _vec(self.b), _val(self.radius)
        pa, ba = p - a, b - a
        h = np.clip(pa @ ba / (ba @ ba), 0.0, 1.0)
        return np.linalg.norm(pa - np.outer(h, ba), axis=1) - r

    def bounds(self):
        a, b, r = _vec(self.a), _vec(self.b), _val(self.radius)
        return np.minimum(a, b) - r, np.maximum(a, b) + r


# ============================================== recursos baseados em esboço
class Extrude(SDF):
    """Extrusão linear de um perfil 2D (paracad.sketch.Profile) em Z."""
    name = "Extrusão"

    def __init__(self, profile, height: Scalar):
        self.profile, self.height = profile, height

    def distance(self, p):
        h = _val(self.height) / 2.0
        d2 = self.profile.distance(p[:, :2])
        dz = np.abs(p[:, 2]) - h
        d = np.stack([d2, dz], axis=1)
        outside = np.linalg.norm(np.maximum(d, 0.0), axis=1)
        inside = np.minimum(np.max(d, axis=1), 0.0)
        return outside + inside

    def bounds(self):
        (xmin, ymin), (xmax, ymax) = self.profile.bounds()
        h = _val(self.height) / 2.0
        return np.array([xmin, ymin, -h]), np.array([xmax, ymax, h])


class Revolve(SDF):
    """
    Revolução de um perfil 2D ao redor do eixo Z.
    O perfil vive no plano (r, z): x do esboço = distância radial.
    """
    name = "Revolução"

    def __init__(self, profile):
        self.profile = profile

    def distance(self, p):
        rq = np.stack([np.linalg.norm(p[:, :2], axis=1), p[:, 2]], axis=1)
        return self.profile.distance(rq)

    def bounds(self):
        (rmin, zmin), (rmax, zmax) = self.profile.bounds()
        return np.array([-rmax, -rmax, zmin]), np.array([rmax, rmax, zmax])


# ================================================================= booleanas
class _Binary(SDF):
    def __init__(self, a: SDF, b: SDF):
        self.a, self.b = a, b

    def bounds(self):
        amin, amax = self.a.bounds()
        bmin, bmax = self.b.bounds()
        return np.minimum(amin, bmin), np.maximum(amax, bmax)


class Union_(_Binary):
    name = "União"

    def distance(self, p):
        return np.minimum(self.a.distance(p), self.b.distance(p))


class Intersection(_Binary):
    name = "Interseção"

    def distance(self, p):
        return np.maximum(self.a.distance(p), self.b.distance(p))

    def bounds(self):
        amin, amax = self.a.bounds()
        bmin, bmax = self.b.bounds()
        return np.maximum(amin, bmin), np.minimum(amax, bmax)


class Difference(_Binary):
    name = "Subtração"

    def distance(self, p):
        return np.maximum(self.a.distance(p), -self.b.distance(p))

    def bounds(self):
        return self.a.bounds()


class SmoothUnion(_Binary):
    """União com filete suave (blend polinomial de raio k)."""
    name = "União com filete"

    def __init__(self, a: SDF, b: SDF, k: Scalar):
        super().__init__(a, b)
        self.k = k

    def distance(self, p):
        k = max(_val(self.k), 1e-9)
        d1, d2 = self.a.distance(p), self.b.distance(p)
        h = np.clip(0.5 + 0.5 * (d2 - d1) / k, 0.0, 1.0)
        return d2 + (d1 - d2) * h - k * h * (1.0 - h)

    def bounds(self):
        amin, amax = super().bounds()
        k = _val(self.k)
        return amin - k, amax + k


class SmoothDifference(_Binary):
    """Subtração com filete côncavo de raio k."""
    name = "Subtração com filete"

    def __init__(self, a: SDF, b: SDF, k: Scalar):
        super().__init__(a, b)
        self.k = k

    def distance(self, p):
        k = max(_val(self.k), 1e-9)
        d1, d2 = self.a.distance(p), -self.b.distance(p)
        h = np.clip(0.5 - 0.5 * (d2 - d1) / k, 0.0, 1.0)
        return d2 + (d1 - d2) * h + k * h * (1.0 - h)

    def bounds(self):
        return self.a.bounds()


# ============================================================ transformações
class Translate(SDF):
    name = "Translação"

    def __init__(self, child: SDF, offset: Vec3):
        self.child, self.offset = child, offset

    def distance(self, p):
        return self.child.distance(p - _vec(self.offset))

    def bounds(self):
        cmin, cmax = self.child.bounds()
        o = _vec(self.offset)
        return cmin + o, cmax + o


class Rotate(SDF):
    name = "Rotação"

    def __init__(self, child: SDF, axis: Vec3, angle_deg: Scalar):
        self.child, self.axis, self.angle = child, axis, angle_deg

    def _matrix(self) -> np.ndarray:
        axis = _vec(self.axis)
        axis = axis / np.linalg.norm(axis)
        t = np.radians(_val(self.angle))
        c, s = np.cos(t), np.sin(t)
        x, y, z = axis
        return np.array([
            [c + x*x*(1-c),   x*y*(1-c) - z*s, x*z*(1-c) + y*s],
            [y*x*(1-c) + z*s, c + y*y*(1-c),   y*z*(1-c) - x*s],
            [z*x*(1-c) - y*s, z*y*(1-c) + x*s, c + z*z*(1-c)],
        ])

    def distance(self, p):
        R = self._matrix()
        return self.child.distance(p @ R)  # p @ R == R^T aplicado (inversa)

    def bounds(self):
        cmin, cmax = self.child.bounds()
        corners = np.array([[x, y, z] for x in (cmin[0], cmax[0])
                            for y in (cmin[1], cmax[1])
                            for z in (cmin[2], cmax[2])])
        rc = corners @ self._matrix().T
        return rc.min(axis=0), rc.max(axis=0)


class Scale(SDF):
    name = "Escala"

    def __init__(self, child: SDF, factor: Scalar):
        self.child, self.factor = child, factor

    def distance(self, p):
        f = _val(self.factor)
        return self.child.distance(p / f) * f

    def bounds(self):
        cmin, cmax = self.child.bounds()
        f = _val(self.factor)
        return cmin * f, cmax * f


class Mirror(SDF):
    """Espelha o sólido em relação ao plano pela origem com a normal dada,
    mantendo também o original (simetria)."""
    name = "Espelho"

    def __init__(self, child: SDF, normal: Vec3):
        self.child, self.normal = child, normal

    def distance(self, p):
        n = _vec(self.normal)
        n = n / np.linalg.norm(n)
        refl = p - 2.0 * np.outer(p @ n, n)
        return np.minimum(self.child.distance(p), self.child.distance(refl))

    def bounds(self):
        cmin, cmax = self.child.bounds()
        n = _vec(self.normal)
        n = n / np.linalg.norm(n)
        corners = np.array([[x, y, z] for x in (cmin[0], cmax[0])
                            for y in (cmin[1], cmax[1])
                            for z in (cmin[2], cmax[2])])
        refl = corners - 2.0 * np.outer(corners @ n, n)
        allc = np.vstack([corners, refl])
        return allc.min(axis=0), allc.max(axis=0)


# ==================================================== operações de engenharia
class Shell(SDF):
    name = "Casca"

    def __init__(self, child: SDF, thickness: Scalar):
        self.child, self.thickness = child, thickness

    def distance(self, p):
        t = _val(self.thickness)
        return np.abs(self.child.distance(p)) - t / 2.0

    def bounds(self):
        cmin, cmax = self.child.bounds()
        t = _val(self.thickness) / 2.0
        return cmin - t, cmax + t


class Round(SDF):
    name = "Arredondamento"

    def __init__(self, child: SDF, radius: Scalar):
        self.child, self.radius = child, radius

    def distance(self, p):
        return self.child.distance(p) - _val(self.radius)

    def bounds(self):
        cmin, cmax = self.child.bounds()
        r = _val(self.radius)
        return cmin - r, cmax + r
