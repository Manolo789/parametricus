"""
parametricus — CAD paramétrico 3D em Python
======================================
Modelagem sólida por geometria implícita (SDF) com sistema de
parâmetros dirigido por expressões, árvore de features, malhagem por
Marching Cubes e exportação STL/OBJ.

Uso rápido:
    from parametricus import Document, Box, Cylinder

    doc = Document("Peça")
    P = doc.params
    P.define("L", 60)
    P.define("furo", "L / 4")
    doc.set_body(lambda P:
        Box((P["L"], P["L"], 20)) - Cylinder(lambda: P["furo"], 30)
    )
    doc.rebuild()
    doc.export_stl("peca.stl")
"""

from .parameters import Parameter, ParameterSet, ParameterError
from .document import Document, Feature
from .mesher import Mesh, MeshStats, MeshGenerator, MarchingCubesGenerator, generate_mesh
from .sdf import (
    SDF,
    # primitivas
    Sphere, Box, Cylinder, Cone, Torus, Capsule,
    # features de esboço
    Extrude, Revolve,
    # booleanas
    Union_, Intersection, Difference, SmoothUnion, SmoothDifference,
    # transformações
    Translate, Rotate, Scale, Mirror,
    # padrões
    PolarArray,
    # engenharia
    Shell, Round,
)
from .sketch import (
    Profile, CircleProfile, RectProfile,
    PolygonProfile, RegularPolygonProfile,
)

__version__ = "1.0.0"
__all__ = [
    "Document", "Feature", "Parameter", "ParameterSet", "ParameterError",
    "Mesh", "MeshStats", "MeshGenerator", "MarchingCubesGenerator",
    "generate_mesh", "SDF",
    "Sphere", "Box", "Cylinder", "Cone", "Torus", "Capsule",
    "Extrude", "Revolve",
    "Union_", "Intersection", "Difference", "SmoothUnion", "SmoothDifference",
    "Translate", "Rotate", "Scale", "Mirror", "PolarArray", "Shell", "Round",
    "Profile", "CircleProfile", "RectProfile",
    "PolygonProfile", "RegularPolygonProfile",
]
