"""
Exemplo 3 — Porca sextavada (extrusão de esboço + chanfros)
===========================================================
Demonstra extrusão de perfil 2D (hexágono - círculo do furo) e chanfro
das faces por interseção com cones — técnica clássica de modelagem.

Execução:  python examples/exemplo_porca.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
from paracad import Document, Extrude, Cone, Translate
from paracad.sketch import RegularPolygonProfile, CircleProfile

doc = Document("Porca M10")
P = doc.params

P.define("rosca",       10,   description="Diâmetro nominal (M)")
P.define("chave",       "rosca * 1.6",  description="Distância entre faces (chave)")
P.define("altura",      "rosca * 0.8",  description="Altura da porca")
P.define("folga_furo",  0.25, description="Folga do furo p/ rosca")

def corpo(P):
    # hexágono definido pela distância entre faces (não pelo circunraio)
    circunraio = lambda: (P["chave"] / 2) / math.cos(math.pi / 6)
    hexagono = RegularPolygonProfile(6, circunraio, rotation_deg=30)
    furo = CircleProfile(lambda: P["rosca"] / 2 + P["folga_furo"])
    perfil = hexagono - furo

    porca = Extrude(perfil, lambda: P["altura"])

    # chanfros: cones inclinados que só interceptam o hexágono perto das
    # faces superior/inferior (no plano médio o raio excede o circunraio)
    r_largo = lambda: circunraio() * 1.45
    r_faces = lambda: P["chave"] / 2 * 1.04
    h = lambda: P["altura"] * 1.02
    chanfro_topo = Cone(r_largo, r_faces, h)   # afina para cima
    chanfro_base = Cone(r_faces, r_largo, h)   # afina para baixo
    return porca & chanfro_topo & chanfro_base

doc.add_feature("Esboço hexagonal", lambda P: Extrude(
    RegularPolygonProfile(6, P["chave"] / 2 / math.cos(math.pi / 6)), P["altura"]))
doc.add_feature("Furo da rosca", lambda P: Extrude(
    CircleProfile(P["rosca"] / 2), P["altura"] * 2))
doc.add_feature("Chanfros cônicos", lambda P: Cone(P["chave"], 0, P["altura"] * 2.2))
doc.set_body(corpo)

print(doc.report(resolution=100))
doc.export_stl("porca_m10.stl", resolution=140)

print("\n>>> Escalando para M16 — um único parâmetro:\n")
P.set("rosca", 16)
print(doc.report(resolution=100))
doc.export_stl("porca_m16.stl", resolution=140)

from paracad.viewer import show_mesh
show_mesh(doc.mesh, title="Porca M16", color="#8a8f98",
          save_path="porca_m16.png", show=False)
