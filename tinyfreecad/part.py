"""FreeCAD's Part module: making shapes."""
import math

import numpy as np
import manifold3d as m3

from tinyfreecad import geometry, sweep
from tinyfreecad.base import Vector, as_array
from tinyfreecad.geometry import (Arc, ArcOfCircle, BSplineCurve, Circle, Curve as Geometry, Line,  # noqa: F401
                                  LineSegment)
from tinyfreecad.topo import (Edge, Face, OCCError, Shape, Solid as _Solid,  # noqa: F401
                              Vertex, Wire, make_compound, unsupported)


def _frame(pnt, dir):
    """4x4 matrix placing local +Z along `dir` with its origin at `pnt`,
    using the X direction OpenCASCADE would pick."""
    n = np.array([0.0, 0.0, 1.0]) if dir is None else as_array(dir)
    n = n / np.linalg.norm(n)
    x = geometry.default_xdir(n)
    m = np.identity(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, np.cross(n, x), n, as_array(pnt)
    return m


def _placed(manifold, pnt, dir):
    return _Solid([manifold.transform(_frame(pnt, dir)[:3, :].tolist())])


def _sector(radius, angle, segments):
    """A pie slice of `radius` from 0 to `angle` degrees as a CrossSection."""
    steps = max(1, int(math.ceil(segments * angle / 360.0)))
    pts = [(0.0, 0.0)] + [(radius * math.cos(math.radians(angle * i / steps)),
                           radius * math.sin(math.radians(angle * i / steps))) for i in range(steps + 1)]
    return m3.CrossSection([pts])


def makeBox(length, width, height, pnt=None, dir=None):
    """A box with one corner at `pnt` (default the origin)."""
    if min(length, width, height) <= 0:
        raise OCCError("a box needs positive sizes")
    return _placed(m3.Manifold.cube([float(length), float(width), float(height)]), pnt, dir)


def makeCylinder(radius, height, pnt=None, dir=None, angle=360):
    """A cylinder with its base centred on `pnt` and its axis along `dir`."""
    if radius <= 0 or height <= 0:
        raise OCCError("a cylinder needs a positive radius and height")
    segs = geometry.circle_segments(radius)
    if angle >= 360:
        m = m3.Manifold.cylinder(float(height), float(radius), float(radius), segs)
    else:
        m = m3.Manifold.extrude(_sector(float(radius), float(angle), segs), float(height))
    return _placed(m, pnt, dir)


def makeCone(radius1, radius2, height, pnt=None, dir=None, angle=360):
    """A cone (or frustum) from radius1 at `pnt` to radius2 at `height`."""
    if angle < 360:
        raise unsupported("part cones (angle below 360)")
    segs = geometry.circle_segments(max(radius1, radius2))
    return _placed(m3.Manifold.cylinder(float(height), float(radius1), float(radius2), segs), pnt, dir)


def makeSphere(radius, pnt=None, dir=None, angle1=-90, angle2=90, angle3=360):
    """A sphere centred on `pnt`."""
    if (angle1, angle2, angle3) != (-90, 90, 360):
        raise unsupported("part spheres")
    # Revolving a half circle keeps every latitude within TOLERANCE.
    segs = geometry.circle_segments(radius)
    half = [(radius * math.cos(a), radius * math.sin(a))
            for a in np.linspace(-math.pi / 2, math.pi / 2, segs // 2 + 1)]
    m = m3.Manifold.revolve(m3.CrossSection([[(0.0, -radius)] + half[1:-1] + [(0.0, radius)]]), segs)
    return _placed(m, pnt, dir)


def makeTorus(radius1, radius2, pnt=None, dir=None, angle1=0, angle2=360, angle=360):
    """A ring: a circle of radius2 swept round a circle of radius1."""
    if (angle1, angle2) != (0, 360):
        raise unsupported("part tori")
    section = m3.CrossSection.circle(float(radius2), geometry.circle_segments(radius2)).translate([radius1, 0.0])
    m = m3.Manifold.revolve(section, geometry.circle_segments(radius1 + radius2), float(angle))
    return _placed(m, pnt, dir)


def makeLine(p1, p2):
    return LineSegment(Vector(*p1), Vector(*p2)).toShape()


def makePolygon(points, closed=False):
    """A wire of straight lines through `points`."""
    pts = [as_array(p) for p in points]
    if closed and np.linalg.norm(pts[0] - pts[-1]) > 0:
        pts.append(pts[0])
    edges = [LineSegment(a, b).toShape() for a, b in zip(pts[:-1], pts[1:]) if np.linalg.norm(b - a) > 0]
    if not edges:
        raise OCCError("a polygon needs at least two different points")
    return Wire(edges)


def makeCircle(radius, center=None, dir=None, angle1=0, angle2=360):
    """A circular edge, or an arc from angle1 to angle2 degrees."""
    c = Circle(Vector(*(center if center is not None else (0, 0, 0))),
               Vector(*(dir if dir is not None else (0, 0, 1))), float(radius))
    if (angle1, angle2) == (0, 360):
        return c.toShape()
    return c.toShape(math.radians(angle1), math.radians(angle2))


def makePlane(length, width, pnt=None, dir=None, xdir=None):
    """A rectangular face with one corner at `pnt`."""
    m = _frame(pnt, dir)
    corners = [m[:3, :3] @ np.array(c) + m[:3, 3] for c in
               ((0, 0, 0), (length, 0, 0), (length, width, 0), (0, width, 0))]
    return Face(makePolygon(corners, True))


def makeCompound(shapes):
    return make_compound(list(shapes))


def Compound(shapes):
    return make_compound(list(shapes))


Solid = _Solid


def makeLoft(sections, solid=False, ruled=False, closed=False, maxDegree=5):
    return sweep.loft(sections, solid, ruled, closed)


def show(shape, name="Shape"):
    """Add `shape` to the active document (Part.show)."""
    import FreeCAD
    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    return obj


def __sortEdges__(edges):
    return Wire(edges).OrderedEdges


sortEdges = __sortEdges__
