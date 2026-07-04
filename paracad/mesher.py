"""
paracad.mesher
==============
Converte a geometria implícita (SDF) em malha triangular via
Marching Cubes (scikit-image) e exporta para STL binário / OBJ.
Também calcula propriedades de massa (volume, área, centroide).
"""

from __future__ import annotations

import struct
import numpy as np
from dataclasses import dataclass
from typing import Tuple

from skimage import measure

from .sdf import SDF


@dataclass
class Mesh:
    vertices: np.ndarray   # (V, 3) float
    faces: np.ndarray      # (F, 3) int
    normals: np.ndarray    # (V, 3) float

    # ------------------------------------------------- propriedades de massa
    def volume(self) -> float:
        """Volume via teorema da divergência (malha fechada)."""
        v = self.vertices
        f = self.faces
        p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        return float(np.abs(np.einsum("ij,ij->i", p0, np.cross(p1, p2)).sum()) / 6.0)

    def surface_area(self) -> float:
        v = self.vertices
        f = self.faces
        p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        return float(np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1).sum() / 2.0)

    def centroid(self) -> np.ndarray:
        v = self.vertices
        f = self.faces
        p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        vol6 = np.einsum("ij,ij->i", p0, np.cross(p1, p2))
        c = (p0 + p1 + p2) / 4.0
        total = vol6.sum()
        if abs(total) < 1e-12:
            return v.mean(axis=0)
        return (c * vol6[:, None]).sum(axis=0) / total

    def bounding_box(self) -> Tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    # ------------------------------------------------------------ exportação
    def save_stl(self, path: str, name: bytes = b"paracad") -> None:
        """STL binário — formato padrão para impressão 3D e CAM."""
        v, f = self.vertices, self.faces
        p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        n = np.cross(p1 - p0, p2 - p0)
        lens = np.linalg.norm(n, axis=1, keepdims=True)
        lens[lens == 0] = 1.0
        n = n / lens
        with open(path, "wb") as fh:
            header = name.ljust(80, b"\0")[:80]
            fh.write(header)
            fh.write(struct.pack("<I", len(f)))
            data = np.zeros(len(f), dtype=[
                ("normal", "<3f4"), ("v0", "<3f4"),
                ("v1", "<3f4"), ("v2", "<3f4"), ("attr", "<u2"),
            ])
            data["normal"], data["v0"], data["v1"], data["v2"] = n, p0, p1, p2
            fh.write(data.tobytes())

    def save_obj(self, path: str) -> None:
        """Wavefront OBJ — legível e amplamente suportado."""
        with open(path, "w") as fh:
            fh.write("# gerado por paracad\n")
            for v in self.vertices:
                fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            for n in self.normals:
                fh.write(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
            for a, b, c in self.faces + 1:
                fh.write(f"f {a}//{a} {b}//{b} {c}//{c}\n")

    def report(self) -> str:
        bmin, bmax = self.bounding_box()
        size = bmax - bmin
        cx, cy, cz = self.centroid()
        return (
            f"  Triângulos ......... {len(self.faces):,}\n"
            f"  Vértices ........... {len(self.vertices):,}\n"
            f"  Volume ............. {self.volume():,.2f} mm³\n"
            f"  Área de superfície . {self.surface_area():,.2f} mm²\n"
            f"  Dimensões (XYZ) .... {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm\n"
            f"  Centroide .......... ({cx:.2f}, {cy:.2f}, {cz:.2f}) mm"
        )


def generate_mesh(solid: SDF, resolution: int = 96, padding: float = 0.05) -> Mesh:
    """
    Gera a malha de um sólido SDF por Marching Cubes.

    resolution: nº de amostras no maior eixo da caixa envolvente.
                64 = rascunho rápido; 128 = boa qualidade; 256 = alta.
    padding:    margem relativa adicionada à caixa envolvente.
    """
    bmin, bmax = solid.bounds()
    bmin, bmax = np.asarray(bmin, float), np.asarray(bmax, float)
    size = bmax - bmin
    pad = size.max() * padding + 1e-6
    bmin, bmax = bmin - pad, bmax + pad
    size = bmax - bmin

    spacing = size.max() / resolution
    counts = np.maximum(np.ceil(size / spacing).astype(int) + 1, 2)

    xs = np.linspace(bmin[0], bmax[0], counts[0])
    ys = np.linspace(bmin[1], bmax[1], counts[1])
    zs = np.linspace(bmin[2], bmax[2], counts[2])
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)

    # avalia em blocos para limitar uso de memória
    n = len(pts)
    dist = np.empty(n, dtype=np.float64)
    block = 500_000
    for i in range(0, n, block):
        dist[i:i + block] = solid.distance(pts[i:i + block])
    field = dist.reshape(counts)

    if field.min() > 0 or field.max() < 0:
        raise ValueError(
            "A superfície não cruza o volume amostrado — "
            "verifique dimensões/parâmetros do modelo."
        )

    dx = [(xs[-1] - xs[0]) / (counts[0] - 1),
          (ys[-1] - ys[0]) / (counts[1] - 1),
          (zs[-1] - zs[0]) / (counts[2] - 1)]
    verts, faces, normals, _ = measure.marching_cubes(field, level=0.0, spacing=dx)
    verts = verts + bmin  # volta ao referencial global
    return Mesh(vertices=verts, faces=faces, normals=normals)
