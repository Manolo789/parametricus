"""
parametricus.viewer
==============
Visualizador 3D compatível com várias engines, com sombreamento por
normal e eixos em escala real. Também salva imagens (PNG) do modelo.
"""

from __future__ import annotations

from .mesher import Mesh


def show_mesh(mesh: Mesh, title: str = "parametricus", color: str = "#4a90d9",
              save_path: str | None = None, elev: float = 22, azim: float = -60,
              show: bool = True, engine="default") -> None:
    common = {"mesh": mesh, "title": title, "color": color, "save_path": save_path, "show": show}
    
    if (engine == "default") or (engine == "pyvista"):
        from .viewer_backend.pyvista import show_pyvista
        return show_pyvista(**common)
        
    elif engine == "trimesh":
        from .viewer_backend.trimesh import show_trimesh
        return show_trimesh(**common)

    elif engine == "pyside6":
        from .viewer_backend.pyside6 import show_pyside6
        return show_pyside6(**common)
    
    elif (engine == "old") or (engine == "matplotlib"): # Descontinuado
        from .viewer_backend.mpl import show_mpl
        return show_mpl(elev=elev, azim=azim, **common)

    else:
        raise ValueError(f"Engine '{engine}' não suportada.")
