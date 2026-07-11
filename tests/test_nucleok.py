# -*- coding: utf-8 -*-
"""Suíte do núcleo-K: consolida as validações das 6 camadas.

Executável direto (``python tests/test_nucleok.py``) ou via pytest.
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleok import (  # noqa: E402
    Circle, HEModel, Line, Location, NURBSCurve, Plane, Transform,
    classify_point, collinear, curve_plane, extrude, line_cylinder,
    line_plane, line_sphere, make_box, make_cylinder, make_sphere,
    make_torus, orient2d, orient3d, plane_plane, read_step, read_stl,
    revolve, signed_volume, surface_area, tessellate,
    triangulate_polygon, validate, volume, write_iges, write_step,
    write_stl,
)

PASS = 0


def check(cond, msg):
    global PASS
    assert cond, msg
    PASS += 1
    print(f"  ok  {msg}")


def test_camada1_fundacao():
    print("[1] fundação matemática")
    check(orient2d((0, 0), (1, 0), (0, 1)) == +1, "orient2d CCW = +1")
    check(orient2d((0, 0), (1e-30, 1e-30), (2e-30, 2e-30)) == 0,
          "orient2d quase-degenerado cai no caminho exato -> 0")
    check(orient3d((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)) == +1,
          "orient3d canônico = +1")
    check(collinear((0, 0, 0), (1, 1, 1), (2, 2, 2)), "collinear exato")
    T = Transform.rotation((0, 0, 1), np.pi / 2)
    check(np.allclose(T.apply_point([1, 0, 0]), [0, 1, 0], atol=1e-12),
          "rotação 90° em Z")
    M = Transform.mirror((1, 0, 0))
    check(not M.is_rigid and np.allclose(M.apply_point([2, 3, 4]),
                                         [-2, 3, 4]),
          "espelho Householder")
    comp = Transform.translation((1, 0, 0)) @ T
    check(np.allclose(comp.inverse().m @ comp.m, np.eye(4), atol=1e-12),
          "composição e inversa")


def test_camada2_geometria():
    print("[2] geometria analítica e NURBS")
    c9 = NURBSCurve.full_circle((0, 0, 0), (0, 0, 1), 5.0)
    ts = np.linspace(0, 1, 200)
    r = np.linalg.norm(c9.evaluate(ts)[:, :2], axis=1)
    check(float(np.abs(r - 5).max()) < 1e-12,
          "círculo NURBS racional exato (9 pontos)")
    c9b = c9.insert_knot(0.37, 2)
    r2 = np.linalg.norm(c9b.evaluate(ts)[:, :2], axis=1)
    check(float(np.abs(r2 - 5).max()) < 1e-12,
          "inserção de nó preserva a forma")
    circ = Circle((1, 2, 3), (0, 0, 1), 2.0)
    p = circ.evaluate(1.234)
    check(abs(circ.parameter_of(p) - 1.234) < 1e-12,
          "Circle.parameter_of inverte evaluate")
    check(abs(circ.length() - 4 * np.pi) < 1e-9,
          "comprimento de arco (Gauss-Legendre)")
    from nucleok import CylindricalSurface, SphericalSurface
    cyl = CylindricalSurface((0, 0, 0), (0, 0, 1), 3.0)
    u, v = cyl.parameters_of(cyl.evaluate(0.7, 1.3))
    check(abs(u - 0.7) < 1e-12 and abs(v - 1.3) < 1e-12,
          "inversão paramétrica do cilindro")
    sph = SphericalSurface((0, 0, 0), 2.0)
    n = sph.normal(0.5, 0.3)
    check(np.allclose(n, sph.evaluate(0.5, 0.3) / 2.0, atol=1e-5),
          "normal da esfera é radial")


def test_camada3_topologia():
    print("[3] topologia B-Rep")
    box = make_box(2, 3, 4)
    rep = validate(box)
    check(rep.ok and (rep.V, rep.E, rep.F) == (8, 12, 6)
          and rep.euler_characteristic == 2, "caixa V8/E12/F6 χ=2")
    cyl = make_cylinder(3, 5)
    rep = validate(cyl)
    check(rep.ok and (rep.V, rep.E, rep.F) == (2, 3, 3)
          and rep.euler_characteristic == 2, "cilindro V2/E3/F3 χ=2")
    sph = make_sphere(2)
    rep = validate(sph)
    check(rep.ok and (rep.V, rep.E, rep.F) == (2, 1, 1)
          and rep.euler_characteristic == 2, "esfera V2/E1/F1 χ=2")
    tor = make_torus(5, 1.5)
    rep = validate(tor)
    check(rep.ok and (rep.V, rep.E, rep.F) == (1, 2, 1)
          and rep.euler_characteristic == 0, "toro V1/E2/F1 χ=0 (gênero 1)")


def test_camada4_algoritmos():
    print("[4] algoritmos fundamentais")
    # triangulação com furos
    sq = [(0, 0), (4, 0), (4, 4), (0, 4)]
    hole = [(1, 1), (3, 1), (3, 3), (1, 3)]
    pts, tris = triangulate_polygon(sq, [hole])
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    area = float(np.abs(0.5 * ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                               - (b[:, 1] - a[:, 1])
                               * (c[:, 0] - a[:, 0]))).sum())
    check(abs(area - 12.0) < 1e-12, "ear clipping com furo: área exata")

    # interseções
    ln = Line((0, 0, -5), (0, 0, 1))
    pl = Plane((0, 0, 2), (0, 0, 1))
    check(abs(line_plane(ln, pl) - 7.0) < 1e-12, "reta×plano")
    il = plane_plane(Plane((0, 0, 0), (0, 0, 1)),
                     Plane((0, 0, 0), (0, 1, 0)))
    check(abs(np.dot(il.direction, [1, 0, 0])) > 1 - 1e-12,
          "plano×plano -> eixo X")
    check(np.allclose(line_sphere(ln, (0, 0, 0), 2.0), [3.0, 7.0]),
          "reta×esfera")
    check(len(line_cylinder(Line((-5, 0, 1), (1, 0, 0)),
                            (0, 0, 0), (0, 0, 1), 2.0)) == 2,
          "reta×cilindro")
    roots = curve_plane(Circle((0, 0, 0), (0, 1, 0), 3.0),
                        Plane((0, 0, 0), (0, 0, 1)))
    check(len(roots) == 2, "curva×plano (bisseção+Newton): 2 raízes")

    # classificação
    box = make_box(2, 3, 4)
    check(classify_point(box, (1, 1, 1)) is Location.INSIDE
          and classify_point(box, (5, 5, 5)) is Location.OUTSIDE
          and classify_point(box, (0, 1, 1)) is Location.ON_BOUNDARY,
          "classificação dentro/fora/na-borda")

    # operadores de Euler: tetraedro
    m = HEModel()
    v0, f0 = m.mvfs((0, 0, 0))
    lp = f0.outer
    v1 = m.mev(v0, (1, 0, 0), lp)
    v2 = m.mev(v1, (0.5, 1, 0), lp)
    hs = lp.halfedges()
    f1 = m.mef(next(h for h in hs if h.origin is v2),
               next(h for h in hs if h.origin is v0))
    lp2 = f1.outer
    v3 = m.mev(next(h for h in lp2.halfedges() if h.origin is v0).origin,
               (0.5, 0.4, 1), lp2)

    def find(va, vb):
        for f in m.faces:
            for L in f.loops:
                hs = L.halfedges()
                ha = [h for h in hs if h.origin is va]
                hb = [h for h in hs if h.origin is vb]
                if ha and hb:
                    return ha[0], hb[0]
        raise AssertionError("par não encontrado")

    m.mef(*find(v3, v1))
    m.mef(*find(v3, v2))
    check((m.V, m.E, m.F) == (4, 6, 4)
          and m.euler_characteristic() == 2,
          "Euler ops: tetraedro V4/E6/F4 χ=2")
    tetra = m.to_solid()
    rep = validate(tetra)
    check(rep.ok, "tetraedro (Euler ops) valida como B-Rep")
    check(abs(abs(signed_volume(tetra)) - 1 / 6) < 1e-9,
          "volume do tetraedro = 1/6 exato")

    # -------- v0.2: tesselação de recortes em superfícies curvas
    from nucleok import CylindricalSurface, tessellate_trimmed
    cylsurf = CylindricalSurface((0, 0, 0), (0, 0, 1), 3.0)
    tt = tessellate_trimmed(
        cylsurf, [[(1, 0), (2, 2), (1, 4), (0, 2)]], deflection=0.002)
    pa = tt.vertices[tt.triangles[:, 0]]
    pb = tt.vertices[tt.triangles[:, 1]]
    pc = tt.vertices[tt.triangles[:, 2]]
    area = float(np.linalg.norm(np.cross(pb - pa, pc - pa),
                                axis=1).sum() / 2)
    check(abs(area - 12.0) / 12.0 < 5e-3,
          "recorte losango no cilindro: área = r·A_uv (< 0.5%)")

    # -------- v0.2: BVH concorda com força bruta
    from nucleok.algo.bvh import BVH
    sph = make_sphere(2)
    tsp = __import__("nucleok").tessellate(sph, 0.01)
    check(len(tsp.triangles) >= 64
          and classify_point(tsp, (1.5, 0.5, 0.5)) is Location.INSIDE
          and classify_point(tsp, (3, 0, 0)) is Location.OUTSIDE,
          "classificação via BVH (malha grande) correta")
    bvh = BVH(tsp.vertices, tsp.triangles)
    d_irr = np.array([0.5773502691896258, 0.2113248654051871,
                      0.7886751345948129])
    hits = bvh.ray_hits((0, 0, 0), d_irr / np.linalg.norm(d_irr))
    check(len(hits) % 2 == 1,
          "BVH: raio do centro cruza número ímpar de vezes (paridade)")


def test_camada5_modelagem():
    print("[5] modelagem sólida")
    box = make_box(2, 3, 4)
    check(abs(signed_volume(box) - 24.0) < 1e-9, "volume caixa exato")
    cyl = make_cylinder(3, 5)
    vol = signed_volume(cyl, 0.005)
    check(abs(vol - np.pi * 45) / (np.pi * 45) < 0.01,
          "volume cilindro < 1% (deflexão 0.005)")
    check(abs(surface_area(cyl, 0.005)
              - (2 * np.pi * 15 + 2 * np.pi * 9))
          / (2 * np.pi * 24) < 0.01, "área cilindro < 1%")
    sph = make_sphere(2)
    check(abs(signed_volume(sph, 0.005) - 4 / 3 * np.pi * 8)
          / (4 / 3 * np.pi * 8) < 0.01, "volume esfera < 1%")
    tor = make_torus(5, 1.5)
    ref = 2 * np.pi ** 2 * 5 * 1.5 ** 2
    check(abs(signed_volume(tor, 0.005) - ref) / ref < 0.01,
          "volume toro < 1%")

    L = [(0, 0), (6, 0), (6, 2), (2, 2), (2, 6), (0, 6)]
    hole = [(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)]
    pris = extrude(L, 3, holes=[hole])
    rep = validate(pris)
    check(rep.ok and rep.euler_characteristic == 0,
          "prisma L com furo passante: válido, χ=0 (gênero 1)")
    check(abs(signed_volume(pris) - 57.0) < 1e-9,
          "volume extrusão com furo exato (57)")

    tubo = revolve([(3, 0), (5, 0), (5, 2), (3, 2)])
    ref = np.pi * (25 - 9) * 2
    check(validate(tubo).ok
          and abs(signed_volume(tubo, 0.005) - ref) / ref < 0.005,
          "revolução: tubo confere com anel cilíndrico")
    tri = revolve([(4, 0), (6, 1), (4, 2)])
    ref = 2 * np.pi * (14 / 3) * 2.0          # Pappus
    check(abs(signed_volume(tri, 0.005) - ref) / ref < 0.005,
          "revolução triangular confere com Pappus")

    # -------- v0.2: revolução parcial e perfis tocando o eixo
    cone = revolve([(0, 0), (3, 0), (0, 4)])
    rep = validate(cone)
    ref = np.pi * 9 * 4 / 3
    check(rep.ok and rep.euler_characteristic == 2
          and abs(signed_volume(cone, 0.003) - ref) / ref < 0.005,
          "cone (perfil no eixo): χ=2 e volume πR²H/3")
    q = revolve([(0, 0), (3, 0), (0, 4)], angle=np.pi / 2)
    check(validate(q).ok
          and abs(signed_volume(q, 0.003) - ref / 4) / (ref / 4) < 0.005,
          "quarto de cone (revolução parcial com tampas)")
    meia = revolve([(3, 0), (5, 0), (5, 2), (3, 2)], angle=np.pi)
    ref = np.pi * 16 * 2 / 2
    check(validate(meia).ok and validate(meia).euler_characteristic == 2
          and abs(signed_volume(meia, 0.005) - ref) / ref < 0.005,
          "meio-tubo (ângulo π): χ=2, metade do volume")

    # -------- v0.2: loft e sweep
    from nucleok import loft, sweep_path
    f = loft([[(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)],
              [(1, 1, 3), (3, 1, 3), (3, 3, 3), (1, 3, 3)]])
    check(validate(f).ok and abs(signed_volume(f) - 28.0) < 1e-9,
          "loft: tronco de pirâmide com volume exato (28)")
    sq = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    swz = sweep_path(sq, [(0, 0, 0), (0, 0, 3), (3, 0, 3), (3, 0, 6)])
    check(validate(swz).ok and abs(signed_volume(swz) - 9.0) < 1e-9,
          "sweep em Z com esquadria: volume exato A·ΣL (9)")

    # -------- v0.2: transformação profunda
    from nucleok import Transform
    M = Transform.mirror((1, 0.3, 0), point=(4, 0, 0))
    S = Transform.scaling(2.0, center=(1, 1, 1))
    tor = make_torus(5, 1.5)
    v0 = signed_volume(tor, 0.01)
    tm = tor.transformed(M)
    check(validate(tm).ok
          and abs(signed_volume(tm, 0.01) - v0) < 1e-9 * max(1, v0),
          "espelho profundo do toro: válido e volume preservado")
    ts = tor.transformed(S)
    check(abs(signed_volume(ts, 0.02) - 8 * v0) / (8 * v0) < 1e-9,
          "escala profunda 2x: volume exatamente 8x (deflexão escalada)")

    # -------- v0.2: booleanas fuse/common/cut
    from nucleok import common, cut, fuse
    a = make_box(2, 2, 2)
    b = make_box(2, 2, 2, origin=(1, 0, 0))
    for op, exp, nome in ((fuse, 12.0, "fuse"), (common, 4.0, "common"),
                          (cut, 4.0, "cut")):
        r = op(a, b)
        rep = validate(r)
        check(rep.ok and rep.euler_characteristic == 2
              and abs(signed_volume(r) - exp) < 1e-9,
              f"booleana {nome} de caixas: B-Rep válido e volume exato "
              f"({exp:g})")
    furada = cut(make_box(6, 6, 4),
                 make_cylinder(1.5, 8, origin=(3, 3, -2)),
                 deflection=0.01)
    ref = 144 - np.pi * 2.25 * 4
    check(validate(furada).ok
          and abs(signed_volume(furada) - ref) / ref < 0.01,
          "caixa − cilindro: válido, volume < 1% do exato")
    lente = common(make_sphere(2), make_sphere(2, center=(2, 0, 0)),
                   deflection=0.01)
    ref = np.pi * 10 * 4 / 12
    check(validate(lente).ok
          and abs(signed_volume(lente) - ref) / ref < 0.04,
          "esfera ∩ esfera: lente com volume < 4% (borda facetada)")

    # -------- v0.2: chanfro e filete
    from nucleok import chamfer_edge, fillet_edge
    box3 = make_box(3, 3, 3)
    alvo = None
    for f_ in box3.faces:
        for lp in f_.loops:
            for e, _ in lp.edges:
                pts = sorted([tuple(np.round(e.start.point, 9)),
                              tuple(np.round(e.end.point, 9))])
                if pts == sorted([(0., 0., 0.), (0., 0., 3.)]):
                    alvo = e
    ch = chamfer_edge(box3, alvo, 0.8)
    check(validate(ch).ok
          and abs(signed_volume(ch) - (27 - 0.32 * 3)) < 1e-9,
          "chanfro em aresta reta: volume exato a³ − (d²/2)L")
    fi = fillet_edge(box3, alvo, 0.8, deflection=0.005)
    ref = 27 - (0.64 - np.pi * 0.64 / 4) * 3
    check(validate(fi).ok
          and abs(signed_volume(fi) - ref) / ref < 0.002,
          "filete em aresta reta: válido, volume < 0.2% do exato")


def test_camada6_interoperabilidade():
    print("[6] interoperabilidade STEP/IGES/STL")
    tmp = tempfile.mkdtemp()
    casos = [
        ("caixa", make_box(2, 3, 4)),
        ("cilindro", make_cylinder(3, 5)),
        ("esfera", make_sphere(2)),
        ("toro", make_torus(5, 1.5)),
        ("revolve", revolve([(3, 0), (5, 0), (5, 2), (3, 2)])),
        ("extrude", extrude([(0, 0), (6, 0), (6, 2), (2, 2), (2, 6),
                             (0, 6)], 3,
                            holes=[[(0.5, 0.5), (1.5, 0.5),
                                    (1.5, 1.5), (0.5, 1.5)]])),
    ]
    for name, s in casos:
        p = os.path.join(tmp, name + ".step")
        write_step(s, p)
        back = read_step(p)[0]
        rep0, rep1 = validate(s), validate(back)
        check(rep1.ok
              and (rep0.V, rep0.E, rep0.F) == (rep1.V, rep1.E, rep1.F),
              f"STEP round-trip {name}: topologia idêntica")
        v0 = signed_volume(s, 0.01)
        v1 = signed_volume(back, 0.01)
        check(abs(v1 - v0) <= 1e-9 * max(1.0, abs(v0)),
              f"STEP round-trip {name}: volume preservado")

    cyl = make_cylinder(3, 5)
    p = os.path.join(tmp, "c.stl")
    write_stl(cyl, p, deflection=0.01)
    t = read_stl(p)
    check(abs(signed_volume(t) - signed_volume(cyl, 0.01)) < 1e-3,
          "STL round-trip binário")
    p2 = os.path.join(tmp, "c_ascii.stl")
    write_stl(cyl, p2, deflection=0.05, binary=False)
    check(len(read_stl(p2).triangles) > 0, "STL ASCII legível")

    p3 = os.path.join(tmp, "c.iges")
    write_iges(cyl, p3)
    lines = open(p3).read().splitlines()
    check(all(len(ln) == 80 for ln in lines)
          and lines[-1][72] == "T", "IGES: 80 colunas e terminador")

    # -------- v0.2: leitor IGES (round-trip wireframe)
    from nucleok import read_iges
    curves = read_iges(p3)
    from nucleok import Circle as _C
    circles = [c for c, _, _ in curves if isinstance(c, _C)]
    check(len(curves) == 3 and len(circles) == 2
          and all(abs(c.radius - 3) < 1e-9 for c in circles),
          "read_iges(cilindro): 1 costura + 2 círculos r=3")
    p4 = os.path.join(tmp, "b.iges")
    write_iges(make_box(2, 3, 4), p4)
    curves = read_iges(p4)
    lens_ = sorted({round(t1 - t0, 9) for _, t0, t1 in curves})
    check(len(curves) == 12 and lens_ == [2.0, 3.0, 4.0],
          "read_iges(caixa): 12 arestas, comprimentos 2/3/4 exatos")

    # -------- v0.2: resultado de booleana exporta para STEP
    from nucleok import cut as _cut
    furada = _cut(make_box(4, 4, 2),
                  make_cylinder(1.0, 4, origin=(2, 2, -1)),
                  deflection=0.02)
    p5 = os.path.join(tmp, "furada.step")
    write_step(furada, p5)
    back = read_step(p5)[0]
    check(abs(signed_volume(back, 0.01) - signed_volume(furada, 0.01))
          < 1e-6, "STEP round-trip de sólido booleano (facetado)")


def test_independencia():
    print("[i] independência do pacote")
    import nucleok
    deps = {m.split(".")[0] for m in sys.modules
            if m.startswith("parametricus")}
    src_dir = os.path.dirname(nucleok.__file__)
    ofensores = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(root, f)) as fh:
                    src = fh.read()
                if ("import parametricus" in src
                        or "from parametricus" in src):
                    ofensores.append(f)
    check(not ofensores,
          "nenhum módulo do nucleok IMPORTA o parametricus")


if __name__ == "__main__":
    test_camada1_fundacao()
    test_camada2_geometria()
    test_camada3_topologia()
    test_camada4_algoritmos()
    test_camada5_modelagem()
    test_camada6_interoperabilidade()
    test_independencia()
    print(f"\n{PASS} asserções passaram — núcleo-K íntegro nas 6 camadas.")
