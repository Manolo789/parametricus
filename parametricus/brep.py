# -*- coding: utf-8 -*-
"""
parametricus.brep — ponte SDF ⇄ B-Rep (núcleo-K)
=================================================

Integra o kernel B-Rep próprio (:mod:`nucleok`) ao parametricus,
concluindo a rota STEP/IGES do roadmap **sem OCCT**:

Exportação (três níveis de fidelidade, escolhidos automaticamente):

1. **Analítica exata** — se a árvore SDF do documento é composta de
   primitivas mapeáveis (Esfera, Caixa, Cilindro, Cone, Toro, Extrusão
   de perfis poligonais/circulares/retangulares, Revolução de perfis
   poligonais) e transformações de similaridade (Translação, Rotação,
   Escala), o STEP sai com as superfícies analíticas EXATAS do núcleo-K
   (PLANE/CYLINDRICAL/SPHERICAL/TOROIDAL/REVOLUTION) — sem perda.
2. **Facetada por booleanas** — se a árvore contém União/Interseção/
   Subtração (ou Espelho), as primitivas continuam sendo construídas em
   B-Rep e as booleanas do núcleo-K resolvem a combinação (resultado
   facetado com deflexão controlada, mas topologicamente VÁLIDO).
3. **Facetada por malha** — qualquer nó fora do vocabulário
   (SmoothUnion, Shell, Round, arrays, MeshSDF, ...) faz a exportação
   cair para o caminho geral: marching cubes → ``solid_from_tessellation``
   → STEP (a limitação de conversão com perda documentada no roadmap).

Importação: ``load_step(path)`` lê STEP com o leitor próprio do
núcleo-K, tessela e devolve um :class:`~parametricus.io.MeshSDF` —
pronto para booleanas com o resto da geometria paramétrica.

Uso::

    from parametricus import Document
    doc.export("peca.step")            # despacho automático (1→2→3)
    doc.export("peca.iges")            # wireframe IGES das arestas

    from parametricus.brep import load_step
    peca = load_step("importada.step") # MeshSDF
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import numpy as np

from ._log import logger
from .mesher import Mesh

try:
    import nucleok as _nk
    from nucleok import Transform as _NkTransform
    HAS_NUCLEOK = True
except ImportError:                                   # pragma: no cover
    HAS_NUCLEOK = False


def _require_nucleok():
    if not HAS_NUCLEOK:
        raise ImportError(
            "parametricus.brep requer o pacote nucleok (o kernel B-Rep "
            "que acompanha este repositório) no PYTHONPATH")


# ============================================================ malha ⇄ B-Rep
def mesh_to_solid(mesh: Mesh) -> "object":
    """Malha fechada do parametricus → Solid B-Rep de faces planas
    (via :func:`nucleok.solid_from_tessellation`)."""
    _require_nucleok()
    tess = _nk.Tessellation(mesh.vertices.astype(np.float64),
                            mesh.faces.astype(np.int64))
    return _nk.solid_from_tessellation(tess)


def solid_to_mesh(solid, deflection: float = 0.02) -> Mesh:
    """Solid do núcleo-K → malha do parametricus (com normais por
    vértice ponderadas por área)."""
    _require_nucleok()
    from .io import _vertex_normals
    t = _nk.tessellate(solid, deflection)
    v = t.vertices.astype(np.float32)
    f = t.triangles.astype(np.int32)
    return Mesh(vertices=v, faces=f, normals=_vertex_normals(v, f))


def solid_to_sdf(solid, deflection: float = 0.02, resolution: int = 64):
    """Solid do núcleo-K → nó :class:`~parametricus.io.MeshSDF`
    (participa de booleanas SDF com o resto do documento)."""
    from .io import MeshSDF
    return MeshSDF(solid_to_mesh(solid, deflection),
                   resolution=resolution)


# ==================================================== árvore SDF → B-Rep
def _val(x):
    from .sdf import _val as sdf_val
    return float(sdf_val(x))


def _vec(x):
    from .sdf import _vec as sdf_vec
    return np.asarray(sdf_vec(x), float)


def _profile_polygon(profile) -> Optional[np.ndarray]:
    """Perfil 2D → polígono (N, 2) quando a forma é poligonal exata."""
    from . import sketch as sk
    if isinstance(profile, sk.PolygonProfile):
        return np.asarray(profile._verts(), float)
    if isinstance(profile, sk.RectProfile) and _val(profile.cr) == 0.0:
        w, h = _val(profile.width) / 2.0, _val(profile.height) / 2.0
        return np.array([(-w, -h), (w, -h), (w, h), (-w, h)])
    if isinstance(profile, sk._PTranslate):
        inner = _profile_polygon(profile.child)
        if inner is not None:
            return inner + np.array([_val(profile.dx), _val(profile.dy)])
    return None


def _dedup(poly: np.ndarray) -> np.ndarray:
    keep = [0]
    for i in range(1, len(poly)):
        if np.linalg.norm(poly[i] - poly[keep[-1]]) > 1e-12:
            keep.append(i)
    if len(keep) > 1 and np.linalg.norm(poly[keep[-1]] - poly[keep[0]]) \
            < 1e-12:
        keep.pop()
    return poly[keep]


def node_to_solid(node, deflection: float = 0.02
                  ) -> Optional[Tuple["object", bool]]:
    """
    Mapeia recursivamente um nó SDF do parametricus para um Solid B-Rep
    do núcleo-K. Devolve ``(solid, analitico)`` — ``analitico=True``
    quando NENHUMA booleana/espelho facetou o caminho — ou ``None`` se
    algum nó da subárvore não tem correspondência B-Rep.
    """
    _require_nucleok()
    from . import sdf as S
    from . import sketch as sk

    # ------------------------------------------------------- primitivas
    if isinstance(node, S.Sphere):
        return _nk.make_sphere(_val(node.radius)), True
    if isinstance(node, S.Box):
        d = _vec(node.size)
        return _nk.make_box(*d, origin=-d / 2.0), True
    if isinstance(node, S.Cylinder):
        r, h = _val(node.radius), _val(node.height)
        return _nk.make_cylinder(r, h, origin=(0, 0, -h / 2.0)), True
    if isinstance(node, S.Cone):
        r1, r2 = _val(node.r1), _val(node.r2)
        h2 = _val(node.height) / 2.0
        prof = _dedup(np.array([(0.0, -h2), (r1, -h2),
                                (r2, h2), (0.0, h2)]))
        return _nk.revolve(prof), True
    if isinstance(node, S.Torus):
        return _nk.make_torus(_val(node.R), _val(node.r)), True

    # ------------------------------------------------ extrusão/revolução
    if isinstance(node, S.Extrude):
        h = _val(node.height)
        if isinstance(node.profile, sk.CircleProfile):
            return _nk.make_cylinder(_val(node.profile.radius), h,
                                     origin=(0, 0, -h / 2.0)), True
        poly = _profile_polygon(node.profile)
        if poly is not None:
            return _nk.extrude(poly, h, z0=-h / 2.0), True
        return None
    if isinstance(node, S.Revolve):
        poly = _profile_polygon(node.profile)
        if poly is not None and np.all(poly[:, 0] >= -1e-12):
            return _nk.revolve(np.clip(poly, [0, -np.inf],
                                       None)), True
        if isinstance(node.profile, sk._PTranslate) and isinstance(
                node.profile.child, sk.CircleProfile):
            R = _val(node.profile.dx)
            r = _val(node.profile.child.radius)
            z = _val(node.profile.dy)
            if R > r > 0:                              # toro exato
                return _nk.make_torus(R, r, center=(0, 0, z)), True
        return None

    # ------------------------------------------------- transformações
    if isinstance(node, S.Translate):
        got = node_to_solid(node.child, deflection)
        if got is None:
            return None
        s, exact = got
        return _nk.transform_solid(
            s, _NkTransform.translation(_vec(node.offset))), exact
    if isinstance(node, S.Rotate):
        got = node_to_solid(node.child, deflection)
        if got is None:
            return None
        s, exact = got
        T = _NkTransform.rotation(_vec(node.axis),
                                  np.radians(_val(node.angle)))
        return _nk.transform_solid(s, T), exact
    if isinstance(node, S.Scale):
        got = node_to_solid(node.child, deflection)
        if got is None:
            return None
        s, exact = got
        return _nk.transform_solid(
            s, _NkTransform.scaling(_val(node.factor))), exact
    if isinstance(node, S.Mirror):
        got = node_to_solid(node.child, deflection)
        if got is None:
            return None
        s, _ = got
        m = _nk.transform_solid(s, _NkTransform.mirror(_vec(node.normal)))
        return _nk.fuse(s, m, deflection=deflection), False

    # ----------------------------------------------------- booleanas
    _BOOL = {S.Union_: _nk.fuse, S.Intersection: _nk.common,
             S.Difference: _nk.cut}
    for cls, op in _BOOL.items():
        if isinstance(node, cls):
            ga = node_to_solid(node.a, deflection)
            gb = node_to_solid(node.b, deflection)
            if ga is None or gb is None:
                return None
            return op(ga[0], gb[0], deflection=deflection), False

    return None                       # nó fora do vocabulário B-Rep


def document_to_solid(doc, deflection: float = 0.02,
                      resolution: Optional[int] = None
                      ) -> Tuple["object", str]:
    """
    Converte o documento em Solid B-Rep pelo melhor caminho disponível.
    Devolve ``(solid, modo)`` com modo em:

    - ``"analítico"``  — árvore inteira mapeada; superfícies exatas;
    - ``"facetado (booleanas B-Rep)"`` — árvore mapeada, mas contém
      booleanas/espelho (resultado facetado com a deflexão dada);
    - ``"facetado (malha)"`` — caminho geral SDF → marching cubes →
      reconstrução B-Rep plana.
    """
    _require_nucleok()
    body = doc.body if doc.body is not None else doc.rebuild(
        verbose=False) and doc.body
    got = node_to_solid(body, deflection) if body is not None else None
    if got is not None:
        solid, exact = got
        return solid, ("analítico" if exact
                       else "facetado (booleanas B-Rep)")
    mesh = doc.get_mesh(resolution or doc.export_resolution)
    return mesh_to_solid(mesh), "facetado (malha)"


# ============================================================== exportação
def export_document_step(doc, path: str, deflection: float = 0.02,
                         resolution: Optional[int] = None) -> str:
    """Exporta o documento para STEP AP214 pelo melhor caminho
    (analítico quando possível). Devolve o modo usado."""
    solid, modo = document_to_solid(doc, deflection, resolution)
    _nk.write_step(solid, path, name=doc.name)
    logger.info("[%s] STEP (%s) salvo em: %s", doc.name, modo, path)
    return modo


def export_document_iges(doc, path: str, deflection: float = 0.02,
                         resolution: Optional[int] = None) -> str:
    """Exporta o wireframe IGES 5.3 das arestas do documento."""
    solid, modo = document_to_solid(doc, deflection, resolution)
    _nk.write_iges(solid, path, name=doc.name)
    logger.info("[%s] IGES wireframe (%s) salvo em: %s",
                doc.name, modo, path)
    return modo


def save_step(mesh: Mesh, path: str) -> None:
    """Exportador de MALHA → STEP facetado (registrado no despacho de
    :func:`parametricus.io.export_mesh`)."""
    _nk.write_step(mesh_to_solid(mesh), path)
    logger.info("STEP (facetado, %d faces de malha) salvo em: %s",
                len(mesh.faces), path)


def save_iges(mesh: Mesh, path: str) -> None:
    """Exportador de MALHA → IGES wireframe (despacho por extensão)."""
    _nk.write_iges(mesh_to_solid(mesh), path)
    logger.info("IGES wireframe salvo em: %s", path)


# ============================================================== importação
def load_step_solids(path: str):
    """Lê um arquivo STEP com o leitor do núcleo-K → lista de Solid."""
    _require_nucleok()
    return _nk.read_step(path)


def load_step_mesh(path: str, deflection: float = 0.02) -> Mesh:
    """STEP → malha do parametricus (sólidos fundidos)."""
    solids = load_step_solids(path)
    if not solids:
        raise ValueError(f"nenhum sólido em {path!r}")
    parts = [solid_to_mesh(s, deflection) for s in solids]
    if len(parts) == 1:
        return parts[0]
    from .io import _vertex_normals
    vs, fs, off = [], [], 0
    for m in parts:
        vs.append(m.vertices)
        fs.append(m.faces + off)
        off += len(m.vertices)
    v = np.vstack(vs)
    f = np.vstack(fs)
    return Mesh(vertices=v, faces=f, normals=_vertex_normals(v, f))


def load_step(path: str, resolution: int = 64,
              deflection: float = 0.02):
    """
    Importa STEP como nó SDF (Fase 4.1 concluída pela rota núcleo-K):
    leitor STEP próprio → tesselação → :class:`~parametricus.io.MeshSDF`.

        peca = load_step("carcaça.step")
        furada = peca - Cylinder(4, 99)      # booleana com paramétrico
    """
    from .io import MeshSDF
    mesh = load_step_mesh(path, deflection)
    logger.info("STEP importado: %s (%d vértices, %d faces)",
                os.path.basename(path), len(mesh.vertices),
                len(mesh.faces))
    return MeshSDF(mesh, resolution=resolution)
