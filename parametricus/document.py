"""
parametricus.document
================
Documento paramétrico: reúne o conjunto de parâmetros, o histórico de
features (agora encadeado e editável), a regeneração seletiva do modelo
(cache inteligente), a malhagem preguiçosa e o Undo/Redo.

Fluxo típico:

    doc = Document("Flange")
    doc.params.define("diametro", 80)
    ...
    doc.set_body(lambda P: <árvore SDF construída com P>)
    doc.rebuild()
    doc.export_stl("flange.stl")

    doc.params.set("diametro", 100)   # muda o parâmetro...
    doc.rebuild()                     # ...apenas o que depende dele regenera

Histórico encadeado (Fase 2.1 — modo recomendado):

    doc.add_feature("Base",  lambda P: Box((P["L"], P["L"], P["e"])))
    doc.add_feature("Furo",  lambda P, prev: prev - Cylinder(P["d"]/2, 99))
    doc.rebuild()                     # corpo = resultado da última feature
    doc.suppress("Furo")              # suprime sem remover
    doc.undo()                        # desfaz a supressão
"""

from __future__ import annotations

import inspect
import time
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from ._log import logger, enable_console_logging
from .materials import Material
from .mesher import Mesh, generate_mesh
from .parameters import ParameterSet
from .sdf import SDF

BuildFn = Union[
    Callable[[ParameterSet], SDF],
    Callable[[ParameterSet, Optional[SDF]], SDF],
]


class Feature:
    """Entrada nomeada no histórico de construção.

    ``build`` aceita duas assinaturas:
    - ``build(P)`` — feature independente (compatível com a API anterior);
    - ``build(P, prev)`` — feature encadeada: recebe o sólido acumulado
      das features anteriores (``None`` na primeira) e retorna o novo.

    Estados: ``ok`` (construída), ``suppressed`` (ignorada no encadeamento,
    como o *suppress* de CADs comerciais), ``error`` (build lançou exceção;
    o encadeamento segue com o sólido anterior) e ``stale`` (aguardando
    rebuild).
    """

    def __init__(self, name: str, build: BuildFn, description: str = ""):
        self.name = name
        self.build = build
        self.description = description
        self.solid: Optional[SDF] = None
        self.state: str = "stale"
        self.error: Optional[Exception] = None
        #: parâmetros lidos no último build (rastreamento da Fase 1.3)
        self.reads: Set[str] = set()

    @property
    def suppressed(self) -> bool:
        return self.state == "suppressed"

    def _accepts_prev(self) -> bool:
        try:
            n = len(inspect.signature(self.build).parameters)
        except (TypeError, ValueError):
            n = 1
        return n >= 2

    def __repr__(self) -> str:
        return f"Feature({self.name!r}, state={self.state!r})"


# ------------------------------------------------------------- undo/redo
class _Command:
    """Comando reversível (padrão Command, Fase 2.2)."""
    label = "comando"

    def do(self, doc: "Document") -> None: ...
    def undo(self, doc: "Document") -> None: ...


class _SetParam(_Command):
    def __init__(self, name: str, old, new):
        self.name, self.old, self.new = name, old, new
        self.label = f"parâmetro {name} = {new!r}"

    def do(self, doc):
        doc.params.set(self.name, self.new)

    def undo(self, doc):
        doc.params.set(self.name, self.old)


class _AddFeature(_Command):
    def __init__(self, feature: Feature, index: int):
        self.feature, self.index = feature, index
        self.label = f"adicionar feature {feature.name!r}"

    def do(self, doc):
        doc.features.insert(self.index, self.feature)
        doc._invalidate_from(self.index)

    def undo(self, doc):
        doc.features.remove(self.feature)
        doc._invalidate_from(self.index)


class _RemoveFeature(_Command):
    def __init__(self, feature: Feature, index: int):
        self.feature, self.index = feature, index
        self.label = f"remover feature {feature.name!r}"

    def do(self, doc):
        doc.features.remove(self.feature)
        doc._invalidate_from(self.index)

    def undo(self, doc):
        doc.features.insert(self.index, self.feature)
        doc._invalidate_from(self.index)


class _SetState(_Command):
    def __init__(self, feature: Feature, old: str, new: str):
        self.feature, self.old, self.new = feature, old, new
        self.label = f"{'suprimir' if new == 'suppressed' else 'reativar'} {feature.name!r}"

    def do(self, doc):
        self.feature.state = self.new
        doc._invalidate_from(doc.features.index(self.feature))

    def undo(self, doc):
        self.feature.state = self.old
        doc._invalidate_from(doc.features.index(self.feature))


class _Reorder(_Command):
    def __init__(self, old_index: int, new_index: int):
        self.old_index, self.new_index = old_index, new_index
        self.label = f"reordenar feature {old_index} -> {new_index}"

    def do(self, doc):
        f = doc.features.pop(self.old_index)
        doc.features.insert(self.new_index, f)
        doc._invalidate_from(min(self.old_index, self.new_index))

    def undo(self, doc):
        f = doc.features.pop(self.new_index)
        doc.features.insert(self.old_index, f)
        doc._invalidate_from(min(self.old_index, self.new_index))


class _EditFeature(_Command):
    def __init__(self, feature: Feature, old_build: BuildFn, new_build: BuildFn):
        self.feature, self.old_build, self.new_build = feature, old_build, new_build
        self.label = f"editar feature {feature.name!r}"

    def do(self, doc):
        self.feature.build = self.new_build
        doc._invalidate_from(doc.features.index(self.feature))

    def undo(self, doc):
        self.feature.build = self.old_build
        doc._invalidate_from(doc.features.index(self.feature))


class Document:
    """Documento CAD paramétrico."""

    def __init__(self, name: str = "Sem título"):
        self.name = name
        self.params = ParameterSet()
        self.features: List[Feature] = []
        self._body_fn: Optional[Callable[[ParameterSet], SDF]] = None
        self._body_reads: Set[str] = set()
        self.body: Optional[SDF] = None
        self.material: Optional[Material] = None

        # --- malha (Fase 1.4 — lazy) --------------------------------------
        #: resolução padrão de pré-visualização (get_mesh()/show() sem args)
        self.preview_resolution: int = 96
        #: resolução padrão de exportação
        self.export_resolution: int = 128
        self._mesh: Optional[Mesh] = None
        self._mesh_resolution: Optional[int] = None
        # cache (resolução, assinatura) -> malha (Fase 1.3): rebuilds que
        # não alteram a geometria — inclusive voltar um parâmetro ao valor
        # anterior — reaproveitam a malha. LRU simples com capacidade fixa.
        self._mesh_cache: Dict[Tuple[int, str], Mesh] = {}
        self._mesh_cache_capacity: int = 8

        # --- invalidação seletiva (Fase 1.3) ------------------------------
        self._dirty_params: Set[str] = set()   # valores alterados desde o
        self._all_dirty = True                  # último rebuild da árvore
        self._first_dirty_feature = 0           # edições estruturais

        # --- undo/redo (Fase 2.2) -----------------------------------------
        self._undo_stack: List[_Command] = []
        self._redo_stack: List[_Command] = []
        self._replaying = False
        #: profundidade máxima da pilha de undo (entradas antigas descartadas)
        self.undo_limit: int = 200
        #: janela (s) para coalescer mudanças consecutivas do MESMO
        #: parâmetro em 1 entrada (arrastar um slider gera 1 undo, não 200)
        self.coalesce_window: float = 0.5
        self._last_param_push: float = 0.0

        self.params.on_change(self._on_params_changed)
        self.params.on_mutate(self._on_param_mutate)

    # ------------------------------------------------------------- features
    def add_feature(self, name: str, build: BuildFn,
                    description: str = "") -> Feature:
        """
        Adiciona uma feature ao histórico.

        ``build(P)`` ou ``build(P, prev)`` — na segunda forma a feature é
        ENCADEADA: recebe o sólido acumulado e o corpo do documento passa a
        ser o resultado da última feature (a menos que ``set_body`` seja
        usado, que tem precedência para compatibilidade).
        """
        f = Feature(name, build, description)
        self._apply(_AddFeature(f, len(self.features)))
        return f

    def get_feature(self, name: str) -> Feature:
        for f in self.features:
            if f.name == name:
                return f
        raise KeyError(f"Feature inexistente: {name!r}")

    def remove_feature(self, name: str) -> None:
        """Remove a feature do histórico (reversível com undo)."""
        f = self.get_feature(name)
        self._apply(_RemoveFeature(f, self.features.index(f)))

    def suppress(self, name: str) -> None:
        """Suprime a feature: permanece no histórico, mas é ignorada."""
        f = self.get_feature(name)
        if f.state != "suppressed":
            self._apply(_SetState(f, f.state, "suppressed"))

    def unsuppress(self, name: str) -> None:
        """Reativa uma feature suprimida."""
        f = self.get_feature(name)
        if f.state == "suppressed":
            self._apply(_SetState(f, "suppressed", "stale"))

    def reorder_feature(self, name: str, new_index: int) -> None:
        """Move a feature para a posição ``new_index`` do histórico."""
        f = self.get_feature(name)
        old = self.features.index(f)
        new_index = max(0, min(new_index, len(self.features) - 1))
        if old != new_index:
            self._apply(_Reorder(old, new_index))

    def edit_feature(self, name: str, build: BuildFn) -> None:
        """Substitui a função de construção da feature (reversível)."""
        f = self.get_feature(name)
        self._apply(_EditFeature(f, f.build, build))

    def set_body(self, build: Callable[[ParameterSet], SDF]) -> None:
        """Define a função que constrói o corpo final do documento.
        Tem precedência sobre o encadeamento de features (compatibilidade);
        sem ela, o corpo é o resultado da última feature não suprimida."""
        self._body_fn = build
        self._all_dirty = True
        self._invalidate_mesh()

    # ------------------------------------------------------------ undo/redo
    def _push(self, cmd: _Command) -> None:
        self._undo_stack.append(cmd)
        if len(self._undo_stack) > self.undo_limit:
            del self._undo_stack[: len(self._undo_stack) - self.undo_limit]
        self._redo_stack.clear()

    def _apply(self, cmd: _Command) -> None:
        cmd.do(self)
        if not self._replaying:
            self._push(cmd)

    def _on_param_mutate(self, name: str, old, new) -> None:
        if self._replaying:
            return
        now = time.monotonic()
        top = self._undo_stack[-1] if self._undo_stack else None
        # coalescência: mudanças consecutivas do mesmo parâmetro dentro da
        # janela viram uma única entrada (mantém o `old` original)
        if (isinstance(top, _SetParam) and top.name == name
                and now - self._last_param_push <= self.coalesce_window):
            top.new = new
            top.label = f"parâmetro {name} = {new!r}"
            self._redo_stack.clear()
        else:
            self._push(_SetParam(name, old, new))
        self._last_param_push = now

    def undo(self) -> bool:
        """Desfaz a última mutação (parâmetro ou edição de histórico)."""
        if not self._undo_stack:
            return False
        cmd = self._undo_stack.pop()
        self._replaying = True
        try:
            cmd.undo(self)
        finally:
            self._replaying = False
        self._redo_stack.append(cmd)
        logger.info("[%s] desfeito: %s", self.name, cmd.label)
        return True

    def redo(self) -> bool:
        """Refaz a última mutação desfeita."""
        if not self._redo_stack:
            return False
        cmd = self._redo_stack.pop()
        self._replaying = True
        try:
            cmd.do(self)
        finally:
            self._replaying = False
        self._undo_stack.append(cmd)
        logger.info("[%s] refeito: %s", self.name, cmd.label)
        return True

    @property
    def undo_labels(self) -> List[str]:
        return [c.label for c in self._undo_stack]

    # ---------------------------------------------------------- invalidação
    def _on_params_changed(self, changed: Set[str]) -> None:
        self._dirty_params |= changed
        self._invalidate_mesh()

    def _invalidate_from(self, index: int) -> None:
        """Edição estrutural do histórico: tudo a partir de ``index`` fica
        obsoleto (o encadeamento muda o ``prev`` das features seguintes)."""
        self._first_dirty_feature = min(self._first_dirty_feature, index)
        for f in self.features[index:]:
            if f.state != "suppressed":
                f.state = "stale"
        self._all_dirty = self._all_dirty or self._body_fn is not None
        self._invalidate_mesh()

    def _invalidate_mesh(self) -> None:
        self._mesh = None  # a malha atual não reflete mais o modelo

    # ---------------------------------------------------------- regeneração
    def rebuild_tree(self) -> Optional[SDF]:
        """
        Regenera APENAS a subárvore afetada (Fase 1.3) e devolve o corpo.

        Uma feature é reconstruída se: (a) tudo está sujo (primeira vez /
        mudança estrutural), (b) leu algum parâmetro cujo valor mudou, ou
        (c) alguma feature anterior foi reconstruída (o ``prev`` mudou).
        As demais reutilizam o sólido do rebuild anterior.
        """
        t0 = time.perf_counter()
        rebuilt = 0
        prev: Optional[SDF] = None
        upstream_changed = False

        for i, f in enumerate(self.features):
            if f.state == "suppressed":
                continue
            needs = (
                self._all_dirty
                or f.solid is None
                or f.state in ("stale", "error")
                or i >= self._first_dirty_feature
                or bool(f.reads & self._dirty_params)
                or (upstream_changed and f._accepts_prev())
            )
            if needs:
                try:
                    with self.params.tracking() as reads:
                        if f._accepts_prev():
                            solid = f.build(self.params, prev)
                        else:
                            solid = f.build(self.params)
                        # dimensões preguiçosas (lambda: P["x"]) só leem o
                        # parâmetro quando avaliadas; a assinatura resolve
                        # todas elas, capturando as leituras da geometria.
                        if solid is not None:
                            solid.signature()
                    f.reads = reads
                    f.solid = solid
                    f.state = "ok"
                    f.error = None
                    rebuilt += 1
                    upstream_changed = True
                except Exception as exc:  # o histórico sobrevive ao erro
                    f.state = "error"
                    f.error = exc
                    logger.warning("[%s] feature %r falhou: %s — encadeamento "
                                   "segue com o sólido anterior",
                                   self.name, f.name, exc)
                    continue
            if f.solid is not None:
                prev = f.solid

        # corpo final: set_body (compat) ou última feature encadeada
        if self._body_fn is not None:
            if (self._all_dirty or self.body is None or upstream_changed
                    or bool(self._body_reads & self._dirty_params)):
                with self.params.tracking() as reads:
                    self.body = self._body_fn(self.params)
                    if self.body is not None:
                        self.body.signature()   # captura leituras preguiçosas
                self._body_reads = reads
                rebuilt += 1
        else:
            self.body = prev

        self._dirty_params.clear()
        self._all_dirty = False
        self._first_dirty_feature = len(self.features)

        dt = (time.perf_counter() - t0) * 1e3
        total = len([f for f in self.features if f.state != "suppressed"])
        logger.debug("[%s] árvore: %d/%d features reconstruídas em %.1f ms "
                     "(cache: %d reutilizadas)",
                     self.name, rebuilt, total, dt, total - min(rebuilt, total))
        self._last_tree_stats = (rebuilt, total, dt)
        return self.body

    def get_mesh(self, resolution: Optional[int] = None) -> Mesh:
        """
        Malha do corpo, gerada preguiçosamente (Fase 1.4).

        A árvore é regenerada (com cache) e a malha só é recalculada se a
        ASSINATURA geométrica do corpo mudou para a resolução pedida —
        mudar um parâmetro e voltar ao valor original, ou reconstruir sem
        mudanças, reutiliza a malha em cache.
        """
        resolution = int(resolution or self.preview_resolution)
        self.rebuild_tree()
        if self.body is None:
            raise RuntimeError(
                "Nenhum corpo definido — chame set_body() ou add_feature().")

        sig = self.body.signature()
        key = (resolution, sig)
        cached = self._mesh_cache.get(key)
        if cached is not None:
            logger.debug("[%s] malha %d^3: cache hit (assinatura %s...)",
                         self.name, resolution, sig[:8])
            self._mesh_cache[key] = self._mesh_cache.pop(key)  # move p/ fim
            self._mesh, self._mesh_resolution = cached, resolution
            return cached

        t0 = time.perf_counter()
        mesh = generate_mesh(self.body, resolution=resolution)
        dt = (time.perf_counter() - t0) * 1e3
        self._mesh_cache[key] = mesh
        while len(self._mesh_cache) > self._mesh_cache_capacity:
            self._mesh_cache.pop(next(iter(self._mesh_cache)))
        self._mesh, self._mesh_resolution = mesh, resolution

        st = mesh.stats
        extra = (f" — {st.voxels:,} voxels, {st.n_triangles:,} triângulos, "
                 f"~{st.peak_memory_mb:.0f} MB de pico" if st else "")
        rb, total, tree_ms = getattr(self, "_last_tree_stats", (0, 0, 0.0))
        logger.info("[%s] árvore (%d/%d features) em %.1f ms, "
                    "malha (%d³ eq.) em %.0f ms%s",
                    self.name, rb, max(total, 1), tree_ms, resolution, dt, extra)
        return mesh

    def rebuild(self, resolution: Optional[int] = None,
                verbose: bool = True) -> Mesh:
        """Regenera árvore + malha (API compatível com a versão anterior;
        internamente delega ao cache/lazy meshing). ``verbose=True`` garante
        que os logs INFO apareçam no console, como o ``print`` antigo."""
        if verbose:
            enable_console_logging()
        return self.get_mesh(resolution or self.preview_resolution)

    @property
    def mesh(self) -> Optional[Mesh]:
        """Última malha gerada (compatibilidade: ``doc.mesh`` após rebuild)."""
        return self._mesh

    def _ensure_mesh(self, resolution: int) -> Mesh:
        return self.get_mesh(resolution)

    # ----------------------------------------------------------- exportação
    def export(self, path: str, resolution: Optional[int] = None) -> None:
        """Exporta despachando pela extensão (.stl/.obj/.ply/.glb/.3mf/
        .step/.iges — Fase 4.2). Para STEP/IGES usa a ponte com o
        núcleo-K, preferindo a rota ANALÍTICA exata quando a árvore SDF
        mapeia para o B-Rep (ver :mod:`parametricus.brep`)."""
        import os as _os
        ext = _os.path.splitext(path)[1].lower()
        if ext in (".step", ".stp"):
            self.export_step(path, resolution=resolution)
            return
        if ext in (".iges", ".igs"):
            self.export_iges(path, resolution=resolution)
            return
        from .io import export_mesh
        mesh = self._ensure_mesh(resolution or self.export_resolution)
        export_mesh(mesh, path)
        logger.info("[%s] exportado em: %s", self.name, path)

    def export_step(self, path: str, resolution: Optional[int] = None,
                    deflection: float = 0.02) -> str:
        """STEP AP214 via núcleo-K: analítico exato quando a árvore SDF
        é mapeável (primitivas + similaridades), facetado caso
        contrário. Devolve o modo usado.

        Assinatura espelha ``export_stl(path, resolution)``: o 2º
        argumento posicional é a RESOLUÇÃO (usada só na rota de malha);
        ``deflection`` controla o facetamento das rotas B-Rep."""
        from .brep import export_document_step
        return export_document_step(self, path, deflection=deflection,
                                    resolution=resolution)

    def export_iges(self, path: str, resolution: Optional[int] = None,
                    deflection: float = 0.02) -> str:
        """IGES 5.3 wireframe (arestas do B-Rep) via núcleo-K; mesmo
        contrato de ``export_step``."""
        from .brep import export_document_iges
        return export_document_iges(self, path, deflection=deflection,
                                    resolution=resolution)

    def export_stl(self, path: str, resolution: Optional[int] = None) -> None:
        mesh = self._ensure_mesh(resolution or self.export_resolution)
        mesh.save_stl(path, name=self.name.encode()[:80])
        logger.info("[%s] STL salvo em: %s", self.name, path)

    def export_obj(self, path: str, resolution: Optional[int] = None) -> None:
        self._ensure_mesh(resolution or self.export_resolution).save_obj(path)
        logger.info("[%s] OBJ salvo em: %s", self.name, path)

    def export_ply(self, path: str, resolution: Optional[int] = None) -> None:
        self._ensure_mesh(resolution or self.export_resolution).save_ply(path)

    # -------------------------------------------------------------- material
    def mass_properties(self, resolution: Optional[int] = None) -> dict:
        """Massa (g), centroide e tensor de inércia (g·mm²) segundo o
        material do documento (padrão: densidade 1 g/cm³)."""
        mesh = self._ensure_mesh(resolution or self.preview_resolution)
        density = (self.material.density_g_mm3 if self.material
                   else 1.0e-3)
        props = mesh.mass_properties(density)
        props["material"] = self.material.name if self.material else "—"
        return props

    # ------------------------------------------------------------ relatório
    def report(self, resolution: Optional[int] = None) -> str:
        mesh = self._ensure_mesh(resolution or self.preview_resolution)
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
            marks = {"ok": " ", "suppressed": "s", "error": "!", "stale": "~"}
            for i, f in enumerate(self.features, 1):
                desc = f" — {f.description}" if f.description else ""
                reads = (f" [{', '.join(sorted(f.reads))}]" if f.reads else "")
                lines.append(f"  {i:2d}.{marks.get(f.state, '?')} "
                             f"{f.name}{desc}{reads}")
            if any(f.state == "suppressed" for f in self.features):
                lines.append("      (s = suprimida, ! = erro)")
        lines += ["", " PROPRIEDADES DO SÓLIDO", " " + "-" * 58,
                  mesh.report()]
        if self.material is not None:
            props = mesh.mass_properties(self.material.density_g_mm3)
            pm = props["principal_moments"]
            lines += [
                "", f" MATERIAL: {self.material.name} "
                    f"({self.material.density_g_cm3:g} g/cm³)",
                " " + "-" * 58,
                f"  Massa .............. {props['mass']:,.2f} g",
                f"  Momentos principais  {pm[0]:,.1f}, {pm[1]:,.1f}, "
                f"{pm[2]:,.1f} g·mm²",
            ]
        lines += ["=" * 60]
        return "\n".join(lines)

    def show(self, resolution: Optional[int] = None, **kwargs) -> None:
        """Abre o visualizador 3D (usa a resolução de preview por padrão)."""
        from .viewer import show_mesh
        show_mesh(self._ensure_mesh(resolution or self.preview_resolution),
                  title=self.name, **kwargs)
