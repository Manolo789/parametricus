"""
parametricus.io
===============
Interoperabilidade (Fase 4 do roadmap).

Implementado nesta fase (sem dependências novas):
- Exportação por extensão: ``.stl``, ``.obj``, ``.ply`` (``export_mesh`` /
  ``Document.export``).
- Importação: ``import_mesh("peca.stl" | "peca.obj") -> Mesh`` (STL binário
  e ASCII; OBJ com faces trianguladas em leque).

Fora de escopo desta fase (exigem OCCT/trimesh como dependência opcional,
ver roadmap): STEP, IGES, GLTF, 3MF e o nó ``MeshSDF`` para booleanas com
malhas importadas.
"""

from __future__ import annotations

import os
import struct
from typing import Callable, Dict

import numpy as np

from ._log import logger
from .mesher import Mesh

# ------------------------------------------------------------------ export
_EXPORTERS: Dict[str, Callable[[Mesh, str], None]] = {
    ".stl": lambda mesh, path: mesh.save_stl(path),
    ".obj": lambda mesh, path: mesh.save_obj(path),
    ".ply": lambda mesh, path: mesh.save_ply(path),
}


def supported_export_formats() -> list:
    return sorted(_EXPORTERS)


def export_mesh(mesh: Mesh, path: str) -> None:
    """Exporta a malha despachando pelo sufixo do arquivo."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _EXPORTERS:
        raise ValueError(
            f"Formato de exportação não suportado: {ext!r} "
            f"(disponíveis: {', '.join(supported_export_formats())})"
        )
    _EXPORTERS[ext](mesh, path)


# ------------------------------------------------------------------ import
def _vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Normais por vértice ponderadas por área (cross não normalizado)."""
    p0 = vertices[faces[:, 0]]
    p1 = vertices[faces[:, 1]]
    p2 = vertices[faces[:, 2]]
    fn = np.cross(p1 - p0, p2 - p0)
    normals = np.zeros_like(vertices, dtype=np.float64)
    for k in range(3):
        np.add.at(normals, faces[:, k], fn)
    lens = np.linalg.norm(normals, axis=1, keepdims=True)
    lens[lens == 0.0] = 1.0
    return (normals / lens).astype(np.float32)


def _weld(vertices: np.ndarray, faces: np.ndarray):
    """Solda vértices duplicados (STL repete 3 vértices por triângulo)."""
    uniq, inverse = np.unique(vertices.round(6), axis=0, return_inverse=True)
    return uniq.astype(np.float32), inverse[faces].astype(np.int32)


def load_stl(path: str) -> Mesh:
    """Carrega STL binário ou ASCII como ``Mesh``."""
    with open(path, "rb") as fh:
        head = fh.read(80)
        rest = fh.read()
    # binário: 80 bytes de header + uint32 n + n * 50 bytes
    if len(rest) >= 4:
        (n,) = struct.unpack("<I", rest[:4])
        if len(rest) == 4 + n * 50:
            data = np.frombuffer(rest, offset=4, dtype=np.dtype([
                ("normal", "<3f4"), ("v0", "<3f4"),
                ("v1", "<3f4"), ("v2", "<3f4"), ("attr", "<u2"),
            ]), count=n)
            tri = np.stack([data["v0"], data["v1"], data["v2"]], axis=1)
            vertices = tri.reshape(-1, 3)
            faces = np.arange(len(vertices)).reshape(-1, 3)
            vertices, faces = _weld(vertices, faces)
            mesh = Mesh(vertices=vertices, faces=faces,
                        normals=_vertex_normals(vertices, faces))
            logger.info("STL importado: %s (%d triângulos)", path, n)
            return mesh
    # ASCII
    text = (head + rest).decode("ascii", errors="ignore")
    coords = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("vertex"):
            coords.append([float(x) for x in line.split()[1:4]])
    if not coords or len(coords) % 3:
        raise ValueError(f"STL inválido ou vazio: {path}")
    vertices = np.asarray(coords, dtype=np.float32)
    faces = np.arange(len(vertices)).reshape(-1, 3)
    vertices, faces = _weld(vertices, faces)
    mesh = Mesh(vertices=vertices, faces=faces,
                normals=_vertex_normals(vertices, faces))
    logger.info("STL (ASCII) importado: %s (%d triângulos)", path, len(faces))
    return mesh


def load_obj(path: str) -> Mesh:
    """Carrega Wavefront OBJ como ``Mesh`` (faces com >3 lados são
    trianguladas em leque)."""
    vertices = []
    faces = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                vertices.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                idx = [int(tok.split("/")[0]) for tok in line.split()[1:]]
                idx = [i - 1 if i > 0 else len(vertices) + i for i in idx]
                for k in range(1, len(idx) - 1):        # leque
                    faces.append([idx[0], idx[k], idx[k + 1]])
    if not vertices or not faces:
        raise ValueError(f"OBJ inválido ou vazio: {path}")
    v = np.asarray(vertices, dtype=np.float32)
    f = np.asarray(faces, dtype=np.int32)
    mesh = Mesh(vertices=v, faces=f, normals=_vertex_normals(v, f))
    logger.info("OBJ importado: %s (%d vértices, %d triângulos)",
                path, len(v), len(f))
    return mesh


_IMPORTERS: Dict[str, Callable[[str], Mesh]] = {
    ".stl": load_stl,
    ".obj": load_obj,
}


def import_mesh(path: str) -> Mesh:
    """Importa uma malha despachando pelo sufixo do arquivo."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _IMPORTERS:
        raise ValueError(
            f"Formato de importação não suportado: {ext!r} "
            f"(disponíveis: {', '.join(sorted(_IMPORTERS))}; "
            f"STEP requer OCCT — ver roadmap Fase 4.1)"
        )
    return _IMPORTERS[ext](path)
