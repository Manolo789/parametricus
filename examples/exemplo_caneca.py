"""
Exemplo 2 — Caneca (revolução + casca + alça)
=============================================
Demonstra o fluxo esboço 2D -> revolução, a operação de casca (shell)
e uniões suaves. A exportação usa STEP via núcleo-K (a árvore contém
fillet_union/cantos arredondados, então sai pela rota de malha
facetada; primitivas puras sairiam com superfícies analíticas exatas). A capacidade (ml) é um parâmetro de entrada: o raio
interno é calculado por expressão a partir do volume desejado.

Execução:  python examples/exemplo_caneca.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parametricus import Document, Revolve, Torus, Rotate, Translate, Cylinder
from parametricus.sketch import RectProfile

doc = Document("Caneca 350ml")
P = doc.params

P.define("capacidade_ml", 350, unit="ml", description="Volume útil desejado")
P.define("altura_int",    95,  description="Altura interna do corpo")
P.define("parede",        3.5, description="Espessura de parede")
P.define("fundo",         6,   description="Espessura do fundo")
# raio interno derivado do volume:  V = pi r² h  ->  r = sqrt(V / (pi h))
P.define("raio_int", "sqrt(capacidade_ml * 1000 / (pi * altura_int))",
         description="Raio interno (derivado do volume)")
P.define("raio_ext",  "raio_int + parede")
P.define("altura_ext", "altura_int + fundo")
P.define("r_alca",    "altura_int * 0.32", description="Raio da alça (toro)")
P.define("tubo_alca", "parede * 1.6",      description="Ø do tubo da alça / 2")

def corpo(P):
    # corpo externo: revolução de retângulo com canto inferior arredondado
    perfil_ext = RectProfile(
        lambda: P["raio_ext"] * 2, lambda: P["altura_ext"],
        corner_radius=lambda: P["parede"],
    )
    externo = Revolve(perfil_ext)

    # cavidade interna: revolução deslocada para cima (deixa o fundo)
    perfil_int = RectProfile(
        lambda: P["raio_int"] * 2, lambda: P["altura_int"] + 2,
    ).translate(0, lambda: (P["fundo"] + 2) / 2 + 0.5)
    cavidade = Revolve(perfil_int)

    copo = externo - cavidade

    # alça: meio-toro no plano XZ, encostado na parede externa
    alca = Rotate(
        Torus(lambda: P["r_alca"], lambda: P["tubo_alca"]),
        (1, 0, 0), 90,
    )
    alca = Translate(alca, lambda: (P["raio_ext"] + P["r_alca"] * 0.45, 0, 0))
    # corta a metade da alça que invadiria o interior
    recorte = Translate(
        Cylinder(lambda: P["raio_int"], lambda: P["altura_ext"] * 2),
        (0, 0, 0),
    )
    alca = alca - recorte

    # união suave alça-corpo (filete orgânico)
    return copo.fillet_union(alca, lambda: P["parede"] * 1.2)

doc.add_feature("Corpo por revolução", lambda P: Revolve(
    RectProfile(P["raio_ext"] * 2, P["altura_ext"])))
doc.add_feature("Cavidade interna", lambda P: Cylinder(P["raio_int"], P["altura_int"]))
doc.add_feature("Alça toroidal", lambda P: Torus(P["r_alca"], P["tubo_alca"]),
                "união com filete suave")
doc.set_body(corpo)

#print(doc.report(resolution=100))
#doc.export_step("caneca_350ml.step", resolution=150)

print("\n>>> Versão 500 ml — só o parâmetro de capacidade muda:\n")
P.set("capacidade_ml", 500)
P.set("altura_int", 110)
print(doc.report(resolution=100))
#doc.export_step("caneca_500ml.step", resolution=150)

from parametricus.viewer import show_mesh
show_mesh(doc.mesh, title="Caneca 500 ml", color="#d97a4a", show=True, engine="pyside6")
