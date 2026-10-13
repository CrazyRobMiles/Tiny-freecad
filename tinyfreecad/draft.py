"""The parts of FreeCAD's Draft module that make text: make_text (a
label, which has no geometry) and make_shapestring (text as faces)."""
from tinyfreecad import app
from tinyfreecad.base import Placement


def _doc():
    return app.activeDocument() or app.newDocument()


def make_text(string, placement=None, screen=False, height=None, line_spacing=1):
    """A text label. It shows in FreeCAD's 3D view but has no shape, so
    here it is just an object in the document."""
    obj = _doc().addObject("App::FeaturePython", "Text")
    obj.Text = [string] if isinstance(string, str) else list(string)
    obj.Placement = Placement(placement) if placement is not None else Placement()
    return obj


makeText = make_text


def make_shapestring(String, FontFile, Size=100, Tracking=0):
    """Text as a Compound of faces, in a ShapeString object."""
    from tinyfreecad import text
    obj = _doc().addObject("Part::Part2DObjectPython", "ShapeString")
    obj.String, obj.FontFile, obj.Size, obj.Tracking = String, FontFile, float(Size), float(Tracking)
    obj.Shape = text.shape_string(String, FontFile, float(Size), float(Tracking))
    return obj


makeShapeString = make_shapestring


def __getattr__(name):
    raise AttributeError("tiny-freecad's Draft module has no %r (only make_text and make_shapestring)" % name)
