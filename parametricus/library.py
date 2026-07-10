"""
parametricus.library
====================
Biblioteca de componentes padronizados (item de longo prazo do roadmap):
fábricas parametrizadas que devolvem nós ``SDF`` prontos para composição
ou documentos completos.

    from parametricus.library import nut, washer, hex_bolt

    porca = nut("M8")                        # SDF pronto
    doc   = nut_document("M8")               # Document com parâmetros

Roscas: o nó :class:`HelicalThread` implementa o SDF helicoidal citado no
roadmap (deslocamento radial triangular ~perfil métrico ISO). Por padrão as
fábricas geram furos/hastes lisos (mais rápidos de malhar); use
``threaded=True`` para a rosca real (exige resolução de malha maior).
"""

from __future__ import annotations

import numpy as np

from .document import Document
from .sdf import SDF, Cylinder, Extrude
from .sketch import RegularPolygonProfile
from .types import Scalar, resolve_scalar as _val

# Dimensões nominais ISO (rosca métrica grossa) — mm
# (passo, largura entre faces da porca s, altura da porca m,
#  diâmetro da arruela D, espessura da arruela h, diâmetro da cabeça s_cab,
#  altura da cabeça k)
_ISO: dict = {
    "M3":  dict(pitch=0.5,  s=5.5,  m=2.4,  wD=7.0,  wh=0.5, k=2.0),
    "M4":  dict(pitch=0.7,  s=7.0,  m=3.2,  wD=9.0,  wh=0.8, k=2.8),
    "M5":  dict(pitch=0.8,  s=8.0,  m=4.7,  wD=10.0, wh=1.0, k=3.5),
    "M6":  dict(pitch=1.0,  s=10.0, m=5.2,  wD=12.0, wh=1.6, k=4.0),
    "M8":  dict(pitch=1.25, s=13.0, m=6.8,  wD=16.0, wh=1.6, k=5.3),
    "M10": dict(pitch=1.5,  s=16.0, m=8.4,  wD=20.0, wh=2.0, k=6.4),
    "M12": dict(pitch=1.75, s=18.0, m=10.8, wD=24.0, wh=2.5, k=7.5),
}


def _size(size: str) -> tuple:
    if size not in _ISO:
        raise KeyError(f"Tamanho não catalogado: {size!r} "
                       f"(disponíveis: {', '.join(sorted(_ISO))})")
    d = float(size[1:])
    return d, _ISO[size]


class HelicalThread(SDF):
    """
    Rosca helicoidal (nó de SDF citado no roadmap para roscas reais).

    Haste cilíndrica de raio nominal ``r`` com deslocamento radial
    triangular de amplitude ``depth`` seguindo a hélice de passo ``pitch``:
    ``r_eff(θ, z) = r - depth * tri(z/pitch - θ/2π)``. Para rosca interna
    (furo de porca), subtraia este nó do sólido.

    Aproximação: o deslocamento quebra levemente a propriedade de
    Lipschitz do campo; o fator ``lipschitz`` reescala a distância para
    manter o marching cubes correto.
    """

    name = "RoscaHelicoidal"

    def __init__(self, radius: Scalar, height: Scalar, pitch: Scalar,
                 depth: Scalar | None = None, internal: bool = False):
        self.radius, self.height, self.pitch = radius, height, pitch
        self.depth = depth
        self.internal = internal

    def _dims(self):
        r = _val(self.radius)
        h = _val(self.height)
        p = _val(self.pitch)
        d = _val(self.depth) if self.depth is not None else 0.61 * p
        return r, h, p, d

    def distance(self, p: np.ndarray) -> np.ndarray:
        r, h, pitch, depth = self._dims()
        rad = np.linalg.norm(p[:, :2], axis=1)
        theta = np.arctan2(p[:, 1], p[:, 0]) / (2.0 * np.pi)
        phase = (p[:, 2] / pitch - theta) % 1.0
        tri = np.abs(2.0 * phase - 1.0)              # 0..1 triangular
        sgn = 1.0 if self.internal else -1.0
        r_eff = r + sgn * depth * (tri - 0.5)
        d_rad = rad - r_eff
        d_z = np.abs(p[:, 2]) - h / 2.0
        d2 = np.stack([d_rad, d_z], axis=1)
        outside = np.linalg.norm(np.maximum(d2, 0.0), axis=1)
        inside = np.minimum(np.max(d2, axis=1), 0.0)
        # reescala Lipschitz: |∇r_eff| ≤ 1 + 2*depth*sqrt(1/p² + 1/r²)
        lip = 1.0 + 2.0 * depth * np.sqrt(1.0 / pitch ** 2
                                          + 1.0 / max(r - depth, 1e-6) ** 2)
        return (outside + inside) / lip

    def bounds(self):
        r, h, _, depth = self._dims()
        R = r + depth
        return (np.array([-R, -R, -h / 2.0]),
                np.array([R, R, h / 2.0]))


def washer(size: str = "M8", thickness: Scalar | None = None) -> SDF:
    """Arruela plana ISO 7089 (aproximada) para o tamanho dado."""
    d, t = _size(size)
    th = thickness if thickness is not None else t["wh"]
    outer = Cylinder(t["wD"] / 2.0, th)
    hole = Cylinder((d + 0.3) / 2.0, float(_val(th)) * 4.0)
    return outer - hole


def nut(size: str = "M8", threaded: bool = False) -> SDF:
    """
    Porca sextavada ISO 4032 (aproximada). ``threaded=True`` gera a rosca
    interna real via :class:`HelicalThread` (malhar com resolução alta).
    """
    d, t = _size(size)
    s = t["s"]                       # largura entre faces
    m = t["m"]                       # altura
    circum = s / np.cos(np.pi / 6.0) / 2.0   # raio circunscrito do hexágono
    hexagon = Extrude(RegularPolygonProfile(6, circum), m)
    # chanfros cônicos das faces superior/inferior (aproximados por corte)
    body = hexagon & Cylinder(circum * 0.98, m * 1.01)
    if threaded:
        hole = HelicalThread((d - 0.61 * t["pitch"]) / 2.0 + 0.61 * t["pitch"],
                             m * 1.2, t["pitch"], internal=True)
    else:
        hole = Cylinder(d / 2.0 * 0.85, m * 1.2)   # furo no diâmetro menor
    return body - hole


def hex_bolt(size: str = "M8", length: Scalar = 30.0,
             threaded: bool = False) -> SDF:
    """
    Parafuso sextavado ISO 4017 (aproximado): cabeça hexagonal + haste.
    A haste fica ao longo de -Z a partir da base da cabeça.
    """
    d, t = _size(size)
    L = _val(length)
    k = t["k"]
    circum = t["s"] / np.cos(np.pi / 6.0) / 2.0
    head = Extrude(RegularPolygonProfile(6, circum), k).translate(
        (0, 0, k / 2.0))
    if threaded:
        shank: SDF = HelicalThread(d / 2.0, L, t["pitch"]).translate(
            (0, 0, -L / 2.0))
    else:
        shank = Cylinder(d / 2.0, L).translate((0, 0, -L / 2.0))
    return head | shank


def nut_document(size: str = "M8", threaded: bool = False) -> Document:
    """Porca como :class:`Document` editável (parâmetros expostos)."""
    d, t = _size(size)
    doc = Document(f"Porca {size}")
    P = doc.params
    P.define("d", d, description="diâmetro nominal")
    P.define("s", t["s"], description="largura entre faces")
    P.define("m", t["m"], description="altura")
    P.define("pitch", t["pitch"], description="passo da rosca")

    def build(P):
        circum = P["s"] / np.cos(np.pi / 6.0) / 2.0
        body = (Extrude(RegularPolygonProfile(6, lambda: P["s"]
                        / np.cos(np.pi / 6.0) / 2.0), lambda: P["m"])
                & Cylinder(circum * 0.98, P["m"] * 1.01))
        if threaded:
            hole: SDF = HelicalThread(
                lambda: P["d"] / 2.0, lambda: P["m"] * 1.2,
                lambda: P["pitch"], internal=True)
        else:
            hole = Cylinder(lambda: P["d"] / 2.0 * 0.85,
                            lambda: P["m"] * 1.2)
        return body - hole

    doc.add_feature("Porca", build, description=f"sextavada {size}")
    return doc
