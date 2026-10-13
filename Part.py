"""tiny-freecad's stand-in for FreeCAD's Part module (see tinyfreecad/part.py)."""
import sys

from tinyfreecad import part

sys.modules[__name__] = part
