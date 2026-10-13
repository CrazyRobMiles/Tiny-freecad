"""Run an example script and measure what it made.

This file runs both under tiny-freecad and inside real FreeCAD (see
make_reference.py), so it only uses the FreeCAD API and the standard
library.

The image examples write their STL files to an "stl" folder beside the
script (OUTPUT_FOLDER). Before running, that setting is pointed at a
scratch folder, in the text that is run, so tests don't write into the
examples; the example files themselves are never changed.
"""
import contextlib
import glob
import io
import os
import random
import re
import time
import traceback

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
EXAMPLES = os.path.join(ROOT, "examples")
REFERENCE = os.path.join(TESTS, "reference")

# Every run starts from the same random numbers, so examples that use
# random make the same shapes in FreeCAD and tiny-freecad.
SEED = 1234


def examples():
    """[(id, path)] of every example script, e.g. ("05", ".../PendantPair.py")."""
    found = []
    for path in sorted(glob.glob(os.path.join(EXAMPLES, "*", "*.py"))):
        folder = os.path.basename(os.path.dirname(path))
        found.append((folder.split(" ")[0], path))
    return found


def prepare_source(path, out_dir):
    """The script's text, with OUTPUT_FOLDER pointed at out_dir."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    return re.sub(r"^(OUTPUT_FOLDER\s*=\s*).*$", lambda m: "%sr\"%s\"" % (m.group(1), out_dir),
                  source, flags=re.M)


def _number(value):
    return float("%.6g" % value)


def measure(obj):
    """What an object holds, as plain JSON-able values."""
    found = {"name": obj.Name, "label": obj.Label, "type": obj.TypeId}
    try:
        shape = obj.Shape
    except AttributeError:
        shape = None
    if shape is not None and not shape.isNull():
        bb = shape.BoundBox
        found.update(shape_type=shape.ShapeType, volume=_number(shape.Volume), area=_number(shape.Area),
                     bound_box=[_number(v) for v in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)],
                     solids=len(shape.Solids))
    try:
        found["color"] = [round(float(c), 3) for c in obj.ViewObject.ShapeColor[:3]]
    except Exception:
        pass
    return found


def run_example(path, out_dir):
    """Run the script at `path` (in a clean session, with the random
    numbers seeded) and return what it made."""
    import FreeCAD as App
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    os.makedirs(out_dir, exist_ok=True)
    source = prepare_source(path, out_dir)
    namespace = {"__name__": "__main__", "__file__": path}
    random.seed(SEED)
    error = None
    output = io.StringIO()
    start = time.time()
    with contextlib.redirect_stdout(output):
        try:
            exec(compile(source, path, "exec"), namespace)
        except Exception as e:
            error = {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()}
    seconds = time.time() - start
    doc = App.ActiveDocument
    return {
        "script": os.path.relpath(path, ROOT).replace("\\", "/"),
        "error": error,
        "seconds": round(seconds, 2),
        "documents": sorted(d.Label for d in App.listDocuments().values()),
        "objects": [measure(o) for o in doc.Objects] if doc is not None else [],
        "files": sorted(os.listdir(out_dir)),
    }
