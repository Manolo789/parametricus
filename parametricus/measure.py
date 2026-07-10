"""
parametricus.measure
====================
Ferramentas de medição e inspeção (Fases 3.2 e 3.3 do roadmap).

Medições:
    distance_point(solid, p)      distância assinada ponto -> sólido
                                  (o SDF *é* a função distância — de graça)
    distance_points(a, b)         distância entre dois pontos
    angle(v1, v2)                 ângulo entre vetores/direções (graus)
    bounding_box(solid | mesh)    caixa envolvente com dimensões

Cortes e seções:
    section(solid, origin, normal)       contornos 2D/3D da seção plana,
                                         com área e perímetro
    slice_field(solid, origin, normal)   campo de distância amostrado no
                                         plano (heatmap p/ inspeção)

Para o corte geométrico 3D use ``solido.cut(normal, offset)`` (sdf.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from skimage import measure as _skmeasure

from .mesher import Mesh
from .sdf import SDF
from .types import FloatArray, Vec3, resolve_vec3


# --------------------------------------------------------------- medições
def distance_point(solid: SDF, point: Sequence[float]) -> float:
    """Distância assinada do ponto à superfície do sólido
    (negativa = ponto interno). Exata: é a própria avaliação do SDF."""
    p = np.asarray(point, dtype=np.float64).reshape(1, 3)
    return float(solid.distance(p)[0])


def distance_points(a: Sequence[float], b: Sequence[float]) -> float:
    """Distância euclidiana entre dois pontos."""
    return float(np.linalg.norm(np.asarray(a, float) - np.asarray(b, float)))


def angle(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Ângulo entre dois vetores/direções, em graus."""
    a = np.asarray(v1, float)
    b = np.asarray(v2, float)
    c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


@dataclass
class BoundingBox:
    min: FloatArray
    max: FloatArray

    @property
    def size(self) -> FloatArray:
        return self.max - self.min

    @property
    def center(self) -> FloatArray:
        return (self.max + self.min) / 2.0

    @property
    def diagonal(self) -> float:
        return float(np.linalg.norm(self.size))

    def report(self) -> str:
        s = self.size
        c = self.center
        return (f"  Bounding box ....... {s[0]:.2f} x {s[1]:.2f} x {s[2]:.2f} mm\n"
                f"  Centro ............. ({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f}) mm\n"
                f"  Diagonal ........... {self.diagonal:.2f} mm")


def bounding_box(obj: Union[SDF, Mesh]) -> BoundingBox:
    """Caixa envolvente de um sólido (bounds da árvore) ou de uma malha
    (justa, pelos vértices)."""
    if isinstance(obj, Mesh):
        bmin, bmax = obj.bounding_box()
    else:
        bmin, bmax = obj.bounds()
    return BoundingBox(np.asarray(bmin, float), np.asarray(bmax, float))


@dataclass
class SolidDistance:
    """Resultado de :func:`distance_solids`."""
    distance: float          # 0.0 se os sólidos se tocam/interpenetram
    point_a: FloatArray      # ponto mais próximo na superfície de A
    point_b: FloatArray      # ponto mais próximo na superfície de B
    intersecting: bool


def _project_to_surface(solid: SDF, p: FloatArray, iters: int = 24,
                        eps: float = 1e-4) -> FloatArray:
    """Projeta ``p`` na superfície do sólido descendo pelo gradiente do SDF."""
    q = p.astype(np.float64).copy()
    for _ in range(iters):
        d = float(solid.distance(q.reshape(1, 3))[0])
        if abs(d) < 1e-9:
            break
        # gradiente numérico central
        offs = np.eye(3) * eps
        pts = np.vstack([q + offs, q - offs])
        vals = solid.distance(pts)
        g = (vals[:3] - vals[3:]) / (2.0 * eps)
        n = np.linalg.norm(g)
        if n < 1e-12:
            break
        q -= d * g / n
    return q


def distance_solids(a: SDF, b: SDF, seed_resolution: int = 24,
                    iters: int = 60) -> SolidDistance:
    """
    Distância mínima entre dois sólidos (Fase 3.2 — otimização sobre os
    dois campos de distância).

    Estratégia: semente por varredura em grade grossa sobre a bbox
    combinada minimizando ``max(dA,0) + max(dB,0)``; refino por projeções
    alternadas nas duas superfícies (cada projeção usa o gradiente do SDF).
    """
    amin, amax = a.bounds()
    bmin, bmax = b.bounds()
    lo = np.minimum(np.asarray(amin, float), np.asarray(bmin, float))
    hi = np.maximum(np.asarray(amax, float), np.asarray(bmax, float))
    axes = [np.linspace(lo[k], hi[k], seed_resolution) for k in range(3)]
    G = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    da = a.distance(G)
    db = b.distance(G)

    # interpenetração: existe ponto interno aos dois campos
    overlap = np.maximum(da, db)
    if float(overlap.min()) < 0.0:
        p = G[int(np.argmin(overlap))]
        return SolidDistance(0.0, p.copy(), p.copy(), intersecting=True)

    cost = np.maximum(da, 0.0) + np.maximum(db, 0.0)
    p = G[int(np.argmin(cost))].astype(np.float64)

    # projeções alternadas A <-> B
    pa = _project_to_surface(a, p)
    pb = _project_to_surface(b, pa)
    for _ in range(iters):
        pa_new = _project_to_surface(a, pb)
        pb_new = _project_to_surface(b, pa_new)
        if (np.linalg.norm(pa_new - pa) < 1e-8
                and np.linalg.norm(pb_new - pb) < 1e-8):
            pa, pb = pa_new, pb_new
            break
        pa, pb = pa_new, pb_new
    return SolidDistance(float(np.linalg.norm(pa - pb)), pa, pb,
                         intersecting=False)


def face_normal_at(mesh: Mesh, point: Sequence[float]) -> FloatArray:
    """
    Normal da face (triângulo) mais próxima do ponto dado — permite medir
    o ângulo entre faces planares da malha: ``angle(face_normal_at(m, p1),
    face_normal_at(m, p2))`` (complemento do item 3.2).
    """
    p = np.asarray(point, dtype=np.float64)
    v = mesh.vertices.astype(np.float64)
    f = mesh.faces
    centroids = (v[f[:, 0]] + v[f[:, 1]] + v[f[:, 2]]) / 3.0
    i = int(np.argmin(((centroids - p) ** 2).sum(axis=1)))
    n = np.cross(v[f[i, 1]] - v[f[i, 0]], v[f[i, 2]] - v[f[i, 0]])
    ln = np.linalg.norm(n)
    return n / ln if ln > 0 else n


# --------------------------------------------------------- cortes / seções
def _plane_basis(normal: FloatArray) -> Tuple[FloatArray, FloatArray]:
    """Base ortonormal (u, v) do plano com a normal dada."""
    n = normal / np.linalg.norm(normal)
    helper = np.array([0.0, 0.0, 1.0])
    if abs(n @ helper) > 0.9:
        helper = np.array([1.0, 0.0, 0.0])
    u = np.cross(n, helper)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v


@dataclass
class Section:
    """Resultado de uma seção plana (Fase 3.3)."""
    origin: FloatArray
    normal: FloatArray
    u: FloatArray                      # base do plano
    v: FloatArray
    contours_2d: List[FloatArray]      # polilinhas (M, 2) em coords do plano
    area: float                        # área da região sólida (mm²)
    perimeter: float                   # comprimento total dos contornos (mm)

    @property
    def contours_3d(self) -> List[FloatArray]:
        """Contornos levados de volta ao espaço 3D do modelo."""
        return [self.origin + c[:, 0:1] * self.u + c[:, 1:2] * self.v
                for c in self.contours_2d]

    def report(self) -> str:
        return (f"  Contornos .......... {len(self.contours_2d)}\n"
                f"  Área da seção ...... {self.area:,.2f} mm²\n"
                f"  Perímetro .......... {self.perimeter:,.2f} mm")


def _plane_grid(solid: SDF, origin: FloatArray, u: FloatArray, v: FloatArray,
                resolution: int, padding: float):
    """Amostra o SDF numa grade 2D sobre o plano; devolve (campo, us, vs)."""
    bmin, bmax = solid.bounds()
    corners = np.array([[x, y, z]
                        for x in (bmin[0], bmax[0])
                        for y in (bmin[1], bmax[1])
                        for z in (bmin[2], bmax[2])]) - origin
    pu = corners @ u
    pv = corners @ v
    lo_u, hi_u = pu.min(), pu.max()
    lo_v, hi_v = pv.min(), pv.max()
    pad = max(hi_u - lo_u, hi_v - lo_v) * padding + 1e-6
    us = np.linspace(lo_u - pad, hi_u + pad, resolution)
    vs = np.linspace(lo_v - pad, hi_v + pad, resolution)
    UU, VV = np.meshgrid(us, vs, indexing="ij")
    pts = origin + UU.reshape(-1, 1) * u + VV.reshape(-1, 1) * v
    fld = solid.distance(pts).reshape(resolution, resolution)
    return fld, us, vs


def section(solid: SDF, origin: Vec3 = (0, 0, 0), normal: Vec3 = (0, 0, 1),
            resolution: int = 256, padding: float = 0.02) -> Section:
    """
    Seção plana do sólido: contornos (marching squares do scikit-image, já
    dependência do projeto), área e perímetro da região cortada.
    """
    o = resolve_vec3(origin)
    n = resolve_vec3(normal)
    n = n / np.linalg.norm(n)
    u, v = _plane_basis(n)
    fld, us, vs = _plane_grid(solid, o, u, v, resolution, padding)

    du = us[1] - us[0]
    dv = vs[1] - vs[0]
    # área por contagem de células internas (robusta a furos/múltiplos loops)
    area = float((fld < 0.0).sum()) * du * dv

    contours: List[FloatArray] = []
    perimeter = 0.0
    if fld.min() < 0.0 < fld.max():
        for c in _skmeasure.find_contours(fld, level=0.0):
            pts = np.column_stack([us[0] + c[:, 0] * du,
                                   vs[0] + c[:, 1] * dv])
            contours.append(pts)
            perimeter += float(np.linalg.norm(np.diff(pts, axis=0),
                                              axis=1).sum())
    return Section(origin=o, normal=n, u=u, v=v, contours_2d=contours,
                   area=area, perimeter=perimeter)


def slice_field(solid: SDF, origin: Vec3 = (0, 0, 0),
                normal: Vec3 = (0, 0, 1), resolution: int = 256,
                padding: float = 0.02):
    """
    Campo de distância amostrado no plano (Fase 3.3 — "Slice"): ótimo para
    inspecionar filetes, cascas e espessuras.

    Retorna ``(field, extent)`` prontos para
    ``plt.imshow(field.T, origin="lower", extent=extent)`` com
    ``plt.contour(..., levels=[0])`` para a silhueta.
    """
    o = resolve_vec3(origin)
    n = resolve_vec3(normal)
    n = n / np.linalg.norm(n)
    u, v = _plane_basis(n)
    fld, us, vs = _plane_grid(solid, o, u, v, resolution, padding)
    extent = (float(us[0]), float(us[-1]), float(vs[0]), float(vs[-1]))
    return fld, extent
