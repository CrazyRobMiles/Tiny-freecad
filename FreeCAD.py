"""tiny-freecad's stand-in for FreeCAD's FreeCAD module (see tinyfreecad/app.py)."""
import sys

from tinyfreecad import app

sys.modules[__name__] = app
