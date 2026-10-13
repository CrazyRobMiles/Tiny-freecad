"""Run a FreeCAD script with tiny-freecad and show what it made, as
FreeCAD would; optionally write every shape it made to STL files:

    python -m tinyfreecad script.py [--stl FOLDER] [--watch] [--no-view] [--screenshot FILE]
"""
import argparse
import os
import re
import runpy
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def use_tinyfreecad():
    """Make `import FreeCAD` (and FreeCADGui, Part, Draft, Mesh) find
    tiny-freecad."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)


def run_script(path, argv=None, fresh=False):
    """Run a script as __main__ (with its folder on sys.path, as Python
    would) and return the documents it left open. fresh=True closes every
    document first."""
    use_tinyfreecad()
    from tinyfreecad import app
    if fresh:
        app.reset()
    old_argv, old_path = sys.argv, list(sys.path)
    sys.argv = [path] + list(argv or [])
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    try:
        runpy.run_path(path, run_name="__main__")
    finally:
        sys.argv, sys.path[:] = old_argv, old_path
    return list(app.listDocuments().values())


def _file_name(label):
    return re.sub(r'[<>:"/\\|?*]', "_", label).strip() or "shape"


def export_documents(documents, folder):
    """Write each object holding a solid to <folder>/<label>.stl. Returns
    the paths written."""
    from tinyfreecad import mesh
    from tinyfreecad.topo import Solid
    os.makedirs(folder, exist_ok=True)
    written = []
    for doc in documents:
        for obj in doc.Objects:
            shape = getattr(obj, "Shape", None)
            if shape is None or not shape.Solids or isinstance(shape, Solid) and shape.isNull():
                continue
            path = os.path.join(folder, _file_name(obj.Label) + ".stl")
            mesh.export([obj], path)
            written.append(path)
    return written


def main(args=None):
    parser = argparse.ArgumentParser(prog="python -m tinyfreecad", description=__doc__.split("\n\n")[0])
    parser.add_argument("script", help="the FreeCAD Python script to run")
    parser.add_argument("--stl", metavar="FOLDER", help="write each shape the script made to an STL file here")
    parser.add_argument("--no-view", action="store_true", help="don't open a window showing what the script made")
    parser.add_argument("--watch", action="store_true",
                        help="run the script again (and redraw) each time it is saved")
    parser.add_argument("--screenshot", metavar="FILE",
                        help="save a picture of the view (.png) instead of opening a window")
    options, script_args = parser.parse_known_args(args)

    def run():
        try:
            run_script(options.script, script_args, fresh=True)
            return True
        except Exception:
            # Like FreeCAD, report the error and still show what was made.
            traceback.print_exc()
            return False

    ok = run()
    from tinyfreecad import app
    if options.stl:
        for path in export_documents(list(app.listDocuments().values()), options.stl):
            print("Wrote:", path)
    if options.screenshot:
        from tinyfreecad import viewer
        viewer.screenshot(options.screenshot)
        print("Wrote:", options.screenshot)
    elif options.watch or not options.no_view:
        from tinyfreecad import viewer
        viewer.show(watch=(options.script, run) if options.watch else None)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
