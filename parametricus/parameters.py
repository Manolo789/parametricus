"""
parametricus.parameters
==================
Sistema de parâmetros com suporte a expressões matemáticas e
resolução automática de dependências (grafo acíclico dirigido).

Exemplo:
    >>> p = ParameterSet()
    >>> p.define("largura", 40)
    >>> p.define("altura", "largura / 2")      # expressão dependente
    >>> p.define("raio", "min(largura, altura) * 0.1")
    >>> p["altura"]
    20.0
    >>> p.set("largura", 100)                  # tudo é reavaliado
    >>> p["altura"]
    50.0
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Set, Union

Number = Union[int, float]

# Funções permitidas dentro de expressões de parâmetros
_SAFE_FUNCS: Dict[str, Callable] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2, "sqrt": math.sqrt, "abs": abs,
    "min": min, "max": max, "floor": math.floor, "ceil": math.ceil,
    "round": round, "radians": math.radians, "degrees": math.degrees,
    "log": math.log, "exp": math.exp, "pow": pow,
}
_SAFE_CONSTS: Dict[str, float] = {"pi": math.pi, "tau": math.tau, "e": math.e}

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ParameterError(Exception):
    """Erro de definição ou avaliação de parâmetro."""


@dataclass
class Parameter:
    name: str
    expression: Union[str, Number]
    value: Optional[float] = None
    unit: str = "mm"
    description: str = ""
    depends_on: Set[str] = field(default_factory=set)

    @property
    def is_expression(self) -> bool:
        return isinstance(self.expression, str)


class _SafeEval(ast.NodeVisitor):
    """Avaliador de expressões restrito (sem acesso a builtins/imports)."""

    _ALLOWED = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
        ast.Call, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div,
        ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
        ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
        ast.IfExp, ast.BoolOp, ast.And, ast.Or, ast.Tuple,
    )

    def __init__(self, names: Dict[str, float]):
        self.names = names

    def eval(self, expr: str) -> float:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise ParameterError(f"Expressão inválida: {expr!r} ({exc})") from exc
        for node in ast.walk(tree):
            if not isinstance(node, self._ALLOWED):
                raise ParameterError(
                    f"Construção não permitida em expressão: {type(node).__name__}"
                )
        return float(self._eval(tree.body))

    def _eval(self, node):
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ParameterError(f"Constante não numérica: {node.value!r}")
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.names:
                return self.names[node.id]
            if node.id in _SAFE_CONSTS:
                return _SAFE_CONSTS[node.id]
            raise ParameterError(f"Nome desconhecido em expressão: {node.id!r}")
        if isinstance(node, ast.BinOp):
            a, b = self._eval(node.left), self._eval(node.right)
            op = type(node.op)
            return {
                ast.Add: lambda: a + b, ast.Sub: lambda: a - b,
                ast.Mult: lambda: a * b, ast.Div: lambda: a / b,
                ast.FloorDiv: lambda: a // b, ast.Mod: lambda: a % b,
                ast.Pow: lambda: a ** b,
            }[op]()
        if isinstance(node, ast.UnaryOp):
            v = self._eval(node.operand)
            return -v if isinstance(node.op, ast.USub) else +v
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCS:
                raise ParameterError("Apenas funções matemáticas básicas são permitidas.")
            args = [self._eval(a) for a in node.args]
            return _SAFE_FUNCS[node.func.id](*args)
        if isinstance(node, ast.IfExp):
            return self._eval(node.body) if self._eval(node.test) else self._eval(node.orelse)
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval(comp)
                ok = {
                    ast.Lt: left < right, ast.LtE: left <= right,
                    ast.Gt: left > right, ast.GtE: left >= right,
                    ast.Eq: left == right, ast.NotEq: left != right,
                }[type(op)]
                if not ok:
                    return 0.0
                left = right
            return 1.0
        if isinstance(node, ast.BoolOp):
            vals = [self._eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return 1.0 if all(vals) else 0.0
            return 1.0 if any(vals) else 0.0
        raise ParameterError(f"Nó não suportado: {type(node).__name__}")


class ParameterSet:
    """
    Conjunto de parâmetros nomeados com reavaliação automática.

    Cada parâmetro pode ser um número literal ou uma expressão que
    referencia outros parâmetros. Ao alterar qualquer valor, todos os
    dependentes são recalculados em ordem topológica.
    """

    def __init__(self) -> None:
        self._params: Dict[str, Parameter] = {}
        self._listeners: List[Callable] = []
        # Fase 1.3 — rastreamento de leitura: enquanto um contexto tracking()
        # está ativo, cada __getitem__ registra o nome lido. É assim que o
        # Document descobre quais parâmetros cada feature consome, sem mudar
        # a API de lambdas (`lambda: P["x"]`).
        self._tracking_stack: List[Set[str]] = []
        # Fase 2.2 — hook de mutação (nome, expr_antiga, expr_nova), usado
        # pelo Document para registrar comandos de Undo/Redo.
        self._mutate_hooks: List[Callable[[str, Union[str, Number], Union[str, Number]], None]] = []

    # ------------------------------------------------------------------ API
    def define(self, name: str, expression: Union[str, Number],
               unit: str = "mm", description: str = "") -> Parameter:
        if not _IDENT_RE.fullmatch(name):
            raise ParameterError(f"Nome de parâmetro inválido: {name!r}")
        if name in _SAFE_FUNCS or name in _SAFE_CONSTS:
            raise ParameterError(f"Nome reservado: {name!r}")
        p = Parameter(name=name, expression=expression, unit=unit,
                      description=description)
        p.depends_on = self._extract_deps(expression)
        self._params[name] = p
        self._recompute(changed_root=name)
        return p

    def set(self, name: str, expression: Union[str, Number]) -> None:
        """Altera o valor/expressão de um parâmetro e regenera dependentes."""
        if name not in self._params:
            raise ParameterError(f"Parâmetro inexistente: {name!r}")
        p = self._params[name]
        old_expression = p.expression
        if expression == old_expression:
            return  # nada mudou — evita rebuilds/invalidações desnecessários
        p.expression = expression
        p.depends_on = self._extract_deps(expression)
        try:
            self._recompute(changed_root=name)
        except ParameterError:
            # reverte para manter o conjunto consistente
            p.expression = old_expression
            p.depends_on = self._extract_deps(old_expression)
            self._recompute()
            raise
        for hook in self._mutate_hooks:
            hook(name, old_expression, expression)

    def __getitem__(self, name: str) -> float:
        if name not in self._params:
            raise ParameterError(f"Parâmetro inexistente: {name!r}")
        if self._tracking_stack:
            for reads in self._tracking_stack:
                reads.add(name)
        return self._params[name].value

    def __contains__(self, name: str) -> bool:
        return name in self._params

    def names(self) -> List[str]:
        return list(self._params)

    def as_dict(self) -> Dict[str, float]:
        return {n: p.value for n, p in self._params.items()}

    def on_change(self, callback: Callable) -> None:
        """
        Registra callback chamado sempre que os valores mudam.

        O callback pode ter duas assinaturas:
        - ``cb()`` — compatibilidade com versões anteriores;
        - ``cb(changed: set[str])`` — recebe o conjunto de nomes cujos
          valores efetivamente mudaram (Fase 1.3), permitindo invalidação
          seletiva no Document.
        """
        self._listeners.append(callback)

    def on_mutate(self, hook: Callable[[str, Union[str, Number], Union[str, Number]], None]) -> None:
        """Registra hook ``(nome, expr_antiga, expr_nova)`` para cada
        ``set()`` bem-sucedido — base do Undo/Redo do Document."""
        self._mutate_hooks.append(hook)

    @contextlib.contextmanager
    def tracking(self) -> Iterator[Set[str]]:
        """
        Context manager que registra os parâmetros lidos no bloco.

            with P.tracking() as reads:
                solid = feature.build(P)
            # reads == {"L", "esp", ...}

        Suporta aninhamento (cada contexto recebe seu próprio conjunto).
        """
        reads: Set[str] = set()
        self._tracking_stack.append(reads)
        try:
            yield reads
        finally:
            self._tracking_stack.pop()

    def dependents_of(self, name: str) -> Set[str]:
        """Fecho transitivo dos parâmetros que dependem de ``name``
        (inclui o próprio ``name``)."""
        reverse: Dict[str, Set[str]] = {n: set() for n in self._params}
        for n, p in self._params.items():
            for dep in p.depends_on:
                if dep in reverse:
                    reverse[dep].add(n)
        result: Set[str] = set()
        stack = [name]
        while stack:
            n = stack.pop()
            if n in result:
                continue
            result.add(n)
            stack.extend(reverse.get(n, ()))
        return result

    def table(self) -> str:
        """Tabela formatada (útil para CLI)."""
        rows = [("PARÂMETRO", "VALOR", "EXPRESSÃO", "DESCRIÇÃO")]
        for p in self._params.values():
            expr = str(p.expression) if p.is_expression else "—"
            rows.append((p.name, f"{p.value:g} {p.unit}", expr, p.description))
        widths = [max(len(r[i]) for r in rows) for i in range(4)]
        lines = []
        for i, r in enumerate(rows):
            lines.append("  ".join(c.ljust(w) for c, w in zip(r, widths)))
            if i == 0:
                lines.append("-" * (sum(widths) + 6))
        return "\n".join(lines)

    # ------------------------------------------------------------- internos
    @staticmethod
    def _extract_deps(expression: Union[str, Number]) -> Set[str]:
        if not isinstance(expression, str):
            return set()
        idents = set(_IDENT_RE.findall(expression))
        return {i for i in idents if i not in _SAFE_FUNCS and i not in _SAFE_CONSTS}

    def _topo_order(self) -> List[str]:
        """Ordenação topológica (detecta ciclos)."""
        order: List[str] = []
        state: Dict[str, int] = {}  # 0=novo, 1=visitando, 2=pronto

        def visit(n: str, chain: List[str]):
            st = state.get(n, 0)
            if st == 2:
                return
            if st == 1:
                ciclo = " -> ".join(chain + [n])
                raise ParameterError(f"Dependência circular: {ciclo}")
            state[n] = 1
            for dep in self._params[n].depends_on:
                if dep not in self._params:
                    raise ParameterError(
                        f"Parâmetro {n!r} depende de {dep!r}, que não existe."
                    )
                visit(dep, chain + [n])
            state[n] = 2
            order.append(n)

        for name in self._params:
            visit(name, [])
        return order

    def _recompute(self, changed_root: Optional[str] = None) -> None:
        old_values = {n: p.value for n, p in self._params.items()}
        values: Dict[str, float] = {}
        for name in self._topo_order():
            p = self._params[name]
            if p.is_expression:
                p.value = _SafeEval(values).eval(p.expression)
            else:
                p.value = float(p.expression)
            values[name] = p.value
        # conjunto de parâmetros cujo VALOR mudou; inclui a raiz da mudança
        # mesmo que o valor final coincida (a expressão pode ter mudado).
        changed: Set[str] = {
            n for n, v in values.items()
            if old_values.get(n) is None or v != old_values[n]
        }
        if changed_root is not None:
            changed.add(changed_root)
        for cb in self._listeners:
            try:
                sig = inspect.signature(cb)
                takes_arg = len(sig.parameters) >= 1
            except (TypeError, ValueError):
                takes_arg = False
            if takes_arg:
                cb(set(changed))
            else:
                cb()
