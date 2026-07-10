"""
Exemplo 4 — Placa com furos: tour pelas funcionalidades da v1.1
===============================================================
Demonstra as melhorias implementadas do roadmap:

  1. Histórico de features ENCADEADO (build(P, prev)) + suppress/edit
  2. Rebuild seletivo com cache (só a subárvore afetada regenera)
  3. Undo/Redo de parâmetros e edições de histórico
  4. Esboço com RESTRIÇÕES (solver) dirigido por parâmetros
  5. Medições, seção plana e corte
  6. Materiais: massa e momentos de inércia
  7. Exportação por extensão (.stl/.obj/.ply) e importação

Execução:  python examples/exemplo_placa_v11.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parametricus import (
    Document, Extrude, Cylinder, ConstrainedSketch, MATERIALS,
    enable_console_logging, distance_point, bounding_box, section,
    import_mesh,
)

enable_console_logging()          # logs INFO da biblioteca no console

doc = Document("Placa furada")
P = doc.params
P.define("W",     80, description="Largura da placa")
P.define("H",     50, description="Altura da placa")
P.define("esp",   8,  description="Espessura")
P.define("furo",  "esp * 0.75", description="Diâmetro dos furos")
P.define("n",     4,  description="Furos no padrão linear")

# ---------------------------------------------------------------- esboço
# Retângulo totalmente restrito: 4 pontos, horizontal + perpendicular +
# paralelismos + dimensões W e H amarradas aos parâmetros.
sk = ConstrainedSketch()
a = sk.point(0, 0)
b = sk.point(70, 2)               # chutes iniciais imprecisos de propósito
c = sk.point(72, 48)
d = sk.point(-2, 51)
ab, bc = sk.line(a, b), sk.line(b, c)
cd, da = sk.line(c, d), sk.line(d, a)
sk.fix(a)
sk.horizontal(ab)
sk.perpendicular(ab, bc)
sk.parallel(ab, cd)
sk.parallel(bc, da)
sk.length(ab, lambda: P["W"])
sk.length(bc, lambda: P["H"])
print("Esboço:", sk.dof_report())

# ------------------------------------------------------------- histórico
doc.add_feature(
    "Placa (esboço restrito)",
    lambda P: Extrude(sk.profile([a, b, c, d]), lambda: P["esp"]),
)
doc.add_feature(
    "Padrão de furos",
    lambda P, prev: prev - (
        Cylinder(lambda: P["furo"] / 2, lambda: P["esp"] * 3)
        .translate((lambda: P["W"] * 0.15, lambda: P["H"] * 0.5, 0))
        .array_linear(int(P["n"]),
                      (lambda: P["W"] * 0.7 / max(P["n"] - 1, 1), 0, 0))
    ),
    description="repetição de domínio — O(1) no nº de furos",
)

doc.material = MATERIALS["Aluminum"]
print(doc.report())               # 1º rebuild: constrói tudo

# ------------------------------------------------- rebuild seletivo + undo
print("\n>>> P.set('furo', 12): só o padrão de furos regenera\n")
P.set("furo", 12)
doc.rebuild()

print("\n>>> undo(): parâmetro volta e a malha anterior sai do cache\n")
doc.undo()
doc.rebuild()

print("\n>>> suppress('Padrão de furos') e redo do histórico\n")
doc.suppress("Padrão de furos")
print(f"    volume sem furos: {doc.get_mesh().volume():,.0f} mm³")
doc.undo()
print(f"    volume com furos: {doc.get_mesh().volume():,.0f} mm³")

# ------------------------------------------------------ medições e seção
print("\n>>> Medições")
bb = bounding_box(doc.body)
print(bb.report())
print(f"  Dist. origem->peça . {distance_point(doc.body, (0, 0, 50)):.2f} mm")
sec = section(doc.body, origin=(0, 0, 0), normal=(0, 0, 1))  # plano médio
print(sec.report())

# --------------------------------------------------------------- material
props = doc.mass_properties()
print(f"\n>>> Massa em {props['material']}: {props['mass']:,.1f} g")

# --------------------------------------------------------------- arquivos
doc.export("placa.stl")
doc.export("placa.ply")
mesh_importada = import_mesh("placa.stl")
print(f">>> Reimportado: {len(mesh_importada.faces):,} triângulos, "
      f"volume {mesh_importada.volume():,.0f} mm³")

for f in ("placa.stl", "placa.ply"):
    os.remove(f)
