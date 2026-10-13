"""Runs inside FreeCAD (started by make_reference.py): runs the examples
with the real FreeCAD and writes what they made to tests/reference.

Only the tests folder goes on sys.path - not the repository root, whose
FreeCAD.py, Part.py, ... would hide FreeCAD's own modules.
"""
import json
import os
import sys
import tempfile
import traceback

tests = os.environ["TINYFREECAD_TESTS"]
sys.path.insert(0, tests)

log = open(os.environ["TINYFREECAD_LOG"], "a", encoding="utf-8")
try:
    import harness

    wanted = [i for i in os.environ.get("TINYFREECAD_IDS", "").split(",") if i]
    os.makedirs(harness.REFERENCE, exist_ok=True)
    for example_id, path in harness.examples():
        if wanted and example_id not in wanted:
            continue
        out_dir = tempfile.mkdtemp(prefix="freecad_%s_" % example_id)
        result = harness.run_example(path, out_dir)
        result["made_by"] = "FreeCAD %s" % ".".join(__import__("FreeCAD").Version()[:3])
        with open(os.path.join(harness.REFERENCE, example_id + ".json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        error = result["error"]
        log.write("%s %-28s %6.1fs %3d objects %s\n" % (
            example_id, os.path.basename(path), result["seconds"], len(result["objects"]),
            "" if error is None else "%s: %s" % (error["type"], error["message"])))
        log.flush()
except Exception:
    log.write(traceback.format_exc())
finally:
    log.close()
    os._exit(0)
