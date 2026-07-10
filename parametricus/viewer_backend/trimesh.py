"""
parametricus.viewer_backend.trimesh
===================
Backend 3D utilizando Trimesh.
"""

from __future__ import annotations

import numpy as np
import trimesh

from ..mesher import Mesh
from .._log import logger

# Install trimesh:
# pip install trimesh[easy]
# Se houver o erro 'ImportError: `trimesh.viewer.windowed` requires `pip install "pyglet<2"`', instalar:
# pip install pyglet<2
# E, se houver o erro 'ImportError: Library "GLU" not found.', instalar:
# sudo apt install libglu1-mesa
def show_trimesh(mesh: Mesh, title: str = "parametricus", color: str = "#4a90d9",
    save_path: str | None = None, show: bool = True) -> None:
    tm = trimesh.Trimesh(
        vertices=mesh.vertices,
        faces=mesh.faces,
        process=False,
    )

    rgba = trimesh.visual.color.hex_to_rgba(color)
    tm.visual.face_colors = np.tile(rgba, (len(tm.faces), 1))

    scene = trimesh.Scene(tm)

    scene.add_geometry(tm)

    if save_path is not None:
        png = scene.save_image(resolution=(1400, 1000))

        with open(save_path, "wb") as f:
            f.write(png)

        logger.info("Imagem salva em: %s", save_path)

    if show:
        scene.show()
