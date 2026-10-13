"""tiny-freecad's pieces behave like FreeCAD's."""
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Mesh  # noqa: E402
import Part  # noqa: E402
from tinyfreecad import app  # noqa: E402

V = App.Vector


def bounds(shape, places=4):
    b = shape.BoundBox
    return [round(v, places) for v in (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)]


class VectorTests(unittest.TestCase):
    def test_freecad_arithmetic(self):
        a, b = V(1, 2, 3), V(4, 5, 6)
        self.assertEqual(a * b, 32.0)                 # Vector * Vector is a dot product
        self.assertEqual(a * 2, V(2, 4, 6))
        self.assertEqual(a.cross(b), V(-3, 6, -3))
        n = V(3, 0, 4)
        self.assertIs(n.normalize(), n)              # in place
        self.assertAlmostEqual(n.Length, 1.0)
        a.x = 10
        self.assertEqual(tuple(a), (10.0, 2.0, 3.0))

    def test_matrix_rotation_applies_after(self):
        m = App.Matrix()
        m.move(V(1, 0, 0))
        m.rotateZ(math.pi / 2)
        p = m.multVec(V(0, 0, 0))
        self.assertAlmostEqual(p.x, 0.0)
        self.assertAlmostEqual(p.y, 1.0)

    def test_placement(self):
        p = App.Placement(V(1, 2, 3), App.Rotation(V(0, 0, 1), 90))
        q = p.multVec(V(1, 0, 0))
        self.assertEqual([round(c, 9) for c in q], [1, 3, 3])


class SolidTests(unittest.TestCase):
    def test_box_cylinder_and_cut(self):
        box = Part.makeBox(10, 20, 30, V(1, 2, 3))
        self.assertEqual(box.ShapeType, "Solid")
        self.assertAlmostEqual(box.Volume, 6000)
        self.assertEqual(bounds(box), [1, 2, 3, 11, 22, 33])
        hole = Part.makeCylinder(2, 40, V(6, 12, 0))
        cut = box.cut(hole)
        self.assertEqual(cut.ShapeType, "Compound")  # like FreeCAD's booleans
        self.assertAlmostEqual(cut.Volume, 6000 - math.pi * 4 * 30, delta=6000 * 0.001)

    def test_downward_cylinder(self):
        c = Part.makeCylinder(2, 4, V(1, 1, 1), V(0, 0, -1))
        self.assertEqual(bounds(c, 3), [-1, -1, -3, 3, 3, 1])

    def test_translate_is_in_place_and_tracks_placement(self):
        b = Part.makeBox(1, 1, 1)
        b.translate(V(5, 0, 0))
        self.assertEqual(bounds(b)[0], 5)
        self.assertEqual(b.Placement.Base, V(5, 0, 0))
        moved = b.copy()
        moved.Placement = App.Placement()
        self.assertEqual(bounds(moved)[0], 0)
        self.assertEqual(bounds(b)[0], 5)

    def test_void_is_part_of_its_solid(self):
        hollow = Part.makeBox(10, 10, 10).cut(Part.makeBox(2, 2, 2, V(4, 4, 4)))
        self.assertEqual(len(hollow.Solids), 1)
        self.assertAlmostEqual(hollow.Volume, 992)

    def test_compound_cut_keeps_members_apart(self):
        boxes = Part.makeCompound([Part.makeBox(1, 1, 1, V(x, 0, 0)) for x in range(4)])
        cut = boxes.cut(Part.makeBox(0.5, 3, 3, V(1.25, -1, -1)))
        self.assertEqual(len(cut.Solids), 5)  # the second box is split in two
        self.assertAlmostEqual(cut.Volume, 3.5)

    def test_sphere_torus_cone(self):
        self.assertAlmostEqual(Part.makeSphere(5).Volume, 4 / 3.0 * math.pi * 125, delta=5)
        self.assertAlmostEqual(Part.makeTorus(10, 2).Volume, 2 * math.pi ** 2 * 10 * 4, delta=5)
        self.assertAlmostEqual(Part.makeCone(2, 4, 10).Volume, math.pi * 10 / 3 * (4 + 8 + 16), delta=2)

    def test_mirror_and_transform_geometry(self):
        b = Part.makeBox(1, 2, 3, V(1, 0, 0))
        self.assertEqual(bounds(b.mirror(V(0, 0, 0), V(1, 0, 0))), [-2, 0, 0, -1, 2, 3])
        m = App.Matrix()
        m.rotateZ(math.pi / 2)
        self.assertEqual(bounds(b.transformGeometry(m)), [-2, 1, 0, 0, 2, 3])


class FaceTests(unittest.TestCase):
    def test_face_with_hole_extrudes(self):
        outer = Part.makePolygon([V(0, 0, 0), V(10, 0, 0), V(10, 10, 0), V(0, 10, 0)], True)
        hole = Part.Wire(Part.makeCircle(2, V(5, 5, 0)))
        face = Part.Face([outer, hole])
        self.assertAlmostEqual(face.Area, 100 - math.pi * 4, delta=0.05)
        solid = face.extrude(V(0, 0, -3))
        self.assertEqual(bounds(solid), [0, 0, -3, 10, 10, 0])
        self.assertAlmostEqual(solid.Volume, 3 * face.Area, delta=0.01)

    def test_three_point_arc(self):
        arc = Part.Arc(V(0, 0, 0), V(1, 1, 0), V(2, 0, 0))
        self.assertEqual(arc.Radius, 1.0)
        self.assertAlmostEqual(arc.toShape().Length, math.pi, places=3)

    def test_revolve(self):
        face = Part.Face(Part.makePolygon([V(2, 0, 0), V(3, 0, 0), V(3, 0, 4), V(2, 0, 4)], True))
        tube = face.revolve(V(0, 0, 0), V(0, 0, 1), 360)
        self.assertAlmostEqual(tube.Volume, math.pi * (9 - 4) * 4, delta=0.2)
        half = face.revolve(V(0, 0, 0), V(0, 0, 1), 180)
        self.assertGreater(half.BoundBox.YMax, 2.9)  # anticlockwise about +Z, from +X towards +Y

    def test_open_wire_cannot_make_a_face(self):
        with self.assertRaises(Part.OCCError):
            Part.Face(Part.makePolygon([V(0, 0, 0), V(1, 0, 0), V(1, 1, 0)]))

    def test_disconnected_edges_cannot_make_a_wire(self):
        with self.assertRaises(Part.OCCError):
            Part.Wire([Part.makeLine(V(0, 0, 0), V(1, 0, 0)), Part.makeLine(V(5, 0, 0), V(6, 0, 0))])


class CurveTests(unittest.TestCase):
    def test_interpolation_matches_opencascade(self):
        # Poles FreeCAD 1.0 gives for these points (GeomAPI_Interpolate).
        c = Part.BSplineCurve()
        c.interpolate([V(0, 0, 0), V(1, 2, 0), V(3, 3, 0), V(6, 1, 0), V(8, 0, 0)])
        d = c.getD1(0.0)
        self.assertAlmostEqual(d.x, 0.08658984, places=6)
        self.assertAlmostEqual(d.y, 1.02950243, places=6)

    def test_interpolation_with_scaled_tangents(self):
        tw, th = 16.0, 16.0 * 0.43
        c = Part.BSplineCurve()
        c.interpolate([V(0, 0, 0), V(8 - 2.8, th * 0.25, 0), V(8 - 3.6, th * 0.5, 0), V(8, th, 0)],
                      InitialTangent=V(1, 0, 0), FinalTangent=V(1, 0, 0))
        self.assertAlmostEqual(c.getD1(c.FirstParameter).x, 2.0940137, places=5)
        self.assertAlmostEqual(c.getD1(c.LastParameter).x, 4.4857924, places=5)

    def test_pipe_along_a_line_and_round_a_circle(self):
        straight = Part.Wire(Part.makeLine(V(0, 0, 0), V(0, 0, 20)))
        profile = Part.Wire(Part.makeCircle(1, V(0, 0, 0), V(0, 0, 1)))
        rod = straight.makePipeShell([profile], True, False)
        self.assertAlmostEqual(rod.Volume, math.pi * 20, delta=math.pi * 20 * 0.005)
        ring = Part.Wire(Part.makeCircle(10)).makePipeShell(
            [Part.Wire(Part.makeCircle(1, V(10, 0, 0), V(0, 1, 0)))], True, False)
        self.assertEqual(len(ring.Solids), 1)
        self.assertAlmostEqual(ring.Volume, 2 * math.pi ** 2 * 10, delta=2 * math.pi ** 2 * 10 * 0.005)

    def test_loft_frustum(self):
        a = Part.makePolygon([V(0, 0, 0), V(4, 0, 0), V(4, 4, 0), V(0, 4, 0)], True)
        b = Part.makePolygon([V(1, 1, 3), V(3, 1, 3), V(3, 3, 3), V(1, 3, 3)], True)
        loft = Part.makeLoft([a, b], True)
        self.assertAlmostEqual(loft.Volume, 3 / 3.0 * (16 + 4 + 8), places=6)


class DocumentTests(unittest.TestCase):
    def setUp(self):
        app.reset()

    def test_names_labels_and_active_document(self):
        self.assertIsNone(App.ActiveDocument)
        self.assertIsNone(Gui.ActiveDocument)
        doc = App.newDocument("Desk Tidy")
        self.assertIs(App.ActiveDocument, doc)
        self.assertEqual((doc.Name, doc.Label), ("Desk_Tidy", "Desk Tidy"))
        names = [doc.addObject("Part::Feature", n).Name for n in ("Desk Tidy", "Desk Tidy", "3 boxes")]
        self.assertEqual(names, ["Desk_Tidy", "Desk_Tidy001", "__boxes"])
        Gui.ActiveDocument.ActiveView.fitAll()  # accepted, does nothing

    def test_shape_is_copied_in_and_out(self):
        doc = App.newDocument()
        obj = doc.addObject("Part::Feature", "Box")
        box = Part.makeBox(1, 1, 1)
        obj.Shape = box
        box.translate(V(5, 0, 0))
        self.assertEqual(obj.Shape.BoundBox.XMin, 0)
        obj.ViewObject.ShapeColor = (1.0, 0.0, 0.0)
        self.assertEqual(obj.ViewObject.ShapeColor[:3], (1.0, 0.0, 0.0))

    def test_parametric_objects(self):
        doc = App.newDocument()
        box = doc.addObject("Part::Box", "Box")
        box.Length = 20
        cyl = doc.addObject("Part::Cylinder", "Cyl")
        cut = doc.addObject("Part::Cut", "Cut")
        cut.Base, cut.Tool = box, cyl
        doc.recompute()
        self.assertAlmostEqual(cut.Shape.Volume, 2000 - math.pi * 4 * 10 / 4, delta=1)

    def test_stl_round_trip(self):
        doc = App.newDocument()
        obj = doc.addObject("Part::Feature", "Box")
        obj.Shape = Part.makeBox(2, 3, 4)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "box.stl")
            Mesh.export([obj], path)
            m = Mesh.Mesh(path)
            self.assertEqual(m.CountFacets, 12)
            self.assertAlmostEqual(m.Volume, 24, places=4)


class ViewTests(unittest.TestCase):
    def setUp(self):
        app.reset()

    def test_view_calls_are_kept(self):
        App.newDocument()
        view = Gui.ActiveDocument.ActiveView
        self.assertEqual(view.orientation, "viewIsometric")  # FreeCAD's default
        view.viewTop()
        view.fitAll()
        self.assertEqual(view.orientation, "viewTop")
        Gui.SendMsgToActiveView("ViewFront")
        self.assertEqual(Gui.activeDocument().activeView().orientation, "viewFront")

    def test_picture_shows_the_shape_in_its_colour(self):
        try:
            import pyvista  # noqa: F401
        except ImportError:
            self.skipTest("pyvista isn't installed")
        from PIL import Image
        from tinyfreecad import viewer
        doc = App.newDocument()
        obj = doc.addObject("Part::Feature", "Box")
        obj.Shape = Part.makeBox(10, 10, 10)
        obj.ViewObject.ShapeColor = (1.0, 0.0, 0.0)
        hidden = doc.addObject("Part::Feature", "Hidden")
        hidden.Shape = Part.makeBox(5, 5, 5, V(50, 0, 0))
        hidden.ViewObject.Visibility = False
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "view.png")
            viewer.screenshot(path, 320, 240)
            with Image.open(path) as image:
                pixels = list(image.convert("RGB").getdata())
        reddish = sum(1 for r, g, b in pixels if r > 120 and g < 60 and b < 60)
        self.assertGreater(reddish, 0.05 * len(pixels))  # the box fills the (fitted) view


if __name__ == "__main__":
    unittest.main()
