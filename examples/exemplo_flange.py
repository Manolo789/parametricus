"""
Exemplo 1 — Flange industrial paramétrica
=========================================
Demonstra o núcleo da modelagem paramétrica: TODAS as dimensões derivam
de poucos parâmetros mestres. Mude `diametro_nominal` e a flange inteira
(furos, cubo, filetes) se reconfigura sozinha.

Execução:  python examples/exemplo_flange.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paracad import Document, Cylinder, Translate

doc = Document("Flange DN80")
P = doc.params

# ----------------------------- parâmetros mestres (edite e regenere!)
P.define("diametro_nominal", 80,  description="Diâmetro nominal do tubo (DN)")
P.define("num_furos",        6,   description="Furos de fixação")

# ----------------------------- parâmetros derivados (expressões)
P.define("d_flange",   "diametro_nominal * 2.2",      description="Ø externo da flange")
P.define("esp_flange", "max(diametro_nominal * 0.18, 8)", description="Espessura do disco")
P.define("d_cubo",     "diametro_nominal * 1.4",      description="Ø do cubo central")
P.define("h_cubo",     "esp_flange * 2.5",            description="Altura do cubo")
P.define("d_furo_fix", "max(diametro_nominal * 0.12, 6)", description="Ø furos de fixação")
P.define("r_circulo_furos", "(d_flange + d_cubo) / 4",  description="Raio do círculo de furos")
P.define("filete",     "esp_flange * 0.35",           description="Raio do filete cubo-disco")

# ----------------------------- árvore de features
def corpo(P):
    disco = Cylinder(lambda: P["d_flange"] / 2, lambda: P["esp_flange"])
    cubo = Translate(
        Cylinder(lambda: P["d_cubo"] / 2, lambda: P["h_cubo"]),
        lambda: (0, 0, (P["h_cubo"] - P["esp_flange"]) / 2),
    )
    # união com filete estrutural entre cubo e disco
    solido = disco.fillet_union(cubo, lambda: P["filete"])

    # furo central passante
    altura_total = lambda: P["h_cubo"] * 3
    furo_central = Cylinder(lambda: P["diametro_nominal"] / 2, altura_total)
    solido = solido - furo_central

    # furos de fixação em padrão polar
    furo = Translate(
        Cylinder(lambda: P["d_furo_fix"] / 2, altura_total),
        lambda: (P["r_circulo_furos"], 0, 0),
    ).array_polar(int(P["num_furos"]))
    return solido - furo

doc.add_feature("Disco base",      lambda P: Cylinder(P["d_flange"]/2, P["esp_flange"]))
doc.add_feature("Cubo central",    lambda P: Cylinder(P["d_cubo"]/2, P["h_cubo"]),
                "com filete de união")
doc.add_feature("Furo passante",   lambda P: Cylinder(P["diametro_nominal"]/2, P["h_cubo"]*3))
doc.add_feature("Furos de fixação", lambda P: Cylinder(P["d_furo_fix"]/2, P["h_cubo"]*3),
                f"padrão polar")
doc.set_body(corpo)

# ----------------------------- geração e exportação
print(doc.report(resolution=110))
doc.export_stl("flange_dn80.stl", resolution=160)

# ----------------------------- o "momento paramétrico": mude 1 parâmetro
print("\n>>> Alterando diametro_nominal: 80 -> 120 mm (tudo regenera)\n")
P.set("diametro_nominal", 120)
P.set("num_furos", 8)
print(doc.report(resolution=110))
doc.export_stl("flange_dn120.stl", resolution=160)

# visualização (salva PNG; use doc.show() para janela interativa)
from paracad.viewer import show_mesh
show_mesh(doc.mesh, title="Flange DN120", save_path="flange_dn120.png", show=False)
