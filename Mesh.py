"""tiny-freecad's stand-in for FreeCAD's Mesh module (see tinyfreecad/mesh.py)."""
import sys

from tinyfreecad import mesh

sys.modules[__name__] = mesh
