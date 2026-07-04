"""
parametricus.viewer
==============
Visualizador 3D simples baseado em matplotlib, com sombreamento por
normal e eixos em escala real. Também salva imagens (PNG) do modelo.
"""

from __future__ import annotations

import numpy as np

from .mesher import Mesh


def show_mesh(mesh: Mesh, title: str = "parametricus", color: str = "#4a90d9",
              save_path: str | None = None, elev: float = 22, azim: float = -60,
              show: bool = True) -> None:
    import matplotlib
    if save_path and not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    v, f = mesh.vertices, mesh.faces
    tris = v[f]

    # sombreamento simples por normal de face (luz direcional fixa)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lens = np.linalg.norm(n, axis=1, keepdims=True)
    lens[lens == 0] = 1.0
    n = n / lens
    light = np.array([0.4, 0.3, 0.85])
    light = light / np.linalg.norm(light)
    intensity = np.clip(n @ light, 0.15, 1.0)

    base = np.array(matplotlib.colors.to_rgb(color))
    face_colors = np.clip(base * intensity[:, None] * 1.15, 0, 1)

    fig = plt.figure(figsize=(9, 8))
    ax = fig.add_subplot(111, projection="3d")
    coll = Poly3DCollection(tris, facecolors=face_colors,
                            edgecolors="none", linewidths=0)
    ax.add_collection3d(coll)

    bmin, bmax = mesh.bounding_box()
    center = (bmin + bmax) / 2.0
    half = (bmax - bmin).max() / 2.0 * 1.05
    ax.set_xlim(center[0] - half, center[0] + half)
    ax.set_ylim(center[1] - half, center[1] + half)
    ax.set_zlim(center[2] - half, center[2] + half)
    ax.set_box_aspect((1, 1, 1))
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title(title)
    ax.view_init(elev=elev, azim=azim)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=140)
        print(f"Imagem salva em: {save_path}")
    if show:
        plt.show()
    else:
        plt.close(fig)
