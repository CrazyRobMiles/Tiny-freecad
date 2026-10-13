"""Record what real FreeCAD makes from each example, for the tests to
compare tiny-freecad against.

    python tests/make_reference.py [IDS...] [--freecad PATH]

This starts FreeCAD (its GUI, as some examples set colours through
ViewObject) on freecad_side.py, which runs each example with
harness.run_example() and writes tests/reference/<id>.json. FreeCAD
closes itself when it has finished.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FREECAD = r"C:\Program Files\FreeCAD 1.0\bin\freecad.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ids", nargs="*", help="example numbers, e.g. 05 18 (default: all)")
    parser.add_argument("--freecad", default=os.environ.get("FREECAD_EXE", DEFAULT_FREECAD),
                        help="FreeCAD's GUI executable")
    options = parser.parse_args()
    log = os.path.join(tempfile.gettempdir(), "tinyfreecad_reference.log")
    env = dict(os.environ, TINYFREECAD_TESTS=TESTS, TINYFREECAD_IDS=",".join(options.ids), TINYFREECAD_LOG=log)
    if os.path.exists(log):
        os.remove(log)
    start = time.time()
    subprocess.run([options.freecad, os.path.join(TESTS, "freecad_side.py")], env=env, check=False)
    if os.path.exists(log):
        with open(log, encoding="utf-8") as f:
            sys.stdout.write(f.read())
    print("FreeCAD finished in %.0fs" % (time.time() - start))


if __name__ == "__main__":
    main()
