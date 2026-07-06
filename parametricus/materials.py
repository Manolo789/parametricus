"""
parametricus.materials
======================
Sistema de materiais (item de longo prazo do roadmap, antecipado por ser
de baixo esforço: volume e centroide já existiam no ``Mesh``; o tensor de
inércia foi adicionado em ``Mesh.inertia_tensor``).

    from parametricus import Document, MATERIALS

    doc.material = MATERIALS["Steel"]
    props = doc.mass_properties()      # massa em g, inércia em g·mm²
    print(doc.report())                # inclui a seção de material

Densidades em g/cm³ (fonte: valores nominais de engenharia).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Material:
    """Material de engenharia com densidade em g/cm³."""
    name: str
    density_g_cm3: float
    color: str = "#8a8f98"

    @property
    def density_g_mm3(self) -> float:
        """Densidade em g/mm³ (unidade nativa do modelo é mm)."""
        return self.density_g_cm3 * 1e-3


#: Materiais pré-definidos citados no roadmap.
MATERIALS: Dict[str, Material] = {
    "Steel":    Material("Steel",    7.85, "#7a7f88"),
    "Aluminum": Material("Aluminum", 2.70, "#c8ccd2"),
    "Titanium": Material("Titanium", 4.51, "#9aa0a8"),
    "ABS":      Material("ABS",      1.04, "#e8b23a"),
    "PLA":      Material("PLA",      1.24, "#4a90d9"),
}
