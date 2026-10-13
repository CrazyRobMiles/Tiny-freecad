"""Each example, run with tiny-freecad, makes what real FreeCAD made.

The FreeCAD results are in tests/reference (made by make_reference.py).
tiny-freecad's solids are meshes, so curved surfaces are polygons within
0.02mm of the true surface: volumes, areas and bounds are compared with a
little slack for that.

    python -m unittest tests.test_examples        # the tests
    python tests/test_examples.py --report [IDS]  # a table of differences
"""
import json
import os
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.dirname(TESTS))

import harness  # noqa: E402

# Slack for comparing with FreeCAD's exact geometry.
VOLUME_TOLERANCE = 0.01   # fraction of the volume
AREA_TOLERANCE = 0.02     # fraction of the area
BOUNDS_TOLERANCE = 0.05   # mm, plus 0.1% of the shape's size
COLOR_TOLERANCE = 0.005
# Compounds of hundreds of solids may differ by a sliver or two where a
# cut grazes a corner.
SOLIDS_TOLERANCE = 0.01   # fraction of the count

# Where an example needs more slack, and why.
VOLUME_TOLERANCE_FOR = {
    # The random path has a near-cusp (bend radius 0.06mm, against a 1.5mm
    # tube) where the sweep folds through itself. tiny-freecad's volume is
    # within 0.3% of pi r^2 L cos(tilt) = 5884; FreeCAD's sweep (which it
    # reports as valid) comes to 5610, 4.7% less.
    "27": 0.05,
}


def reference(example_id):
    path = os.path.join(harness.REFERENCE, example_id + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run(path):
    out_dir = tempfile.mkdtemp(prefix="tinyfreecad_")
    return harness.run_example(path, out_dir)


def _close(a, b, fraction, absolute=0.0):
    return abs(a - b) <= fraction * abs(b) + absolute


def differences(expected, actual, volume_tolerance=VOLUME_TOLERANCE):
    """What differs between FreeCAD's results and tiny-freecad's, as
    readable lines (empty if they match)."""
    problems = []
    e_err, a_err = expected["error"], actual["error"]
    if (e_err is None) != (a_err is None) or (e_err and e_err["type"] != a_err["type"]):
        problems.append("error: FreeCAD %s, tiny-freecad %s" % (
            e_err and "%s: %s" % (e_err["type"], e_err["message"]),
            a_err and a_err["traceback"]))
    if expected["documents"] != actual["documents"]:
        problems.append("documents: %s vs %s" % (expected["documents"], actual["documents"]))
    if expected["files"] != actual["files"]:
        problems.append("files: %s vs %s" % (expected["files"], actual["files"]))
    e_objs, a_objs = expected["objects"], actual["objects"]
    if [o["name"] for o in e_objs] != [o["name"] for o in a_objs]:
        problems.append("objects: %s vs %s" % ([o["name"] for o in e_objs], [o["name"] for o in a_objs]))
        return problems
    for e, a in zip(e_objs, a_objs):
        where = e["name"]
        for key in ("label", "type", "shape_type"):
            if e.get(key) != a.get(key):
                problems.append("%s %s: %r vs %r" % (where, key, e.get(key), a.get(key)))
        if (e.get("solids") is None) != (a.get("solids") is None) or (
                e.get("solids") is not None and not _close(a["solids"], e["solids"], SOLIDS_TOLERANCE)):
            problems.append("%s solids: %r vs %r" % (where, e.get("solids"), a.get("solids")))
        if "volume" in e and "volume" in a:
            if not _close(a["volume"], e["volume"], volume_tolerance, 1e-6):
                problems.append("%s volume: %g vs %g (%+.3f%%)" % (
                    where, e["volume"], a["volume"], 100.0 * (a["volume"] / e["volume"] - 1)))
            if not _close(a["area"], e["area"], AREA_TOLERANCE, 1e-6):
                problems.append("%s area: %g vs %g (%+.3f%%)" % (
                    where, e["area"], a["area"], 100.0 * (a["area"] / e["area"] - 1)))
            eb, ab = e["bound_box"], a["bound_box"]
            size = max(eb[3] - eb[0], eb[4] - eb[1], eb[5] - eb[2])
            slack = BOUNDS_TOLERANCE + 0.001 * size
            if any(abs(x - y) > slack for x, y in zip(eb, ab)):
                problems.append("%s bounds: %s vs %s" % (where, eb, ab))
        if "color" in e or "color" in a:
            ec, ac = e.get("color"), a.get("color")
            if ec is None or ac is None or any(abs(x - y) > COLOR_TOLERANCE for x, y in zip(ec, ac)):
                problems.append("%s color: %s vs %s" % (where, ec, ac))
    return problems


class ExampleTests(unittest.TestCase):
    pass


def _make_test(example_id, path):
    def test(self):
        expected = reference(example_id)
        if expected is None:
            self.skipTest("no FreeCAD reference for %s (run tests/make_reference.py)" % example_id)
        # A run that failed in FreeCAD too would "match" without testing anything.
        self.assertIsNone(expected["error"], "the example failed in FreeCAD: %s" % (expected["error"],))
        problems = differences(expected, run(path), VOLUME_TOLERANCE_FOR.get(example_id, VOLUME_TOLERANCE))
        self.assertEqual(problems, [], "\n".join(problems))
    return test


for _id, _path in harness.examples():
    _name = "test_%s_%s" % (_id, os.path.splitext(os.path.basename(_path))[0])
    setattr(ExampleTests, _name, _make_test(_id, _path))


def report(ids):
    for example_id, path in harness.examples():
        if ids and example_id not in ids:
            continue
        expected = reference(example_id)
        actual = run(path)
        problems = (differences(expected, actual, VOLUME_TOLERANCE_FOR.get(example_id, VOLUME_TOLERANCE))
                    if expected else ["(no reference)"])
        print("%s %-26s FreeCAD %6.1fs tiny %6.1fs  %s" % (
            example_id, os.path.basename(path), expected["seconds"] if expected else 0, actual["seconds"],
            "OK" if not problems else "DIFFERENT"))
        for p in problems:
            print("     " + p)


if __name__ == "__main__":
    if "--report" in sys.argv:
        report([a for a in sys.argv[1:] if a != "--report"])
    else:
        unittest.main()
