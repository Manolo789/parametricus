"""
parametricus.document
================
Documento paramétrico: reúne o conjunto de parâmetros, a árvore de
features (histórico de construção) e a regeneração do modelo.

Fluxo típico:

    doc = Document("Flange")
    doc.params.define("diametro", 80)
    ...
    doc.set_body(lambda P: <árvore SDF construída com P>)
    doc.rebuild()
    doc.export_stl("flange.stl")

    doc.params.set("diametro", 100)   # muda o parâmetro...
    doc.rebuild()                     # ...e o modelo inteiro regenera
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from .parameters import ParameterSet
from .sdf import SDF
from .mesher import Mesh, generate_mesh


class Feature:
    """Entrada nomeada no histórico de construção (árvore de features)."""

    def __init__(self, name: str, build: Callable[[ParameterSet], SDF],
                 description: str = ""):
        self.name = name
        self.build = build
        self.description = description
        self.solid: Optional[SDF] = None


class Document:
    """Documento CAD paramétrico."""

    def __init__(self, name: str = "Sem título"):
        self.name = name
        self.params = ParameterSet()
        self.features: List[Feature] = []
        self._body_fn: Optional[Callable[[ParameterSet], SDF]] = None
        self.body: Optional[SDF] = None
        self.mesh: Optional[Mesh] = None
        self._mesh_resolution: Optional[int] = None
        self._dirty = True
        self.params.on_change(self._mark_dirty)

    # ------------------------------------------------------------- features
    def add_feature(self, name: str, build: Callable[[ParameterSet], SDF],
                    description: str = "") -> Feature:
        """
        Adiciona uma feature ao histórico. `build` recebe o ParameterSet e
        retorna o sólido daquela etapa. O corpo final é definido por
        set_body (que normalmente combina as features).
        """
        f = Feature(name, build, description)
        self.features.append(f)
        self._dirty = True
        return f

    def set_body(self, build: Callable[[ParameterSet], SDF]) -> None:
        """Define a função que constrói o corpo final do documento."""
        self._body_fn = build
        self._dirty = True

    # ---------------------------------------------------------- regeneração
    def _mark_dirty(self) -> None:
        self._dirty = True

    def rebuild(self, resolution: int = 96, verbose: bool = True) -> Mesh:
        """Regenera a árvore de features e a malha do corpo final."""
        if self._body_fn is None:
            raise RuntimeError("Nenhum corpo definido — chame set_body().")

        t0 = time.perf_counter()
        for f in self.features:
            f.solid = f.build(self.params)
        self.body = self._body_fn(self.params)
        t1 = time.perf_counter()

        self.mesh = generate_mesh(self.body, resolution=resolution)
        self._mesh_resolution = resolution
        t2 = time.perf_counter()
        self._dirty = False

        if verbose:
            st = self.mesh.stats
            extra = (f" — {st.voxels:,} voxels, {st.n_triangles:,} triângulos, "
                     f"~{st.peak_memory_mb:.0f} MB de pico" if st else "")
            print(f"[{self.name}] árvore reconstruída em {(t1 - t0)*1e3:.1f} ms, "
                  f"malha ({resolution}³ eq.) em {(t2 - t1)*1e3:.0f} ms{extra}")
        return self.mesh

    def _ensure_mesh(self, resolution: int) -> Mesh:
        if self.mesh is None or self._dirty or (self._mesh_resolution != resolution):
            self.rebuild(resolution=resolution)
        return self.mesh

    # ----------------------------------------------------------- exportação
    def export_stl(self, path: str, resolution: int = 128) -> None:
        self._ensure_mesh(resolution).save_stl(path, name=self.name.encode()[:80])
        print(f"[{self.name}] STL salvo em: {path}")

    def export_obj(self, path: str, resolution: int = 128) -> None:
        self._ensure_mesh(resolution).save_obj(path)
        print(f"[{self.name}] OBJ salvo em: {path}")

    # ------------------------------------------------------------ relatório
    def report(self, resolution: int = 96) -> str:
        mesh = self._ensure_mesh(resolution)
        lines = [
            "=" * 60,
            f" DOCUMENTO: {self.name}",
            "=" * 60,
            "",
            " PARÂMETROS",
            " " + "-" * 58,
        ]
        lines += ["  " + ln for ln in self.params.table().splitlines()]
        if self.features:
            lines += ["", " HISTÓRICO DE FEATURES", " " + "-" * 58]
            for i, f in enumerate(self.features, 1):
                desc = f" — {f.description}" if f.description else ""
                lines.append(f"  {i:2d}. {f.name}{desc}")
        lines += ["", " PROPRIEDADES DO SÓLIDO", " " + "-" * 58,
                  mesh.report(), "=" * 60]
        return "\n".join(lines)

    def show(self, resolution: int = 96, **kwargs) -> None:
        """Abre o visualizador 3D (matplotlib)."""
        from .viewer import show_mesh
        show_mesh(self._ensure_mesh(resolution), title=self.name, **kwargs)
