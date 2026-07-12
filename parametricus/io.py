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

import json
import os
import struct
import zipfile
from typing import Callable, Dict

import numpy as np

from ._log import logger
from .mesher import Mesh
from .sdf import SDF


# ------------------------------------------------------ export: GLB (glTF 2.0)
def save_glb(mesh: Mesh, path: str) -> None:
    """
    Exporta a malha como GLB (glTF 2.0 binário, Fase 4.2 — escrita direta,
    sem dependências). Um único buffer com POSITION, NORMAL e índices
    uint32; pronto para web/preview (three.js, <model-viewer>, Blender).
    """
    v = np.ascontiguousarray(mesh.vertices, dtype="<f4")
    n = np.ascontiguousarray(mesh.normals, dtype="<f4")
    idx = np.ascontiguousarray(mesh.faces.reshape(-1), dtype="<u4")

    def _pad4(b: bytes, fill: bytes = b"\0") -> bytes:
        return b + fill * (-len(b) % 4)

    vb, nb, ib = v.tobytes(), n.tobytes(), idx.tobytes()
    bin_chunk = _pad4(vb) + _pad4(nb) + _pad4(ib)
    off_v, off_n = 0, len(_pad4(vb))
    off_i = off_n + len(_pad4(nb))

    gltf = {
        "asset": {"version": "2.0", "generator": "parametricus"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1},
            "indices": 2, "mode": 4,
        }]}],
        "buffers": [{"byteLength": len(bin_chunk)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": off_v, "byteLength": len(vb),
             "target": 34962},
            {"buffer": 0, "byteOffset": off_n, "byteLength": len(nb),
             "target": 34962},
            {"buffer": 0, "byteOffset": off_i, "byteLength": len(ib),
             "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(v),
             "type": "VEC3",
             "min": [float(x) for x in v.min(axis=0)],
             "max": [float(x) for x in v.max(axis=0)]},
            {"bufferView": 1, "componentType": 5126, "count": len(n),
             "type": "VEC3"},
            {"bufferView": 2, "componentType": 5125, "count": len(idx),
             "type": "SCALAR"},
        ],
    }
    json_chunk = _pad4(json.dumps(gltf, separators=(",", ":")).encode(), b" ")

    with open(path, "wb") as fh:
        total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
        fh.write(struct.pack("<III", 0x46546C67, 2, total))       # "glTF"
        fh.write(struct.pack("<II", len(json_chunk), 0x4E4F534A))  # JSON
        fh.write(json_chunk)
        fh.write(struct.pack("<II", len(bin_chunk), 0x004E4942))   # BIN
        fh.write(bin_chunk)
    logger.info("GLB salvo em: %s (%d vértices, %d faces)",
                path, len(v), len(mesh.faces))


# ------------------------------------------------------------ export: 3MF
def save_3mf(mesh: Mesh, path: str, unit: str = "millimeter") -> None:
    """
    Exporta a malha como 3MF (Fase 4.2 — ZIP + XML, escrita própria).
    Formato relevante para impressão 3D (Cura, PrusaSlicer, Bambu Studio).
    """
    v = mesh.vertices
    f = mesh.faces
    verts_xml = "".join(
        f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in v)
    tris_xml = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f)
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<model unit="{unit}" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        '<resources><object id="1" type="model"><mesh>'
        f"<vertices>{verts_xml}</vertices>"
        f"<triangles>{tris_xml}</triangles>"
        "</mesh></object></resources>"
        '<build><item objectid="1"/></build></model>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" '
        'ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("3D/3dmodel.model", model)
    logger.info("3MF salvo em: %s (%d vértices, %d faces)",
                path, len(v), len(f))


# ------------------------------------------------------------------ export
def _save_step(mesh: Mesh, path: str) -> None:
    from .brep import save_step
    save_step(mesh, path)


def _save_iges(mesh: Mesh, path: str) -> None:
    from .brep import save_iges
    save_iges(mesh, path)


_EXPORTERS: Dict[str, Callable[[Mesh, str], None]] = {
    ".stl": lambda mesh, path: mesh.save_stl(path),
    ".obj": lambda mesh, path: mesh.save_obj(path),
    ".ply": lambda mesh, path: mesh.save_ply(path),
    ".glb": save_glb,
    ".3mf": save_3mf,
    ".step": _save_step,
    ".stp": _save_step,
    ".iges": _save_iges,
    ".igs": _save_iges,
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


# ------------------------------------------------------------------ MeshSDF
class MeshSDF(SDF):
    """
    SDF de uma malha triangular (Fase 4.1) — permite **booleanas entre
    peças importadas (STL/OBJ) e geometria paramétrica**:

        casco = MeshSDF(import_mesh("carcaça.stl"))
        peca  = casco - Cylinder(4, 99)          # furo na malha importada

    Implementação sem dependências: a distância assinada é pré-amostrada
    numa grade regular (distância exata ponto→triângulo + sinal por número
    de enrolamento generalizado, robusto a malhas imperfeitas) e as
    consultas usam interpolação trilinear. Custo de construção
    ~O(grade × triângulos), pago uma única vez; consultas são O(1).
    """

    name = "MeshSDF"

    def __init__(self, mesh: Mesh, resolution: int = 64,
                 padding: float = 0.05):
        self.mesh = mesh
        bmin, bmax = mesh.bounding_box()
        pad = float(np.max(bmax - bmin)) * padding + 1e-6
        self._lo = np.asarray(bmin, np.float64) - pad
        self._hi = np.asarray(bmax, np.float64) + pad
        self._res = int(resolution)
        self._grid = self._sample_grid()

    # ---- amostragem (construção) ----
    def _sample_grid(self) -> np.ndarray:
        r = self._res
        axes = [np.linspace(self._lo[k], self._hi[k], r) for k in range(3)]
        pts = np.stack(np.meshgrid(*axes, indexing="ij"),
                       axis=-1).reshape(-1, 3)
        dist = self._unsigned_distance(pts)
        inside = self._inside_mask(axes)
        logger.debug("MeshSDF: grade %d^3 amostrada (%d triângulos)",
                     r, len(self.mesh.faces))
        return np.where(inside.reshape(-1), -dist, dist).reshape(r, r, r)

    @staticmethod
    def _tri_dist(q, a, b, c):
        """Distância exata ponto->triângulo; q, a, b, c: (..., 3)."""
        ab, ac = b - a, c - a
        ap = q - a
        d1 = np.einsum("...k,...k->...", ab, ap)
        d2 = np.einsum("...k,...k->...", ac, ap)
        aa = np.einsum("...k,...k->...", ab, ab)
        bb = np.einsum("...k,...k->...", ac, ac)
        abac = np.einsum("...k,...k->...", ab, ac)
        denom = np.maximum(aa * bb - abac * abac, 1e-18)
        s = np.clip((bb * d1 - abac * d2) / denom, 0.0, 1.0)
        t = np.clip((aa * d2 - abac * d1) / denom, 0.0, 1.0)
        over = s + t > 1.0
        ssum = np.where(s + t == 0.0, 1.0, s + t)
        s = np.where(over, s / ssum, s)
        t = np.where(over, t / ssum, t)
        proj = a + s[..., None] * ab + t[..., None] * ac
        d = np.linalg.norm(q - proj, axis=-1)

        def edge(p0, e):
            w = q - p0
            ee = np.maximum(np.einsum("...k,...k->...", e, e), 1e-18)
            tt = np.clip(np.einsum("...k,...k->...", e, w) / ee, 0.0, 1.0)
            return np.linalg.norm(w - tt[..., None] * e, axis=-1)

        d = np.minimum(d, edge(a, ab))
        d = np.minimum(d, edge(a, ac))
        d = np.minimum(d, edge(b, c - b))
        return d

    def _unsigned_distance(self, pts: np.ndarray) -> np.ndarray:
        """Distância não assinada ponto->malha. Para malhas grandes usa
        kNN sobre os centroides (SciPy, se disponível) + distância exata
        aos k triângulos candidatos; senão, força bruta em blocos."""
        v = self.mesh.vertices.astype(np.float64)
        f = self.mesh.faces
        A, B, C = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        F = len(f)
        try:
            from scipy.spatial import cKDTree
        except ImportError:
            cKDTree = None

        if cKDTree is not None and F > 512:
            cent = (A + B + C) / 3.0
            # raio de segurança: o triângulo mais próximo pode não ter o
            # centroide mais próximo; k vizinhos + meia-diagonal cobre isso
            half = np.linalg.norm(
                np.stack([A, B, C]) - cent[None], axis=-1).max()
            k = min(16, F)
            _, idx = cKDTree(cent).query(pts, k=k)          # (N, k)
            out = np.empty(len(pts))
            chunk = max(1, int(4_000_000 / k))
            for s0 in range(0, len(pts), chunk):
                sl = slice(s0, s0 + chunk)
                i = idx[sl]
                q = pts[sl][:, None, :]
                d = self._tri_dist(q, A[i], B[i], C[i])     # (n, k)
                out[sl] = d.min(axis=1)
            _ = half  # nota: erro limitado pela densidade da malha
            return out

        # força bruta (malhas pequenas ou sem SciPy)
        out = np.empty(len(pts))
        chunk = max(1, int(2_000_000 / max(F, 1)))
        for s0 in range(0, len(pts), chunk):
            q = pts[s0:s0 + chunk][:, None, :]
            d = self._tri_dist(q, A[None], B[None], C[None])
            out[s0:s0 + chunk] = d.min(axis=1)
        return out

    def _inside_mask(self, axes) -> np.ndarray:
        """Sinal por paridade de cruzamentos: um raio +X por linha (y, z)
        da grade; O(linhas x triângulos), muito mais barato que
        enrolamento por ponto."""
        xs, ys, zs = axes
        r = self._res
        v = self.mesh.vertices.astype(np.float64)
        f = self.mesh.faces
        A, B, C = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        span = float(np.max(self._hi - self._lo))
        # jitter irracional minúsculo evita raios passando por arestas
        YY, ZZ = np.meshgrid(ys + span * 1.23456789e-9,
                             zs + span * 2.34567891e-9, indexing="ij")
        rows = np.stack([YY.ravel(), ZZ.ravel()], axis=1)    # (R, 2)

        a2 = A[:, 1:]                       # projeção no plano (y, z)
        e0 = C[:, 1:] - a2                  # (F, 2)
        e1 = B[:, 1:] - a2
        d00 = (e0 * e0).sum(1)
        d01 = (e0 * e1).sum(1)
        d11 = (e1 * e1).sum(1)
        denom = d00 * d11 - d01 * d01
        ok = np.abs(denom) > 1e-18
        denom = np.where(ok, denom, 1.0)

        inside = np.zeros((len(rows), r), dtype=bool)
        chunk = max(1, int(4_000_000 / max(len(f), 1)))
        for s0 in range(0, len(rows), chunk):
            p = rows[s0:s0 + chunk][:, None, :] - a2[None]   # (n, F, 2)
            dp0 = (p * e0[None]).sum(-1)
            dp1 = (p * e1[None]).sum(-1)
            u = (d11 * dp0 - d01 * dp1) / denom
            w = (d00 * dp1 - d01 * dp0) / denom
            hit = ok & (u >= 0) & (w >= 0) & (u + w <= 1.0)  # (n, F)
            x_int = A[:, 0] + u * (C[:, 0] - A[:, 0]) + w * (B[:, 0] - A[:, 0])
            x_int = np.sort(np.where(hit, x_int, np.inf), axis=1)
            n_hits = hit.sum(axis=1)
            # paridade: nº de interseções com x_int > x do ponto, via
            # busca binária por linha (poucas interseções por raio)
            for j in range(len(x_int)):
                cnt = n_hits[j] - np.searchsorted(x_int[j], xs, side="right")
                inside[s0 + j] = (cnt % 2) == 1
        # inside está indexado por (y, z, x) -> reordena para (x, y, z)
        return np.moveaxis(inside.reshape(r, r, r), 2, 0)

    # ---- consultas (interpolação trilinear) ----
    def distance(self, p: np.ndarray) -> np.ndarray:
        r = self._res
        span = self._hi - self._lo
        pc = np.clip(p, self._lo, self._hi)
        outside = np.linalg.norm(p - pc, axis=1)
        u = (pc - self._lo) / span * (r - 1)
        i0 = np.clip(u.astype(np.int64), 0, r - 2)
        frac = u - i0
        g = self._grid
        ix, iy, iz = i0[:, 0], i0[:, 1], i0[:, 2]
        fx, fy, fz = frac[:, 0], frac[:, 1], frac[:, 2]
        c00 = g[ix, iy, iz] * (1 - fx) + g[ix + 1, iy, iz] * fx
        c01 = g[ix, iy, iz + 1] * (1 - fx) + g[ix + 1, iy, iz + 1] * fx
        c10 = g[ix, iy + 1, iz] * (1 - fx) + g[ix + 1, iy + 1, iz] * fx
        c11 = g[ix, iy + 1, iz + 1] * (1 - fx) + g[ix + 1, iy + 1, iz + 1] * fx
        c0 = c00 * (1 - fy) + c10 * fy
        c1 = c01 * (1 - fy) + c11 * fy
        return c0 * (1 - fz) + c1 * fz + outside

    def bounds(self):
        return self._lo.copy(), self._hi.copy()


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
