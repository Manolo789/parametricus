# -*- coding: utf-8 -*-
"""Integração parametricus ⇄ núcleo-K (parametricus/brep.py).

Cobre as três rotas de exportação STEP (analítica exata, booleanas
B-Rep facetadas, malha), o despacho por extensão, o IGES e a
importação STEP → MeshSDF. Executável direto ou via pytest.
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import nucleok as nk                                      # noqa: E402
from parametricus import Document                         # noqa: E402
from parametricus.brep import (document_to_solid, load_step,  # noqa: E402
                               load_step_mesh, mesh_to_solid,
                               node_to_solid, solid_to_mesh, solid_to_sdf)
from parametricus.sdf import (Box, Cone, Cylinder, Difference,  # noqa: E402
                              Extrude, Revolve, Rotate, Scale, SmoothUnion,
                              Sphere, Torus, Translate, Union_)
from parametricus.sketch import (CircleProfile, PolygonProfile,  # noqa: E402
                                 RectProfile)

PASS = 0


def check(cond, msg):
    global PASS
    assert cond, msg
    PASS += 1
    print(f"  ok  {msg}")


def _doc(body_fn, name="t"):
    d = Document(name)
    d.set_body(body_fn)
    d.rebuild(verbose=False)
    return d


def test_mapeamento_exato():
    print("[1] mapeamento analítico nó SDF -> B-Rep")
    casos = [
        (Sphere(2.0), 4 / 3 * np.pi * 8, "esfera"),
        (Box((2, 3, 4)), 24.0, "caixa"),
        (Cylinder(3.0, 5.0), np.pi * 45, "cilindro"),
        (Cone(3.0, 0.0, 4.0), np.pi * 9 * 4 / 3, "cone (ápice)"),
        (Cone(3.0, 1.5, 4.0),
         np.pi * 4 / 3 * (9 + 4.5 + 2.25), "tronco de cone"),
        (Torus(5.0, 1.5), 2 * np.pi**2 * 5 * 2.25, "toro"),
        (Extrude(CircleProfile(2.0), 6.0), np.pi * 4 * 6,
         "extrusão de círculo -> cilindro"),
        (Extrude(RectProfile(2.0, 3.0), 4.0), 24.0,
         "extrusão de retângulo -> caixa"),
        (Extrude(PolygonProfile([(0, 0), (4, 0), (4, 2), (0, 2)]), 3.0),
         24.0, "extrusão de polígono"),
        (Revolve(PolygonProfile([(3, -1), (5, -1), (5, 1), (3, 1)])),
         np.pi * 16 * 2, "revolução de polígono (tubo)"),
    ]
    for node, exato, nome in casos:
        got = node_to_solid(node)
        assert got is not None, nome
        s, analitico = got
        v = nk.signed_volume(s, 0.003)
        check(analitico and nk.validate(s).ok
              and abs(v - exato) / exato < 0.01,
              f"{nome}: analítico, válido, volume < 1% ({exato:.3f})")

    got = node_to_solid(
        Translate(Rotate(Scale(Box((2, 2, 2)), 1.5), (1, 1, 0), 40.0),
                  (7, -3, 2)))
    s, analitico = got
    check(analitico and abs(nk.signed_volume(s) - 27.0) < 1e-6,
          "cadeia Translate∘Rotate∘Scale: exata (8·1.5³ = 27)")

    check(node_to_solid(SmoothUnion(Sphere(1), Sphere(1), 0.3)) is None,
          "nó fora do vocabulário (SmoothUnion) -> None (rota de malha)")


def test_tres_rotas_de_exportacao():
    print("[2] três rotas de exportação STEP")
    tmp = tempfile.mkdtemp()

    d1 = _doc(lambda p: Translate(
        Rotate(Cylinder(4.0, 10.0), (1, 0, 0), 30.0), (5, 0, 2)))
    p1 = os.path.join(tmp, "a.step")
    modo = d1.export_step(p1)
    back = nk.read_step(p1)[0]
    exato = np.pi * 16 * 10
    check(modo == "analítico"
          and "CYLINDRICAL_SURFACE" in open(p1).read()
          and abs(nk.signed_volume(back, 0.003) - exato) / exato < 0.005,
          "rota 1: STEP analítico (superfície cilíndrica exata no arquivo)")

    d2 = _doc(lambda p: Difference(Box((6, 6, 4)), Cylinder(1.5, 10)))
    p2 = os.path.join(tmp, "b.step")
    modo2 = d2.export_step(p2, deflection=0.01)
    back2 = nk.read_step(p2)[0]
    exato2 = 144 - np.pi * 2.25 * 4
    v2 = nk.signed_volume(back2, 0.01)
    check(modo2 == "facetado (booleanas B-Rep)"
          and nk.validate(back2).ok
          and abs(v2 - exato2) / exato2 < 0.01,
          "rota 2: booleanas B-Rep facetadas (< 1%), STEP válido")
    solid2, _ = document_to_solid(d2, deflection=0.01)
    check(abs(nk.signed_volume(back2, 0.01)
              - nk.signed_volume(solid2, 0.01)) < 1e-9,
          "rota 2: round-trip STEP sem perda (Δ = 0)")

    d3 = _doc(lambda p: SmoothUnion(
        Sphere(2.0), Translate(Sphere(2.0), (2.5, 0, 0)), 0.5))
    p3 = os.path.join(tmp, "c.step")
    modo3 = d3.export_step(p3, resolution=64)
    back3 = nk.read_step(p3)[0]
    v_mesh = d3.mesh.volume()
    check(modo3 == "facetado (malha)"
          and abs(nk.signed_volume(back3, 0.05) - v_mesh) / v_mesh < 1e-6,
          "rota 3: malha SDF -> B-Rep -> STEP com volume preservado")


def test_despacho_e_iges():
    print("[3] despacho por extensão e IGES")
    tmp = tempfile.mkdtemp()
    d = _doc(lambda p: Cylinder(3.0, 5.0))
    for ext in (".step", ".stp", ".iges", ".igs"):
        path = os.path.join(tmp, "peca" + ext)
        d.export(path)
        check(os.path.getsize(path) > 0, f"doc.export('peca{ext}')")
    curvas = nk.read_iges(os.path.join(tmp, "peca.iges"))
    circulos = [c for c, _, _ in curvas
                if isinstance(c, nk.Circle)]
    check(len(circulos) == 2
          and all(abs(c.radius - 3) < 1e-9 for c in circulos),
          "IGES do documento: círculos r=3 exatos (rota analítica)")

    from parametricus.io import export_mesh, supported_export_formats
    check({".step", ".stp", ".iges", ".igs"} <=
          set(supported_export_formats()),
          "formatos STEP/IGES registrados no despacho de malha")
    m = d.get_mesh(64)
    pm = os.path.join(tmp, "malha.step")
    export_mesh(m, pm)
    back = nk.read_step(pm)[0]
    check(abs(nk.signed_volume(back, 0.01) - m.volume()) / m.volume()
          < 1e-6, "export_mesh('.step'): STEP facetado da malha")


def test_importacao_step():
    print("[4] importação STEP -> MeshSDF")
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "imp.step")
    nk.write_step(nk.make_cylinder(4.0, 10.0, origin=(0, 0, -5)), p)

    m = load_step_mesh(p, deflection=0.01)
    exato = np.pi * 16 * 10
    check(abs(m.volume() - exato) / exato < 0.01,
          "load_step_mesh: volume < 1% do analítico")

    sdf = load_step(p, resolution=48, deflection=0.01)
    d = sdf.distance(np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]))
    check(d[0] < 0 < d[1], "MeshSDF importado: sinal correto dentro/fora")
    check(abs(-d[0] - 4.0) < 0.3,
          "distância no eixo ~ raio (interpolação da grade)")

    comb = Difference(sdf, Cylinder(1.0, 99.0))
    dd = comb.distance(np.array([[0.0, 0.0, 0.0], [2.5, 0.0, 0.0]]))
    check(dd[0] > 0 > dd[1],
          "booleana MeshSDF − Cylinder: furo remove o centro")


def test_ida_e_volta_malha():
    print("[5] malha ⇄ B-Rep ⇄ SDF")
    d = _doc(lambda p: Union_(Box((3, 3, 3)),
                              Translate(Box((3, 3, 3)), (1.5, 0, 0))))
    m = d.get_mesh(96)
    s = mesh_to_solid(m)
    check(nk.validate(s).ok
          and abs(nk.signed_volume(s) - m.volume()) / m.volume() < 1e-9,
          "mesh_to_solid: B-Rep válido com o volume da malha")
    m2 = solid_to_mesh(s, deflection=0.02)
    check(abs(m2.volume() - m.volume()) / m.volume() < 1e-9,
          "solid_to_mesh: ida e volta sem perda (faces planas)")
    sdf = solid_to_sdf(nk.make_sphere(2.0), resolution=48)
    dd = sdf.distance(np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]]))
    check(dd[0] < 0 < dd[1], "solid_to_sdf: esfera B-Rep vira MeshSDF")


if __name__ == "__main__":
    test_mapeamento_exato()
    test_tres_rotas_de_exportacao()
    test_despacho_e_iges()
    test_importacao_step()
    test_ida_e_volta_malha()
    print(f"\n{PASS} asserções passaram — integração parametricus ⇄ "
          "núcleo-K íntegra.")
