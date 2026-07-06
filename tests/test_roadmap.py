"""Suíte de testes das melhorias do roadmap (executar: python tests/test_roadmap.py)."""
import math
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parametricus import (
    Box, ConstrainedSketch, Cylinder, Document, Extrude, MATERIALS, Mesh,
    ParameterSet, Sphere, bounding_box, distance_point, generate_mesh,
    import_mesh, section, slice_field,
)
from parametricus.sketch import PolygonProfile

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FALHOU: {label}"
    PASS += 1
    print(f"  ok  {label}")


# ------------------------------------------------------- Fase 1.3: parâmetros
print("\n[Fase 1.3] rastreamento e notificação seletiva de parâmetros")
P = ParameterSet()
P.define("L", 60)
P.define("esp", "L*0.2")
P.define("furo", "L/4")
P.define("solto", 5)

received = []
P.on_change(lambda changed: received.append(changed))
P.set("L", 100)
ok(received[-1] == {"L", "esp", "furo"},
   f"mudança em L notifica só dependentes: {received[-1]}")
P.set("solto", 7)
ok(received[-1] == {"solto"}, "mudança em 'solto' não arrasta os demais")
n_before = len(received)
P.set("solto", 7)
ok(len(received) == n_before, "set() com mesmo valor não notifica")

with P.tracking() as reads:
    _ = P["esp"] + P["furo"]
ok(reads == {"esp", "furo"}, f"tracking registra leituras: {reads}")
ok(P.dependents_of("L") == {"L", "esp", "furo"}, "dependents_of transitivo")

# ------------------------------------------- Fase 1.3/1.4: cache no documento
print("\n[Fase 1.3/1.4] cache inteligente e lazy meshing no Document")
doc = Document("Placa")
Q = doc.params
Q.define("L", 60)
Q.define("esp", 12)
Q.define("furo", 15)

builds = {"base": 0, "furo": 0}


def build_base(P):
    builds["base"] += 1
    return Box((lambda: P["L"], lambda: P["L"], lambda: P["esp"]))


def build_furo(P, prev):
    builds["furo"] += 1
    return prev - Cylinder(lambda: P["furo"] / 2, lambda: P["esp"] * 3)


doc.add_feature("Base", build_base)
doc.add_feature("Furo", build_furo)

doc.rebuild_tree()
ok(builds == {"base": 1, "furo": 1}, "primeiro rebuild constrói tudo")
ok(doc.body is not None, "corpo = última feature encadeada (sem set_body)")

Q.set("furo", 20)
doc.rebuild_tree()
ok(builds == {"base": 1, "furo": 2},
   "mudar 'furo' NÃO reconstrói a Base (subárvore afetada apenas)")

Q.set("L", 80)
doc.rebuild_tree()
ok(builds == {"base": 2, "furo": 3},
   "mudar 'L' reconstrói Base e, por encadeamento, Furo")

doc.rebuild_tree()
ok(builds == {"base": 2, "furo": 3}, "rebuild sem mudanças: cache total")

m1 = doc.get_mesh(48)
gen1 = m1.stats.total_time_s
m2 = doc.get_mesh(48)
ok(m2 is m1, "malha em cache reutilizada (mesma assinatura)")
Q.set("L", 90)
m3 = doc.get_mesh(48)
ok(m3 is not m1, "malha regenerada após mudança de parâmetro")
Q.set("L", 80)
m4 = doc.get_mesh(48)
ok(m4 is m1, "voltar ao valor original: cache por assinatura recupera a malha")

# --------------------------------------------------- Fase 2.1: histórico
print("\n[Fase 2.1] histórico de features editável")
vol_com_furo = doc.get_mesh(48).volume()
doc.suppress("Furo")
vol_sem_furo = doc.get_mesh(48).volume()
ok(vol_sem_furo > vol_com_furo, "suppress remove o furo do corpo")
doc.unsuppress("Furo")
ok(abs(doc.get_mesh(48).volume() - vol_com_furo) < 1e-6,
   "unsuppress restaura (e recupera a malha do cache)")

doc.edit_feature("Furo",
                 lambda P, prev: prev - Cylinder(lambda: P["furo"], 99))
vol_furo_maior = doc.get_mesh(48).volume()
ok(vol_furo_maior < vol_com_furo, "edit_feature altera a geometria")

fail = Document("comErro")
fail.params.define("r", 5)
fail.add_feature("Boa", lambda P: Sphere(lambda: P["r"]))
fail.add_feature("Quebrada", lambda P, prev: (_ for _ in ()).throw(
    ValueError("boom")))
fail.rebuild_tree()
ok(fail.get_feature("Quebrada").state == "error"
   and fail.body is not None,
   "feature com erro não derruba o rebuild (corpo = sólido anterior)")

# --------------------------------------------------- Fase 2.2: undo/redo
print("\n[Fase 2.2] undo/redo")
d2 = Document("Undo")
d2.params.define("r", 10)
d2.add_feature("Esfera", lambda P: Sphere(lambda: P["r"]))
d2.params.set("r", 20)
ok(d2.params["r"] == 20, "set aplicado")
d2.undo()
ok(d2.params["r"] == 10, "undo de parâmetro")
d2.redo()
ok(d2.params["r"] == 20, "redo de parâmetro")
d2.suppress("Esfera")
ok(d2.get_feature("Esfera").suppressed, "suppress aplicado")
d2.undo()
ok(not d2.get_feature("Esfera").suppressed, "undo de suppress")
d2.remove_feature("Esfera")
ok(len(d2.features) == 0, "remove aplicado")
d2.undo()
ok(len(d2.features) == 1, "undo de remove restaura a feature")

# ------------------------------------------------ Fase 2.3: constraints
print("\n[Fase 2.3] sketch constraints")
PS = ParameterSet()
PS.define("W", 30)
PS.define("H", 12)

sk = ConstrainedSketch()
a = sk.point(0, 0)
b = sk.point(25, 1)      # chutes imprecisos de propósito
c = sk.point(26, 9)
d = sk.point(-1, 10)
ab, bc = sk.line(a, b), sk.line(b, c)
cd, da = sk.line(c, d), sk.line(d, a)
sk.fix(a)
sk.horizontal(ab)
sk.perpendicular(ab, bc)
sk.parallel(ab, cd)
sk.parallel(bc, da)
sk.length(ab, lambda: PS["W"])
sk.length(bc, lambda: PS["H"])
sk.solve()
ok(abs(ab.length() - 30) < 1e-6 and abs(bc.length() - 12) < 1e-6,
   f"retângulo resolvido: {ab.length():.6f} x {bc.length():.6f}")
ok(abs(ab.direction()[0]*cd.direction()[1] - ab.direction()[1]*cd.direction()[0]) < 1e-6,
   "paralelismo satisfeito")
ok(sk.dof() == 0, f"totalmente restrito ({sk.dof_report()})")

perfil = sk.profile([a, b, c, d])
solido = Extrude(perfil, 5)
v1 = generate_mesh(solido, resolution=64).volume()
PS.set("W", 40)                       # dimensão dirigida por parâmetro
v2 = generate_mesh(solido, resolution=64).volume()
ok(abs(v1 - 30 * 12 * 5) / (30 * 12 * 5) < 0.02,
   f"volume extrudado ~ W*H*e: {v1:.1f}")
ok(abs(v2 - 40 * 12 * 5) / (40 * 12 * 5) < 0.02,
   f"parâmetro re-resolve o esboço: {v2:.1f}")

# tangência + círculo
sk2 = ConstrainedSketch()
p1 = sk2.point(0, 0, fixed=True)
p2 = sk2.point(10, 0, fixed=True)
ln = sk2.line(p1, p2)
ctr = sk2.point(5, 3)
circ = sk2.circle(ctr, 2)
sk2.radius(circ, 4)
sk2.vertical(sk2.line(p1, ctr))
sk2.tangent(ln, circ)
sk2.solve()
ok(abs(circ.radius - 4) < 1e-6 and abs(abs(ctr.xy[1]) - 4) < 1e-6,
   f"tangência: centro a {ctr.xy[1]:.4f} da reta, r={circ.radius:.4f}")

# simetria
sk3 = ConstrainedSketch()
e1 = sk3.point(0, -5, fixed=True)
e2 = sk3.point(0, 5, fixed=True)
eixo = sk3.line(e1, e2)
pa = sk3.point(-3, 2, fixed=True)
pb = sk3.point(2, 1)
sk3.symmetric(pa, pb, eixo)
sk3.solve()
ok(np.allclose(pb.xy, [3, 2], atol=1e-6), f"simetria: {pb.xy}")

# ------------------------------------------------ Fase 3.1: vetorização
print("\n[Fase 3.1] equivalência numérica das otimizações")
rng = np.random.default_rng(1)


def ref_poly(v, p):
    n = len(v)
    dd = np.full(len(p), np.inf)
    sign = np.ones(len(p))
    j = n - 1
    for i in range(n):
        e = v[j] - v[i]
        w = p - v[i]
        t = np.clip((w @ e) / (e @ e), 0, 1)
        bb = w - np.outer(t, e)
        dd = np.minimum(dd, np.sum(bb * bb, axis=1))
        c1 = p[:, 1] >= v[i][1]
        c2 = p[:, 1] < v[j][1]
        c3 = e[0] * w[:, 1] > e[1] * w[:, 0]
        flip = (c1 & c2 & c3) | (~c1 & ~c2 & ~c3)
        sign = np.where(flip, -sign, sign)
        j = i
    return sign * np.sqrt(dd)


for nv in (3, 6, 17):
    angs = np.sort(rng.uniform(0, 2 * np.pi, nv))
    v = np.stack([rng.uniform(1, 3, nv) * np.cos(angs),
                  rng.uniform(1, 3, nv) * np.sin(angs)], 1)
    pts = rng.uniform(-4, 4, (3000, 2))
    ok(np.allclose(PolygonProfile(v).distance(pts), ref_poly(v, pts),
                   atol=1e-10), f"PolygonProfile otimizado == original (E={nv})")

s = Sphere(1.0)
arr = s.array_linear(6, (2.5, 0.5, 0))
chain = s
from parametricus.sdf import Translate
for i in range(1, 6):
    chain = chain | Translate(s, tuple(np.array([2.5, 0.5, 0.0]) * i))
pts3 = rng.uniform(-3, 17, (10000, 3))
ok(np.allclose(arr.distance(pts3), chain.distance(pts3), atol=1e-10),
   "array_linear (repetição de domínio) == cadeia de uniões")

# ------------------------------------------------ Fase 3.2/3.3: medições
print("\n[Fase 3.2/3.3] medições, seções e cortes")
cyl = Cylinder(10.0, 20.0)
ok(abs(distance_point(cyl, (15, 0, 0)) - 5.0) < 1e-9,
   "distance_point exata via SDF")
bb = bounding_box(cyl)
ok(np.allclose(bb.size, [20, 20, 20]), f"bounding_box: {bb.size}")

sec = section(cyl, origin=(0, 0, 0), normal=(0, 0, 1), resolution=400)
ok(abs(sec.area - math.pi * 100) / (math.pi * 100) < 0.01,
   f"área da seção ~ pi*r²: {sec.area:.2f} (exato {math.pi*100:.2f})")
ok(abs(sec.perimeter - 2 * math.pi * 10) / (2 * math.pi * 10) < 0.01,
   f"perímetro ~ 2*pi*r: {sec.perimeter:.2f}")
ok(len(sec.contours_3d) == 1 and sec.contours_3d[0].shape[1] == 3,
   "contornos 3D disponíveis")

fld, extent = slice_field(cyl, normal=(1, 0, 0), resolution=64)
ok(fld.shape == (64, 64) and fld.min() < 0 < fld.max(),
   "slice_field amostra o campo no plano")

metade = Sphere(10.0).cut((0, 0, 1), 0.0)
vol = generate_mesh(metade, resolution=80).volume()
esperado = 0.5 * 4 / 3 * math.pi * 1000
ok(abs(vol - esperado) / esperado < 0.02,
   f"cut(): meia esfera = {vol:.0f} (~{esperado:.0f})")

# ----------------------------------------- materiais / inércia (longo prazo)
print("\n[Materiais] massa e tensor de inércia")
box = generate_mesh(Box((20.0, 30.0, 40.0)), resolution=64)
rho = MATERIALS["Steel"].density_g_mm3
props = box.mass_properties(rho)
m_exp = 7.85e-3 * 20 * 30 * 40
ok(abs(props["mass"] - m_exp) / m_exp < 0.01,
   f"massa da caixa em aço: {props['mass']:.1f} g (~{m_exp:.1f})")
I = props["inertia_tensor"]
Ixx = m_exp * (30**2 + 40**2) / 12
Iyy = m_exp * (20**2 + 40**2) / 12
Izz = m_exp * (20**2 + 30**2) / 12
ok(abs(I[0, 0] - Ixx) / Ixx < 0.02 and abs(I[1, 1] - Iyy) / Iyy < 0.02
   and abs(I[2, 2] - Izz) / Izz < 0.02,
   f"inércia diagonal ~ analítica: {np.diag(I).round(0)} vs "
   f"({Ixx:.0f}, {Iyy:.0f}, {Izz:.0f})")
ok(np.abs(I - np.diag(np.diag(I))).max() < 0.01 * Ixx,
   "termos fora da diagonal ~ 0 (caixa alinhada)")

# --------------------------------------------------------- Fase 4: I/O
print("\n[Fase 4] exportação/importação")
with tempfile.TemporaryDirectory() as tmp:
    d3 = Document("io")
    d3.params.define("r", 8)
    d3.set_body(lambda P: Sphere(lambda: P["r"]))
    d3.material = MATERIALS["PLA"]

    for ext in (".stl", ".obj", ".ply"):
        path = os.path.join(tmp, "peca" + ext)
        d3.export(path, resolution=48)
        ok(os.path.getsize(path) > 1000, f"export('{ext}') gera arquivo")

    v_orig = d3.mesh.volume()
    m_in = import_mesh(os.path.join(tmp, "peca.stl"))
    ok(isinstance(m_in, Mesh) and abs(m_in.volume() - v_orig) < 1e-3,
       f"STL round-trip preserva volume ({m_in.volume():.2f})")
    m_obj = import_mesh(os.path.join(tmp, "peca.obj"))
    ok(abs(m_obj.volume() - v_orig) < 1e-2, "OBJ round-trip preserva volume")

    with open(os.path.join(tmp, "peca.ply"), "rb") as fh:
        ok(fh.read(3) == b"ply", "PLY com header válido")

    rep = d3.report(resolution=48)
    ok("MATERIAL: PLA" in rep and "Massa" in rep,
       "report inclui seção de material")

print(f"\n{PASS} testes passaram.")
