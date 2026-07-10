"""
parametricus.mesher
==============
Conversão da geometria implícita (SDF) em malha triangular, com
propriedades de massa (volume, área, centroide) e exportação STL binário / OBJ.

Arquitetura
-----------
- ``Mesh`` — contêiner da malha pronta (vértices/faces/normais) com
  propriedades de massa e exportação. Não conhece amostragem nem
  visualização: o viewer apenas recebe um ``Mesh``.
- ``MeshGenerator`` — interface (padrão Strategy) dos algoritmos de
  geração de malha.
- ``MarchingCubesGenerator`` — implementação padrão: grade uniforme
  avaliada em blocos (chunks) + Marching Cubes. A grade de pontos nunca
  é materializada por inteiro; o único array do tamanho do domínio é o
  campo escalar em float32.
- ``generate_mesh()`` — fachada pública estável. Algoritmos futuros
  (ex.: malha adaptativa por octree) implementam ``MeshGenerator`` e são
  injetados pelo parâmetro ``generator``, sem mudanças nos demais módulos.
"""

from __future__ import annotations

import struct
import time
from abc import ABC, abstractmethod
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple

from skimage import measure

from . import sdf as _sdf
from .sdf import SDF
from ._log import logger


# ============================================================== estatísticas
@dataclass
class MeshStats:
    """Estatísticas de uma geração de malha."""
    generator: str
    grid_shape: Tuple[int, int, int]
    voxels: int                 # nº de amostras do SDF avaliadas
    n_vertices: int
    n_triangles: int
    sample_time_s: float        # amostragem do campo (avaliação dos SDFs)
    extract_time_s: float       # extração da superfície (Marching Cubes)
    total_time_s: float
    peak_memory_mb: float       # estimativa do pico durante a geração

    def report(self) -> str:
        nx, ny, nz = self.grid_shape
        return (
            f"  Gerador ............ {self.generator}\n"
            f"  Grade .............. {nx} x {ny} x {nz} ({self.voxels:,} voxels)\n"
            f"  Amostragem SDF ..... {self.sample_time_s * 1e3:.0f} ms\n"
            f"  Extração ........... {self.extract_time_s * 1e3:.0f} ms\n"
            f"  Total .............. {self.total_time_s * 1e3:.0f} ms\n"
            f"  Vértices ........... {self.n_vertices:,}\n"
            f"  Triângulos ......... {self.n_triangles:,}\n"
            f"  Pico de memória .... ~{self.peak_memory_mb:.1f} MB (estimado)"
        )

    def __str__(self) -> str:
        return self.report()


# ===================================================================== malha

@dataclass
class Mesh:
    vertices: np.ndarray            # (V, 3) float32
    faces: np.ndarray               # (F, 3) int32
    normals: np.ndarray             # (V, 3) float32
    stats: Optional[MeshStats] = None

    def _triangles(self):
        """Vértices por face em float64 (somatórios de massa precisos)."""
        v = self.vertices.astype(np.float64, copy=False)
        f = self.faces
        return v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]

    # ------------------------------------------------- propriedades de massa
    def volume(self) -> float:
        """Volume via teorema da divergência (malha fechada)."""
        p0, p1, p2 = self._triangles()
        return float(np.abs(np.einsum("ij,ij->i", p0, np.cross(p1, p2)).sum()) / 6.0)

    def surface_area(self) -> float:
        p0, p1, p2 = self._triangles()
        return float(np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1).sum() / 2.0)

    def centroid(self) -> np.ndarray:
        p0, p1, p2 = self._triangles()
        vol6 = np.einsum("ij,ij->i", p0, np.cross(p1, p2))
        c = (p0 + p1 + p2) / 4.0
        total = vol6.sum()
        if abs(total) < 1e-12:
            return self.vertices.mean(axis=0)
        return (c * vol6[:, None]).sum(axis=0) / total

    def bounding_box(self) -> Tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    # ------------------------------------------------------------ exportação
    def save_stl(self, path: str, name: bytes = b"parametricus") -> None:
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
        """Wavefront OBJ — legível e amplamente suportado.
        Escrita em blocos via ``np.savetxt`` (Fase 3.1 — antes, um f-string
        por linha; malhas grandes caíam de segundos para frações)."""
        with open(path, "w") as fh:
            fh.write("# gerado por parametricus\n")
            np.savetxt(fh, self.vertices, fmt="v %.6f %.6f %.6f")
            np.savetxt(fh, self.normals, fmt="vn %.6f %.6f %.6f")
            f = self.faces.astype(np.int64) + 1
            idx = np.column_stack([f[:, 0], f[:, 0], f[:, 1], f[:, 1],
                                   f[:, 2], f[:, 2]])
            np.savetxt(fh, idx, fmt="f %d//%d %d//%d %d//%d")

    def save_ply(self, path: str) -> None:
        """PLY binário (little-endian) com normais por vértice (Fase 4.2)."""
        header = (
            "ply\n"
            "format binary_little_endian 1.0\n"
            "comment gerado por parametricus\n"
            f"element vertex {len(self.vertices)}\n"
            "property float x\nproperty float y\nproperty float z\n"
            "property float nx\nproperty float ny\nproperty float nz\n"
            f"element face {len(self.faces)}\n"
            "property list uchar int vertex_indices\n"
            "end_header\n"
        )
        vdata = np.hstack([self.vertices, self.normals]).astype("<f4")
        fdata = np.empty(len(self.faces),
                         dtype=[("n", "u1"), ("idx", "<i4", (3,))])
        fdata["n"] = 3
        fdata["idx"] = self.faces
        with open(path, "wb") as fh:
            fh.write(header.encode("ascii"))
            fh.write(vdata.tobytes())
            fh.write(fdata.tobytes())
        logger.info("PLY salvo em: %s (%d vértices, %d faces)",
                    path, len(self.vertices), len(self.faces))

    # ---------------------------------------------- propriedades inerciais
    def inertia_tensor(self, density: float = 1.0) -> np.ndarray:
        """
        Tensor de inércia 3x3 em relação ao CENTROIDE (kg·mm² se a
        densidade vier em kg/mm³; em geral, [densidade]·mm⁵), calculado
        por integração exata sobre tetraedros origem-face (mesmo método
        do volume/centroide, estendido aos momentos de 2ª ordem).
        Requer malha fechada. Base do sistema de materiais do roadmap.
        """
        p0, p1, p2 = self._triangles()
        det = np.einsum("ij,ij->i", p0, np.cross(p1, p2))   # 6 x vol assinado
        volume = det.sum() / 6.0

        # integral de x_i * x_j sobre cada tetraedro (0, p0, p1, p2):
        # detJ/120 * ( sum_k p_k p_k^T + (sum_k p_k)(sum_k p_k)^T )
        s = p0 + p1 + p2                                    # (F, 3)
        outer_sum = (np.einsum("fi,fj->fij", p0, p0) +
                     np.einsum("fi,fj->fij", p1, p1) +
                     np.einsum("fi,fj->fij", p2, p2))
        outer_s = np.einsum("fi,fj->fij", s, s)
        C = np.einsum("f,fij->ij", det, outer_sum + outer_s) / 120.0

        sign = 1.0 if volume >= 0 else -1.0
        C *= sign
        volume = abs(volume)
        mass = density * volume
        C *= density

        # translada para o centroide: C_c = C - m * c c^T
        c = self.centroid()
        C -= mass * np.outer(c, c)
        # tensor de inércia: I = tr(C) Id - C
        return np.trace(C) * np.eye(3) - C

    def mass_properties(self, density: float = 1.0) -> dict:
        """Dicionário com massa, volume, centroide e tensor/momentos
        principais de inércia para a densidade dada ([massa]/mm³)."""
        volume = self.volume()
        inertia = self.inertia_tensor(density)
        principal = np.linalg.eigvalsh(inertia)
        return {
            "volume_mm3": volume,
            "mass": density * volume,
            "centroid_mm": self.centroid(),
            "inertia_tensor": inertia,
            "principal_moments": principal,
        }

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


# ================================================================= geradores
class MeshGenerator(ABC):
    """Interface dos geradores de malha (padrão Strategy).
    Um gerador converte um sólido SDF em ``Mesh``. Novos algoritmos —
    por exemplo, malha adaptativa por octree — implementam esta interface
    e são usados via ``generate_mesh(..., generator=...)``, sem alterações
    em Document, viewer ou no kernel geométrico.
    """

    name: str = "MeshGenerator"

    @abstractmethod
    def generate(self, solid: SDF, resolution: int = 96,
                 padding: float = 0.05) -> Mesh:
        """Gera a malha do sólido.
        resolution: nº de amostras no maior eixo da caixa envolvente.
        padding:    margem relativa adicionada à caixa envolvente.
        """


class MarchingCubesGenerator(MeshGenerator):
    """Grade uniforme + Marching Cubes, processada em blocos (chunks).
    A grade de pontos nunca existe por inteiro: cada bloco de até
    ``block_points`` amostras é gerado num buffer float32 reutilizado,
    avaliado e sobrescrito pelo bloco seguinte. O único array persistente
    do tamanho do domínio é o campo escalar float32 (4 bytes por voxel;
    o Marching Cubes do scikit-image opera em float32 nativamente, sem
    cópia adicional).
    """

    name = "MarchingCubes (grade em blocos, float32)"

    def __init__(self, block_points: int = 500_000):
        self.block_points = int(block_points)

    def generate(self, solid: SDF, resolution: int = 96,
                 padding: float = 0.05) -> Mesh:
        t0 = time.perf_counter()
        bmin, bmax = solid.bounds()
        bmin, bmax = np.asarray(bmin, float), np.asarray(bmax, float)
        size = bmax - bmin
        pad = size.max() * padding + 1e-6
        bmin, bmax = bmin - pad, bmax + pad
        size = bmax - bmin

        spacing = size.max() / resolution
        counts = np.maximum(np.ceil(size / spacing).astype(int) + 1, 2)
        nx, ny, nz = (int(c) for c in counts)

        xs = np.linspace(bmin[0], bmax[0], nx)
        ys = np.linspace(bmin[1], bmax[1], ny)
        zs = np.linspace(bmin[2], bmax[2], nz)

        # amostragem por lotes de fatias em z, com poda por bbox nas
        # booleanas (margem >= diagonal da célula mantém exata a
        # interpolação do Marching Cubes junto à superfície)
        field = np.empty((nx, ny, nz), dtype=np.float32)
        XY = np.stack(np.meshgrid(xs, ys, indexing="ij"),
                      axis=-1).reshape(-1, 2).astype(np.float32)
        slab = nx * ny
        zstep = max(1, self.block_points // slab)
        buf = np.empty((slab * zstep, 3), dtype=np.float32)
        with _sdf.prune_margin(2.0 * spacing):
            for k0 in range(0, nz, zstep):
                ks = range(k0, min(k0 + zstep, nz))
                m = len(ks) * slab
                for j, k in enumerate(ks):
                    buf[j * slab:(j + 1) * slab, :2] = XY
                    buf[j * slab:(j + 1) * slab, 2] = zs[k]
                d = solid.distance(buf[:m])
                field[:, :, k0:k0 + len(ks)] = (
                    d.reshape(len(ks), nx, ny).transpose(1, 2, 0))
        t_sample = time.perf_counter() - t0

        if field.min() > 0 or field.max() < 0:
            raise ValueError(
                "A superfície não cruza o volume amostrado — "
                "verifique dimensões/parâmetros do modelo."
            )

        dx = [(xs[-1] - xs[0]) / (nx - 1),
              (ys[-1] - ys[0]) / (ny - 1),
              (zs[-1] - zs[0]) / (nz - 1)]
        t1 = time.perf_counter()
        verts, faces, normals, _ = measure.marching_cubes(
            field, level=0.0, spacing=dx)
        verts = (verts + bmin).astype(np.float32)
        # SDF: interior negativo -> o gradiente aponta para fora; o
        # marching_cubes assume o oposto ('descent'), então as normais
        # vêm apontando para dentro.
        normals = np.ascontiguousarray(-normals, dtype=np.float32)
        faces = faces.astype(np.int32)
        t2 = time.perf_counter()

        mesh_mb = (verts.nbytes + faces.nbytes + normals.nbytes) / 2 ** 20
        # pico ~ campo + bloco de pontos + temporários da árvore SDF
        # (vários arrays float64 do tamanho do bloco durante a avaliação)
        block_mb = (buf.nbytes + 6 * len(buf) * 8) / 2 ** 20
        peak_mb = field.nbytes / 2 ** 20 + max(block_mb, mesh_mb * 2)
        stats = MeshStats(
            generator=self.name,
            grid_shape=(nx, ny, nz),
            voxels=nx * ny * nz,
            n_vertices=len(verts),
            n_triangles=len(faces),
            sample_time_s=t_sample,
            extract_time_s=t2 - t1,
            total_time_s=t2 - t0,
            peak_memory_mb=peak_mb,
        )
        return Mesh(vertices=verts, faces=faces, normals=normals, stats=stats)


# ==================================================================== fachada
_DEFAULT_GENERATOR: MeshGenerator = MarchingCubesGenerator()


def generate_mesh(solid: SDF, resolution: int = 96, padding: float = 0.05,
                  generator: Optional[MeshGenerator] = None,
                  verbose: bool = False) -> Mesh:
    """
    Gera a malha de um sólido SDF.

    resolution: nº de amostras no maior eixo da caixa envolvente.
                64 = rascunho rápido; 128 = boa qualidade; 256 = alta.
    padding:    margem relativa adicionada à caixa envolvente.
    generator:  algoritmo de geração (padrão: MarchingCubesGenerator).
                Alternativas implementam a interface MeshGenerator.
    verbose:    imprime as estatísticas da geração (também disponíveis
                em mesh.stats).
    """
    mesh = (generator or _DEFAULT_GENERATOR).generate(solid, resolution=resolution, padding=padding)
    if mesh.stats is not None:
        level = logger.info if verbose else logger.debug
        level("%s", mesh.stats.report())
    return mesh
