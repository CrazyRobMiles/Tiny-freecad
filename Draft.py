"""tiny-freecad's stand-in for FreeCAD's Draft module (see tinyfreecad/draft.py)."""
import sys

from tinyfreecad import draft

sys.modules[__name__] = draft
