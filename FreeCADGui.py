"""tiny-freecad's stand-in for FreeCAD's FreeCADGui module (see tinyfreecad/gui.py)."""
import sys

from tinyfreecad import gui

sys.modules[__name__] = gui
