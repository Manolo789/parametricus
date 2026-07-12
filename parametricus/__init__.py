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

from ._log import logger, enable_console_logging, disable_console_logging
from .parameters import Parameter, ParameterSet, ParameterError
from .document import Document, Feature
from .mesher import Mesh, MeshStats, MeshGenerator, MarchingCubesGenerator, generate_mesh
from .materials import Material, MATERIALS
from . import brep
from .io import (
    export_mesh, import_mesh, load_stl, load_obj,
    save_glb, save_3mf, MeshSDF,
)
from .measure import (
    distance_point, distance_points, distance_solids, SolidDistance,
    angle, face_normal_at, bounding_box, BoundingBox,
    section, slice_field, Section,
)
from .constraints import (
    ConstrainedSketch, Point2D, Line2D, Circle2D, SolverError,
)
from .sdf import (
    SDF,
    # primitivas
    Sphere, Box, Cylinder, Cone, Torus, Capsule, HalfSpace,
    # features de esboço
    Extrude, Revolve,
    # booleanas
    Union_, Intersection, Difference, SmoothUnion, SmoothDifference,
    # transformações
    Translate, Rotate, Scale, Mirror,
    # padrões
    PolarArray, LinearArray,
    # engenharia
    Shell, Round,
)
from .sketch import (
    Profile, CircleProfile, RectProfile,
    PolygonProfile, RegularPolygonProfile,
)

__version__ = "1.1.0"
__all__ = [
    "logger", "enable_console_logging", "disable_console_logging",
    "Document", "Feature", "Parameter", "ParameterSet", "ParameterError",
    "Mesh", "MeshStats", "MeshGenerator", "MarchingCubesGenerator",
    "generate_mesh",
    "Material", "MATERIALS",
    "export_mesh", "import_mesh", "load_stl", "load_obj",
    "save_glb", "save_3mf", "MeshSDF",
    "distance_point", "distance_points", "distance_solids", "SolidDistance",
    "angle", "face_normal_at", "bounding_box",
    "BoundingBox", "section", "slice_field", "Section",
    "ConstrainedSketch", "Point2D", "Line2D", "Circle2D", "SolverError",
    "SDF",
    "Sphere", "Box", "Cylinder", "Cone", "Torus", "Capsule", "HalfSpace",
    "Extrude", "Revolve",
    "Union_", "Intersection", "Difference", "SmoothUnion", "SmoothDifference",
    "Translate", "Rotate", "Scale", "Mirror", "PolarArray", "LinearArray",
    "Shell", "Round",
    "Profile", "CircleProfile", "RectProfile",
    "PolygonProfile", "RegularPolygonProfile",
]
