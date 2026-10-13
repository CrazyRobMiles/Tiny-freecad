"""The FreeCAD module: documents and the objects in them.

`import FreeCAD` gives this module. Documents hold objects in the order
they were made; Part features hold a shape, which tiny-freecad can write
out as STL (see tinyfreecad.mesh and tinyfreecad.runner).
"""
import re
import sys

from tinyfreecad import base as Base  # noqa: N812  (FreeCAD.Base)
from tinyfreecad.base import BoundBox, Matrix, Placement, Rotation, Vector  # noqa: F401

__all__ = ["Vector", "Matrix", "Placement", "Rotation", "BoundBox", "Base", "newDocument", "closeDocument",
           "getDocument", "listDocuments", "setActiveDocument", "activeDocument", "Console", "Version"]

_documents = {}
_active = [None]


def _valid_name(name):
    """A name FreeCAD would accept: letters, digits and _ only, not
    starting with a digit."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", str(name)) or "Unnamed"
    if name[0].isdigit():
        name = "_" + name[1:]
    return name


def _unique_name(name, taken, digits=3):
    if name not in taken:
        return name
    stem = name.rstrip("0123456789") or name
    used = [int(t[len(stem):]) for t in taken if t.startswith(stem) and t[len(stem):].isdigit()]
    number = max(used) + 1 if used else 1
    return "%s%0*d" % (stem, digits, number)


# -- view providers --


class ViewObject(object):
    """What FreeCAD's GUI keeps about an object: its colours and so on.
    Any property can be set; the common ones have FreeCAD's defaults."""

    def __init__(self, obj):
        self.__dict__["Object"] = obj
        self.__dict__["_props"] = {"Visibility": True}
        if obj.TypeId.startswith("Part::"):
            self.__dict__["_props"].update({
                "ShapeColor": (173 / 255.0, 181 / 255.0, 189 / 255.0, 0.0),  # FreeCAD 1.0's default
                "LineColor": (25 / 255.0, 25 / 255.0, 25 / 255.0, 0.0),
                "PointColor": (25 / 255.0, 25 / 255.0, 25 / 255.0, 0.0),
                "Transparency": 0, "DisplayMode": "Flat Lines", "LineWidth": 2.0, "PointSize": 2.0,
            })

    def __getattr__(self, name):
        props = self.__dict__["_props"]
        if name in props:
            return props[name]
        raise AttributeError("ViewObject has no property %r" % name)

    def __setattr__(self, name, value):
        if name.endswith("Color") and isinstance(value, (tuple, list)):
            value = tuple(float(v) / 255.0 if isinstance(v, int) and v > 1 else float(v) for v in value)
            value = (value + (0.0,))[:4] if len(value) == 3 else value
        self.__dict__["_props"][name] = value

    @property
    def PropertiesList(self):
        return sorted(self.__dict__["_props"])

    def show(self):
        self.Visibility = True

    def hide(self):
        self.Visibility = False


# -- document objects --


class DocumentObject(object):
    """An object in a document (App::DocumentObject)."""

    def __init__(self, doc, type_id, name):
        self.__dict__.update(Document=doc, TypeId=type_id, Name=name, _label=name, _touched=True,
                             _props={}, _types={})
        self.__dict__["_viewobject"] = ViewObject(self)

    @property
    def Label(self):
        return self._label

    @Label.setter
    def Label(self, value):
        self.__dict__["_label"] = str(value)

    @property
    def ViewObject(self):
        return self._viewobject

    @property
    def FullName(self):
        return "%s#%s" % (self.Document.Name, self.Name)

    @property
    def PropertiesList(self):
        return sorted(["Label", "Name"] + list(self._props))

    def __getattr__(self, name):
        props = self.__dict__.get("_props", {})
        if name in props:
            return props[name]
        raise AttributeError("%s object has no attribute %r" % (self.TypeId, name))

    def __setattr__(self, name, value):
        if name in type(self).__dict__ or any(name in c.__dict__ for c in type(self).__mro__):
            object.__setattr__(self, name, value)
        else:
            self._props[name] = value
            self.__dict__["_touched"] = True

    def addProperty(self, type_id, name, group="", doc="", attr=0, read_only=False, hidden=False):
        defaults = {"App::PropertyLength": 0.0, "App::PropertyDistance": 0.0, "App::PropertyFloat": 0.0,
                    "App::PropertyInteger": 0, "App::PropertyBool": False, "App::PropertyString": "",
                    "App::PropertyVector": Vector(), "App::PropertyAngle": 0.0}
        self._props.setdefault(name, defaults.get(type_id))
        self._types[name] = type_id
        return self

    def getTypeIdOfProperty(self, name):
        return self._types.get(name, "")

    def touch(self):
        self.__dict__["_touched"] = True

    def isValid(self):
        return True

    def isDerivedFrom(self, type_id):
        return type_id in (self.TypeId, "App::DocumentObject") or (
            type_id == "Part::Feature" and self.TypeId.startswith("Part::"))

    def recompute(self, recursive=False):
        self._execute()
        self.__dict__["_touched"] = False
        return True

    def _execute(self):
        pass

    def __repr__(self):
        return "<%s object>" % self.TypeId.split("::")[-1]


class PartFeature(DocumentObject):
    """Part::Feature: an object holding a shape. Setting Shape stores a copy
    of it, and its placement becomes the object's Placement."""

    def __init__(self, doc, type_id, name):
        DocumentObject.__init__(self, doc, type_id, name)
        from tinyfreecad.topo import Shape
        self.__dict__["_shape"] = Shape()

    @property
    def Shape(self):
        return self._recomputed()._shape.copy()

    @Shape.setter
    def Shape(self, shape):
        self.__dict__["_shape"] = shape.copy()

    @property
    def Placement(self):
        return self._shape.Placement

    @Placement.setter
    def Placement(self, placement):
        self._shape.Placement = placement

    def _recomputed(self):
        return self


class _Parametric(PartFeature):
    """A Part primitive or boolean that rebuilds its shape from its
    properties when the document is recomputed (or its Shape is read)."""

    DEFAULTS = {}

    def __init__(self, doc, type_id, name):
        PartFeature.__init__(self, doc, type_id, name)
        self.__dict__["_place"] = Placement()
        for k, v in self.DEFAULTS.items():
            self._props[k] = v

    @property
    def Placement(self):
        return Placement(self._place)

    @Placement.setter
    def Placement(self, placement):
        self.__dict__["_place"] = Placement(placement)
        self.touch()

    def _recomputed(self):
        if self._touched:
            self.recompute()
        return self

    def _execute(self):
        shape = self._build()
        shape.Placement = self._place.multiply(shape.Placement)
        self.__dict__["_shape"] = shape


class _Box(_Parametric):
    DEFAULTS = {"Length": 10.0, "Width": 10.0, "Height": 10.0}

    def _build(self):
        from tinyfreecad import part
        return part.makeBox(self.Length, self.Width, self.Height)


class _Cylinder(_Parametric):
    DEFAULTS = {"Radius": 2.0, "Height": 10.0, "Angle": 360.0}

    def _build(self):
        from tinyfreecad import part
        return part.makeCylinder(self.Radius, self.Height, None, None, self.Angle)


class _Cone(_Parametric):
    DEFAULTS = {"Radius1": 2.0, "Radius2": 4.0, "Height": 10.0, "Angle": 360.0}

    def _build(self):
        from tinyfreecad import part
        return part.makeCone(self.Radius1, self.Radius2, self.Height, None, None, self.Angle)


class _Sphere(_Parametric):
    DEFAULTS = {"Radius": 5.0}

    def _build(self):
        from tinyfreecad import part
        return part.makeSphere(self.Radius)


class _Boolean(_Parametric):
    DEFAULTS = {"Base": None, "Tool": None, "Shapes": [], "Refine": False}
    OP = "fuse"

    def _build(self):
        if self.TypeId == "Part::MultiFuse":
            shapes = [o.Shape for o in self.Shapes]
            return shapes[0].fuse(shapes[1:])
        if self.TypeId == "Part::MultiCommon":
            shapes = [o.Shape for o in self.Shapes]
            result = shapes[0]
            for s in shapes[1:]:
                result = result.common(s)
            return result
        for o in (self.Base, self.Tool):
            if o is not None:
                o.ViewObject.Visibility = False
        return getattr(self.Base.Shape, self.OP)(self.Tool.Shape)


class _Cut(_Boolean):
    OP = "cut"


class _Common(_Boolean):
    OP = "common"


class Group(DocumentObject):
    """App::DocumentObjectGroup: a folder of objects."""

    def __init__(self, doc, type_id, name):
        DocumentObject.__init__(self, doc, type_id, name)
        self._props["Group"] = []

    def addObject(self, obj):
        self._props["Group"] = self.Group + [obj]
        return [obj]

    def removeObject(self, obj):
        self._props["Group"] = [o for o in self.Group if o is not obj]

    def newObject(self, type_id, name=None):
        obj = self.Document.addObject(type_id, name)
        self.addObject(obj)
        return obj


_TYPES = {
    "Part::Feature": PartFeature, "Part::FeaturePython": PartFeature,
    "Part::Part2DObjectPython": PartFeature, "Part::Box": _Box, "Part::Cylinder": _Cylinder,
    "Part::Cone": _Cone, "Part::Sphere": _Sphere, "Part::Fuse": _Boolean, "Part::MultiFuse": _Boolean,
    "Part::Cut": _Cut, "Part::Common": _Common, "Part::MultiCommon": _Boolean,
    "App::FeaturePython": DocumentObject, "App::DocumentObjectGroup": Group,
}


class Document(object):
    """A FreeCAD document: a named list of objects."""

    def __init__(self, name, label):
        self.Name, self.Label = name, label
        self._objects = []
        self.FileName = ""

    @property
    def Objects(self):
        return list(self._objects)

    @property
    def ActiveObject(self):
        return self._objects[-1] if self._objects else None

    def supportedTypes(self):
        return sorted(_TYPES)

    def addObject(self, type_id, name=None, *args, **kwargs):
        cls = _TYPES.get(type_id)
        if cls is None:
            if type_id.endswith("Python"):
                cls = DocumentObject
            else:
                raise ValueError("tiny-freecad does not support document objects of type %r" % type_id)
        name = _unique_name(_valid_name(name or type_id.split("::")[-1]), {o.Name for o in self._objects})
        obj = cls(self, type_id, name)
        self._objects.append(obj)
        return obj

    def removeObject(self, name):
        obj = self.getObject(name)
        if obj is None:
            raise NameError("No document object found with name '%s'" % name)
        self._objects.remove(obj)
        for o in self._objects:
            if isinstance(o, Group):
                o.removeObject(obj)

    def getObject(self, name):
        for o in self._objects:
            if o.Name == name:
                return o
        return None

    def getObjectsByLabel(self, label):
        return [o for o in self._objects if o.Label == label]

    def findObjects(self, Type=None, Name=None, Label=None):
        out = []
        for o in self._objects:
            if Type and not o.isDerivedFrom(Type):
                continue
            if Name and not re.search(Name, o.Name):
                continue
            if Label and not re.search(Label, o.Label):
                continue
            out.append(o)
        return out

    def recompute(self, *args):
        count = 0
        for o in self._objects:
            if o._touched:
                o.recompute()
                count += 1
        return count

    def clearAll(self):
        self._objects = []

    def openTransaction(self, name=""):
        pass

    def commitTransaction(self):
        pass

    def abortTransaction(self):
        pass

    def save(self):
        raise NotImplementedError("tiny-freecad can't save FreeCAD documents; export STL files instead")

    saveAs = save

    def __getattr__(self, name):
        for o in self.__dict__.get("_objects", []):
            if o.Name == name:
                return o
        raise AttributeError("Document has no attribute or object %r" % name)

    def __repr__(self):
        return "<Document object>"


# -- the application --


def newDocument(name="Unnamed", label=None, hidden=False, temp=False):
    doc_name = _unique_name(_valid_name(name), set(_documents), digits=0)
    doc = Document(doc_name, label or name)
    _documents[doc_name] = doc
    _active[0] = doc
    return doc


def closeDocument(name):
    doc = _documents.pop(name, None)
    if doc is None:
        raise NameError("Unknown document '%s'" % name)
    if _active[0] is doc:
        _active[0] = next(reversed(_documents.values()), None) if _documents else None


def getDocument(name):
    if name not in _documents:
        raise NameError("Unknown document '%s'" % name)
    return _documents[name]


def listDocuments():
    return dict(_documents)


def setActiveDocument(name):
    _active[0] = getDocument(name) if name else None


def activeDocument():
    return _active[0]


def openDocument(path, hidden=False):
    raise NotImplementedError("tiny-freecad can't open FreeCAD documents")


def reset():
    """Close every document (used between script runs)."""
    _documents.clear()
    _active[0] = None


def Version():
    return ["1", "0", "2", "tiny-freecad"]


class _Console(object):
    def PrintMessage(self, text):
        sys.stdout.write(str(text))

    def PrintLog(self, text):
        pass

    def PrintWarning(self, text):
        sys.stderr.write(str(text))

    def PrintError(self, text):
        sys.stderr.write(str(text))

    PrintCritical = PrintError
    PrintNotification = PrintMessage


Console = _Console()


class _Params(object):
    """A ParamGet() group: hands back the defaults it is asked for."""

    def __getattr__(self, name):
        if name.startswith("Get"):
            return lambda key, default=None: default
        return lambda *args: None


def ParamGet(path):
    return _Params()


def __getattr__(name):
    if name == "ActiveDocument":
        return _active[0]
    raise AttributeError("tiny-freecad's FreeCAD module has no attribute %r" % name)
