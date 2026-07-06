"""
parametricus.constraints
========================
Restrições de esboço (Fase 2.3 do roadmap): entidades 2D com graus de
liberdade explícitos, restrições geométricas/dimensionais como resíduos
``f(q) = 0`` e solver de mínimos quadrados não linear (Levenberg-Marquardt
em NumPy puro — sem novas dependências).

Restrições implementadas: coincidência, horizontal, vertical, paralelismo,
perpendicularidade, tangência, simetria, fixação e as dimensionais
(distância, comprimento, ângulo, raio) — que aceitam Scalars preguiçosos
(``lambda: P["L"]``), ligando o solver ao sistema paramétrico existente.

Exemplo — retângulo paramétrico totalmente restrito:

    sk = ConstrainedSketch()
    a = sk.point(0, 0);  b = sk.point(10, 0)
    c = sk.point(10, 5); d = sk.point(0, 5)
    ab, bc = sk.line(a, b), sk.line(b, c)
    cd, da = sk.line(c, d), sk.line(d, a)
    sk.fix(a)
    sk.horizontal(ab); sk.vertical(bc)
    sk.parallel(ab, cd); sk.perpendicular(ab, da)
    sk.length(ab, lambda: P["L"])      # dimensão dirigida por parâmetro
    sk.length(bc, lambda: P["H"])
    print(sk.dof_report())             # deve indicar 0 DOF restantes

    perfil = sk.profile([a, b, c, d])  # PolygonProfile que RE-RESOLVE o
    corpo = Extrude(perfil, 10)        # esboço a cada rebuild paramétrico
"""

from __future__ import annotations


from typing import Callable, List, Optional, Sequence, Tuple, Union

import numpy as np

from ._log import logger
from .sketch import PolygonProfile
from .types import Scalar, resolve_scalar as _val


def _cross2(a, b) -> float:
    """Produto vetorial 2D escalar (np.cross 2D foi deprecado no NumPy 2)."""
    return float(a[0] * b[1] - a[1] * b[0])


# ---------------------------------------------------------------- entidades
class Point2D:
    """Ponto do esboço: 2 graus de liberdade (x, y), salvo se fixado."""

    def __init__(self, sketch: "ConstrainedSketch", x: float, y: float,
                 fixed: bool = False):
        self._sketch = sketch
        self.x0, self.y0 = float(x), float(y)   # chute inicial
        self.fixed = fixed
        self.index: int = -1                     # posição em q (se livre)

    @property
    def xy(self) -> np.ndarray:
        """Posição resolvida (após o último solve)."""
        return self._sketch._point_xy(self)

    def __repr__(self) -> str:
        x, y = self.xy
        return f"Point2D({x:.4g}, {y:.4g}{', fixed' if self.fixed else ''})"


class Line2D:
    """Segmento entre dois pontos do esboço."""

    def __init__(self, p1: Point2D, p2: Point2D):
        self.p1, self.p2 = p1, p2

    def direction(self) -> np.ndarray:
        d = self.p2.xy - self.p1.xy
        return d

    def length(self) -> float:
        return float(np.linalg.norm(self.direction()))


class Circle2D:
    """Círculo: centro (Point2D) + raio (1 DOF adicional)."""

    def __init__(self, sketch: "ConstrainedSketch", center: Point2D,
                 radius: float):
        self._sketch = sketch
        self.center = center
        self.r0 = float(radius)
        self.index: int = -1                     # posição do raio em q

    @property
    def radius(self) -> float:
        return self._sketch._circle_radius(self)


# --------------------------------------------------------------- restrições
class _Constraint:
    """Restrição = resíduos que devem zerar. ``arity`` = nº de equações."""
    label = "restrição"
    arity = 1

    def residual(self, sk: "ConstrainedSketch") -> np.ndarray:
        raise NotImplementedError


class _FnConstraint(_Constraint):
    def __init__(self, label: str, arity: int,
                 fn: Callable[[], Sequence[float]]):
        self.label, self.arity, self._fn = label, arity, fn

    def residual(self, sk):
        return np.atleast_1d(np.asarray(self._fn(), dtype=np.float64))


class SolverError(RuntimeError):
    """O solver não convergiu (esboço inconsistente ou sobre-restrito)."""


# ------------------------------------------------------------------- sketch
class ConstrainedSketch:
    """Esboço 2D com restrições e solver (Fase 2.3)."""

    def __init__(self):
        self.points: List[Point2D] = []
        self.circles: List[Circle2D] = []
        self.constraints: List[_Constraint] = []
        self._solution: Optional[np.ndarray] = None
        self._solved_key: Optional[str] = None

    # ------------------------------------------------------------ entidades
    def point(self, x: float, y: float, fixed: bool = False) -> Point2D:
        p = Point2D(self, x, y, fixed)
        self.points.append(p)
        self._invalidate()
        return p

    def line(self, p1: Point2D, p2: Point2D) -> Line2D:
        return Line2D(p1, p2)

    def circle(self, center: Point2D, radius: float) -> Circle2D:
        c = Circle2D(self, center, radius)
        self.circles.append(c)
        self._invalidate()
        return c

    # ----------------------------------------------------------- variáveis q
    def _assign_indices(self) -> int:
        n = 0
        for p in self.points:
            if not p.fixed:
                p.index = n
                n += 2
            else:
                p.index = -1
        for c in self.circles:
            c.index = n
            n += 1
        return n

    def _initial_q(self, n: int) -> np.ndarray:
        q = np.empty(n)
        for p in self.points:
            if p.index >= 0:
                q[p.index:p.index + 2] = (p.x0, p.y0)
        for c in self.circles:
            q[c.index] = c.r0
        return q

    def _point_xy(self, p: Point2D) -> np.ndarray:
        if p.fixed or p.index < 0 or self._solution is None:
            return np.array([p.x0, p.y0])
        return self._solution[p.index:p.index + 2].copy()

    def _circle_radius(self, c: Circle2D) -> float:
        if self._solution is None or c.index < 0:
            return c.r0
        return float(self._solution[c.index])

    def _invalidate(self) -> None:
        self._solution = None
        self._solved_key = None

    # ---------------------------------------------------------- restrições
    def _add(self, label: str, arity: int,
             fn: Callable[[], Sequence[float]]) -> None:
        self.constraints.append(_FnConstraint(label, arity, fn))
        self._invalidate()

    def fix(self, p: Point2D) -> None:
        """Fixa o ponto na posição inicial (remove 2 DOF)."""
        p.fixed = True
        self._invalidate()

    def coincident(self, a: Point2D, b: Point2D) -> None:
        """Coincidência: a == b (2 equações)."""
        self._add("coincidência", 2, lambda: a.xy - b.xy)

    def horizontal(self, line: Line2D) -> None:
        """Reta horizontal: y1 == y2."""
        self._add("horizontal", 1,
                  lambda: [line.p1.xy[1] - line.p2.xy[1]])

    def vertical(self, line: Line2D) -> None:
        """Reta vertical: x1 == x2."""
        self._add("vertical", 1,
                  lambda: [line.p1.xy[0] - line.p2.xy[0]])

    def parallel(self, l1: Line2D, l2: Line2D) -> None:
        """Paralelismo: cross(d1, d2) == 0."""
        self._add("paralelismo", 1, lambda: [_cross2(l1.direction(), l2.direction())])

    def perpendicular(self, l1: Line2D, l2: Line2D) -> None:
        """Perpendicularidade: dot(d1, d2) == 0."""
        self._add("perpendicularidade", 1, lambda: [float(
            l1.direction() @ l2.direction())])

    def tangent(self, line: Line2D, circle: Circle2D) -> None:
        """Tangência reta-círculo: dist(centro, reta) == raio."""
        def res():
            p1 = line.p1.xy
            d = line.direction()
            L = np.linalg.norm(d)
            if L < 1e-12:
                return [1.0]
            dist = abs(_cross2(d, circle.center.xy - p1)) / L
            return [dist - circle.radius]
        self._add("tangência", 1, res)

    def symmetric(self, a: Point2D, b: Point2D, axis: Line2D) -> None:
        """Simetria de a e b em relação à reta-eixo (2 equações):
        ponto médio sobre o eixo + segmento ab perpendicular ao eixo."""
        def res():
            d = axis.direction()
            L = np.linalg.norm(d)
            if L < 1e-12:
                return [1.0, 1.0]
            d = d / L
            mid = (a.xy + b.xy) / 2.0 - axis.p1.xy
            ab = b.xy - a.xy
            return [_cross2(d, mid),           # médio sobre o eixo
                    float(d @ ab)]             # ab perpendicular ao eixo
        self._add("simetria", 2, res)

    # dimensionais (aceitam Scalar preguiçoso -> integração com ParameterSet)
    def distance(self, a: Point2D, b: Point2D, value: Scalar) -> None:
        """Distância dimensional entre dois pontos."""
        self._add("distância", 1, lambda: [
            float(np.linalg.norm(a.xy - b.xy)) - _val(value)])

    def length(self, line: Line2D, value: Scalar) -> None:
        """Comprimento dimensional de um segmento."""
        self.distance(line.p1, line.p2, value)

    def angle(self, l1: Line2D, l2: Line2D, degrees: Scalar) -> None:
        """Ângulo dimensional entre duas retas (graus)."""
        def res():
            d1, d2 = l1.direction(), l2.direction()
            ang = np.degrees(np.arctan2(_cross2(d1, d2),
                                        float(d1 @ d2)))
            target = _val(degrees)
            diff = (ang - target + 180.0) % 360.0 - 180.0
            return [diff]
        self._add("ângulo", 1, res)

    def radius(self, circle: Circle2D, value: Scalar) -> None:
        """Raio dimensional de um círculo."""
        self._add("raio", 1, lambda: [circle.radius - _val(value)])

    # --------------------------------------------------------------- solver
    def _residuals(self, q: np.ndarray) -> np.ndarray:
        self._solution = q
        if not self.constraints:
            return np.zeros(0)
        return np.concatenate([c.residual(self) for c in self.constraints])

    def _jacobian(self, q: np.ndarray, r0: np.ndarray,
                  eps: float = 1e-7) -> np.ndarray:
        J = np.empty((len(r0), len(q)))
        for j in range(len(q)):
            qj = q.copy()
            h = eps * max(1.0, abs(q[j]))
            qj[j] += h
            J[:, j] = (self._residuals(qj) - r0) / h
        return J

    def solve(self, tol: float = 1e-20, max_iter: int = 200) -> np.ndarray:
        """
        Resolve as restrições por Levenberg-Marquardt (Jacobiano numérico).

        Retorna o vetor de incógnitas; as posições ficam acessíveis em
        ``Point2D.xy`` / ``Circle2D.radius``. Lança :class:`SolverError`
        se não convergir (esboço inconsistente).
        """
        n = self._assign_indices()
        q = self._initial_q(n)
        if n == 0 or not self.constraints:
            self._solution = q
            return q

        lam = 1e-3
        r = self._residuals(q)
        cost = float(r @ r)
        for it in range(max_iter):
            if cost < tol:
                break
            J = self._jacobian(q, r)
            JtJ = J.T @ J
            g = J.T @ r
            for _ in range(30):                 # ajuste do amortecimento
                try:
                    step = np.linalg.solve(
                        JtJ + lam * np.diag(np.maximum(np.diag(JtJ), 1e-12)),
                        -g)
                except np.linalg.LinAlgError:
                    lam *= 10.0
                    continue
                r_new = self._residuals(q + step)
                cost_new = float(r_new @ r_new)
                if cost_new < cost:             # aceita o passo
                    q = q + step
                    r, cost = r_new, cost_new
                    lam = max(lam / 3.0, 1e-12)
                    break
                lam *= 10.0
            else:
                break
        self._solution = q
        if cost > 1e-8:
            raise SolverError(
                f"Esboço não convergiu (custo residual {cost:.3e}) — "
                f"verifique restrições conflitantes/sobre-restrição.")
        logger.debug("sketch resolvido em %d iterações (custo %.2e)",
                     it + 1, cost)
        return q

    # ------------------------------------------------------------ diagnóstico
    def dof(self) -> int:
        """Graus de liberdade restantes (variáveis - posto do Jacobiano).
        0 = totalmente restrito; >0 = sub-restrito."""
        n = self._assign_indices()
        if n == 0:
            return 0
        q = self._solution if (self._solution is not None
                               and len(self._solution) == n) \
            else self._initial_q(n)
        r = self._residuals(q)
        if len(r) == 0:
            return n
        J = self._jacobian(q, r)
        rank = int(np.linalg.matrix_rank(J, tol=1e-8))
        return n - rank

    def dof_report(self) -> str:
        n = self._assign_indices()
        m = sum(c.arity for c in self.constraints)
        d = self.dof()
        status = ("totalmente restrito" if d == 0
                  else f"sub-restrito ({d} DOF livres)")
        redundant = m - (n - d)
        extra = (f", {redundant} equação(ões) redundante(s)"
                 if redundant > 0 else "")
        return f"{n} variáveis, {m} equações de restrição -> {status}{extra}"

    # ------------------------------------------------------- ponte para SDF
    def profile(self, loop: Sequence[Point2D]) -> PolygonProfile:
        """
        Perfil poligonal pelo ciclo de pontos dado, RE-RESOLVIDO a cada
        avaliação: mudou um parâmetro dimensional, os resíduos deixam de
        zerar e o solver roda de novo — a geometria acompanha o parâmetro.
        Se nada mudou (resíduos ~0), a solução anterior é reutilizada.
        """
        def verts():
            n = self._assign_indices()
            need = self._solution is None or len(self._solution) != n
            if not need:
                r = self._residuals(self._solution)
                need = len(r) > 0 and float(np.max(np.abs(r))) > 1e-8
            if need:
                self.solve()
            return np.stack([p.xy for p in loop])
        return PolygonProfile(verts)
