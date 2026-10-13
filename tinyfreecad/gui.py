"""The FreeCADGui module.

Nothing is drawn while a script runs. Calls such as
Gui.ActiveDocument.ActiveView.fitAll() or viewTop() are accepted, and the
view a script asks for is kept, so that tinyfreecad.viewer can show the
document that way afterwards (python -m tinyfreecad does this). As in
FreeCAD, Gui.ActiveDocument is None until there is an active document.
"""
from tinyfreecad import app


class _Ignored(object):
    """Accepts any method call and ignores it."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _ignore


def _ignore(*args, **kwargs):
    return None


# View3D methods that set the view; the viewer (tinyfreecad.viewer)
# applies the last orientation a script asked for when it shows the
# document.
_ORIENTATIONS = {"viewIsometric", "viewAxonometric", "viewDimetric", "viewTrimetric", "viewFront", "viewRear",
                 "viewTop", "viewBottom", "viewLeft", "viewRight", "viewAxometric"}
_MESSAGES = {"ViewFit": "fitAll", "ViewIsometric": "viewIsometric", "ViewAxo": "viewIsometric",
             "ViewFront": "viewFront", "ViewRear": "viewRear", "ViewTop": "viewTop", "ViewBottom": "viewBottom",
             "ViewLeft": "viewLeft", "ViewRight": "viewRight"}


class View3D(_Ignored):
    """The 3D view. Nothing is drawn while the script runs; the camera
    settings it asks for are kept for tinyfreecad.viewer."""

    def __init__(self):
        self.orientation = "viewIsometric"   # FreeCAD's default for a new document
        self.camera_type = "Orthographic"

    def __getattr__(self, name):
        if name in _ORIENTATIONS:
            return lambda *args, **kwargs: setattr(self, "orientation", name)
        return _Ignored.__getattr__(self, name)

    def getCameraType(self):
        return self.camera_type

    def setCameraType(self, camera_type):
        self.camera_type = "Perspective" if str(camera_type).lower().startswith("p") else "Orthographic"

    def saveImage(self, filename, width=800, height=600, *args, **kwargs):
        from tinyfreecad import viewer
        viewer.screenshot(filename, width, height)


class GuiDocument(_Ignored):
    def __init__(self, doc):
        self.Document = doc
        self.ActiveView = View3D()

    def getObject(self, name):
        obj = self.Document.getObject(name)
        return obj.ViewObject if obj is not None else None

    def activeView(self):
        return self.ActiveView


_gui_docs = {}


def getDocument(name):
    doc = app.getDocument(name) if isinstance(name, str) else name
    if id(doc) not in _gui_docs or _gui_docs[id(doc)].Document is not doc:
        _gui_docs[id(doc)] = GuiDocument(doc)
    return _gui_docs[id(doc)]


def activeDocument():
    doc = app.activeDocument()
    return getDocument(doc) if doc is not None else None


def activeView():
    doc = activeDocument()
    return doc.ActiveView if doc is not None else None


class _Selection(_Ignored):
    def getSelection(self, *args):
        return []

    def getSelectionEx(self, *args):
        return []


Selection = _Selection()


def SendMsgToActiveView(message, *args):
    view = activeView()
    if view is not None and message in _MESSAGES:
        getattr(view, _MESSAGES[message])()
    return None


def updateGui():
    return None


def doCommand(*args):
    return None


def runCommand(*args):
    return None


def addModule(*args):
    return None


def getMainWindow():
    return None


def __getattr__(name):
    if name == "ActiveDocument":
        return activeDocument()
    raise AttributeError("tiny-freecad's FreeCADGui module has no attribute %r" % name)
