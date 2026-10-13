"""Shapes: Part.Vertex, Edge, Wire, Face, Solid and Compound.

Edges, wires and faces keep their exact curves. Solids are closed
triangle meshes held by manifold3d, so booleans are fast and always give
something a slicer can print. Curved surfaces become polygons that stay
within geometry.TOLERANCE of the true surface.

A Solid holds one or more manifold "parts". A single part is what booleans
produce; several parts make a compound (Part.makeCompound()), whose
volume is the sum of its parts, as in FreeCAD. Booleans treat a compound
as the union of its parts.
"""
import math

import numpy as np
import manifold3d as m3

from tinyfreecad import geometry
from tinyfreecad.base import BoundBox, Matrix, Placement, Rotation, Vector, as_array, as_vector

TOLERANCE = geometry.TOLERANCE

# Edge ends closer than this (mm) are joined when edges make a wire.
JOIN_TOLERANCE = 1e-5


class OCCError(RuntimeError):
    """Part.OCCError: a modelling operation couldn't be done."""


def unsupported(what):
    return NotImplementedError("tiny-freecad does not support %s" % what)


def _translation(v):
    m = np.identity(4)
    m[:3, 3] = as_array(v)
    return m


def _rotation(base, axis, degrees):
    c = as_array(base)
    r = Rotation(Vector(*axis), degrees).toMatrix()._a
    return _translation(c) @ r @ _translation(-c)


def _mirroring(base, normal):
    n = as_array(normal)
    n = n / np.linalg.norm(n)
    m = np.identity(4)
    m[:3, :3] -= 2.0 * np.outer(n, n)
    m[:3, 3] = 2.0 * np.dot(as_array(base), n) * n
    return m


def _matrix_of(matrix):
    return matrix._a if isinstance(matrix, Matrix) else np.asarray(matrix, dtype=float)


def _unit(a):
    n = np.linalg.norm(a)
    return a / n if n > 0 else a


class Shape(object):
    """The base of every shape (Part.Shape). Like FreeCAD's shapes,
    translate(), rotate(), scale() and transformShape() move a shape in
    place; mirror(), transformGeometry() and the booleans return new
    shapes."""

    ShapeType = "Shape"

    def __init__(self):
        self._placement = np.identity(4)

    # -- subclasses provide --

    def _apply(self, m):
        """Move this shape's geometry by the 4x4 matrix m, in place."""
        raise NotImplementedError

    def _copy(self):
        raise NotImplementedError

    def _points(self):
        """Points whose bounds are the shape's bounds (Nx3)."""
        return np.zeros((0, 3))

    # -- copying and moving --

    def copy(self, *args, **kwargs):
        c = self._copy()
        c._placement = self._placement.copy()
        return c

    def _moved(self, m):
        self._apply(m)
        self._placement = m @ self._placement
        return self

    def translate(self, v):
        return self._moved(_translation(v))

    def rotate(self, base, axis, degree):
        return self._moved(_rotation(base, axis, degree))

    def scale(self, factor, base=None):
        c = as_array(base)
        return self._moved(_translation(c) @ np.diag([factor, factor, factor, 1.0]) @ _translation(-c))

    def transformShape(self, matrix, copy=False, checkScale=False):
        return self._moved(_matrix_of(matrix))

    def transformGeometry(self, matrix):
        return self.copy()._moved(_matrix_of(matrix))

    def transformed(self, matrix, copy=False, checkScale=False, op=None):
        return self.transformGeometry(matrix)

    def mirror(self, base, normal):
        return self.copy()._moved(_mirroring(base, normal))

    def translated(self, v):
        return self.copy().translate(v)

    def rotated(self, base, axis, degree):
        return self.copy().rotate(base, axis, degree)

    def scaled(self, factor, base=None):
        return self.copy().scale(factor, base)

    @property
    def Placement(self):
        return Placement(Matrix(self._placement.copy()))

    @Placement.setter
    def Placement(self, placement):
        self._moved(placement.toMatrix()._a @ np.linalg.inv(self._placement))

    @property
    def Matrix(self):
        return Matrix(self._placement.copy())

    @Matrix.setter
    def Matrix(self, matrix):
        self._moved(_matrix_of(matrix) @ np.linalg.inv(self._placement))

    # -- measuring --

    @property
    def BoundBox(self):
        pts = self._points()
        if len(pts) == 0:
            return BoundBox()
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        return BoundBox(lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])

    @property
    def Volume(self):
        return 0.0

    @property
    def Area(self):
        return 0.0

    @property
    def Length(self):
        return sum(e.Length for e in self.Edges)

    def isNull(self):
        return False

    def isValid(self):
        return not self.isNull()

    def check(self, *args):
        if not self.isValid():
            raise ValueError("shape is not valid")

    def fix(self, *args):
        return True

    def removeSplitter(self):
        return self.copy()

    def isClosed(self):
        return False

    # -- sub-shapes --

    @property
    def Vertexes(self):
        return []

    @property
    def Edges(self):
        return []

    @property
    def Wires(self):
        return []

    @property
    def Faces(self):
        return []

    @property
    def Shells(self):
        return []

    @property
    def Solids(self):
        return []

    @property
    def SubShapes(self):
        return []

    # -- operations every solid-bearing shape shares --

    def fuse(self, *others):
        return Solid._boolean(self, others, "fuse")

    def cut(self, *others):
        return Solid._boolean(self, others, "cut")

    def common(self, *others):
        return Solid._boolean(self, others, "common")

    __or__ = fuse
    __sub__ = cut
    __and__ = common

    def multiFuse(self, others, tolerance=0.0):
        return self.fuse(list(others))

    def extrude(self, vector):
        raise unsupported("extruding a %s" % self.ShapeType.lower())

    def revolve(self, base, axis, angle=360.0):
        raise unsupported("revolving a %s" % self.ShapeType.lower())

    def makeFillet(self, *args):
        raise unsupported("fillets (makeFillet)")

    def makeChamfer(self, *args):
        raise unsupported("chamfers (makeChamfer)")

    def makeThickness(self, *args):
        raise unsupported("hollowing (makeThickness)")

    def makeOffsetShape(self, *args, **kwargs):
        raise unsupported("offset shapes (makeOffsetShape)")

    def section(self, *args):
        raise unsupported("sections")

    def slice(self, *args):
        raise unsupported("slicing shapes")

    def tessellate(self, tolerance=TOLERANCE):
        raise unsupported("tessellating a %s" % self.ShapeType.lower())

    def exportStl(self, filename):
        from tinyfreecad import mesh
        mesh.write_stl([self], filename)

    def __repr__(self):
        return "<%s object at %s>" % (self.ShapeType, hex(id(self)))


# -- vertices, edges and wires --


class Vertex(Shape):
    ShapeType = "Vertex"

    def __init__(self, *args):
        Shape.__init__(self)
        if len(args) == 1:
            self._p = as_array(args[0])
        elif len(args) == 3:
            self._p = np.array([float(a) for a in args])
        else:
            self._p = np.zeros(3)

    def _apply(self, m):
        self._p = m[:3, :3] @ self._p + m[:3, 3]

    def _copy(self):
        return Vertex(self._p)

    def _points(self):
        return self._p.reshape(1, 3)

    @property
    def Point(self):
        return as_vector(self._p)

    @property
    def X(self):
        return float(self._p[0])

    @property
    def Y(self):
        return float(self._p[1])

    @property
    def Z(self):
        return float(self._p[2])

    @property
    def Vertexes(self):
        return [self]


class Edge(Shape):
    """A curve between two parameters (Part.Edge). Make one with
    curve.toShape(), Part.makeLine() or Part.makeCircle()."""

    ShapeType = "Edge"

    def __init__(self, curve=None, first=None, last=None, reversed=False):
        Shape.__init__(self)
        if isinstance(curve, Edge):
            curve, first, last, reversed = curve.Curve, curve._u0, curve._u1, curve._rev
        elif isinstance(curve, Vertex):
            raise unsupported("edges made from vertices; use Part.makeLine()")
        if curve is None:
            curve = geometry.LineSegment()
        self.Curve = curve
        self._u0 = curve.FirstParameter if first is None else float(first)
        self._u1 = curve.LastParameter if last is None else float(last)
        self._rev = bool(reversed)

    def _apply(self, m):
        self.Curve = self.Curve._transformed(m)

    def _copy(self):
        return Edge(self.Curve._transformed(np.identity(4)), self._u0, self._u1, self._rev)

    @property
    def Orientation(self):
        return "Reversed" if self._rev else "Forward"

    @property
    def FirstParameter(self):
        return self._u0

    @property
    def LastParameter(self):
        return self._u1

    @property
    def ParameterRange(self):
        return (self._u0, self._u1)

    def _start(self):
        return self.Curve._eval(self._u1 if self._rev else self._u0)

    def _end(self):
        return self.Curve._eval(self._u0 if self._rev else self._u1)

    def _sample(self, tolerance=TOLERANCE):
        """(points, unit tangents) along the edge, in its direction."""
        us = self.Curve._params(self._u0, self._u1, tolerance)
        pts = np.array([self.Curve._eval(u) for u in us])
        tangents = np.array([_unit(self.Curve._deriv(u)) for u in us])
        if self._rev:
            return pts[::-1].copy(), -tangents[::-1]
        return pts, tangents

    def _points(self):
        return self._sample()[0]

    @property
    def Length(self):
        return self.Curve.length(self._u0, self._u1)

    @property
    def Vertexes(self):
        if self.isClosed():
            return [Vertex(self._start())]
        return [Vertex(self._start()), Vertex(self._end())]

    def firstVertex(self, orientation=False):
        return Vertex(self._start() if orientation else self.Curve._eval(self._u0))

    def lastVertex(self, orientation=False):
        return Vertex(self._end() if orientation else self.Curve._eval(self._u1))

    @property
    def Edges(self):
        return [self]

    def isClosed(self):
        return np.linalg.norm(self._start() - self._end()) < JOIN_TOLERANCE

    def valueAt(self, u):
        return self.Curve.value(u)

    def tangentAt(self, u):
        return self.Curve.tangent(u)[0]

    def derivative1At(self, u):
        return self.Curve.getD1(u)

    def reversed(self):
        e = self.copy()
        e._rev = not self._rev
        return e

    def reverse(self):
        self._rev = not self._rev

    def discretize(self, *args, **kwargs):
        return _discretize(self._sample(TOLERANCE / 20.0)[0], *args, **kwargs)


def _discretize(pts, *args, **kwargs):
    """Points spread evenly (by length) along a polyline: Number=n or
    Distance=d, as FreeCAD's discretize() takes them."""
    number = kwargs.get("Number")
    distance = kwargs.get("Distance")
    if args:
        if isinstance(args[0], int):
            number = args[0]
        else:
            distance = args[0]
    lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    total = lengths[-1]
    if number is None:
        if distance is None:
            raise TypeError("discretize() needs Number or Distance")
        number = max(2, int(math.ceil(total / float(distance))) + 1)
    targets = np.linspace(0.0, total, int(number))
    out = []
    for t in targets:
        i = min(int(np.searchsorted(lengths, t, side="right")) - 1, len(pts) - 2)
        seg = lengths[i + 1] - lengths[i]
        f = (t - lengths[i]) / seg if seg > 0 else 0.0
        out.append(as_vector(pts[i] + f * (pts[i + 1] - pts[i])))
    return out


def _close(a, b):
    return np.linalg.norm(a - b) < JOIN_TOLERANCE


def _chain(edges):
    """Edges joined end to end (reversing any that point the wrong way),
    as BRepBuilderAPI_MakeWire would."""
    remaining = list(edges)
    chain = [remaining.pop(0)]
    while remaining:
        head, tail = chain[0]._start(), chain[-1]._end()
        for i, e in enumerate(remaining):
            s, t = e._start(), e._end()
            if _close(s, tail):
                chain.append(e)
            elif _close(t, tail):
                chain.append(e.reversed())
            elif _close(t, head):
                chain.insert(0, e)
            elif _close(s, head):
                chain.insert(0, e.reversed())
            else:
                continue
            remaining.pop(i)
            break
        else:
            raise OCCError("BRep_API: command not done (the edges don't join up into a wire)")
    return chain


class Wire(Shape):
    """Edges joined end to end (Part.Wire). Part.Wire(edge),
    Part.Wire([edges...]) and Part.Wire([wires...]) are accepted."""

    ShapeType = "Wire"

    def __init__(self, arg=None):
        Shape.__init__(self)
        if arg is None:
            self._edges = []
            return
        items = arg if isinstance(arg, (list, tuple)) else [arg]
        edges = []
        for item in items:
            if isinstance(item, Edge):
                edges.append(item.copy())
            elif isinstance(item, Wire):
                edges.extend(e.copy() for e in item._edges)
            elif isinstance(item, geometry.Curve):
                edges.append(item.toShape())
            else:
                raise TypeError("a wire is made from edges or wires, not %r" % (item,))
        if not edges:
            raise OCCError("BRep_API: command not done (no edges)")
        self._edges = _chain(edges)

    def _apply(self, m):
        for e in self._edges:
            e._apply(m)

    def _copy(self):
        w = Wire()
        w._edges = [e.copy() for e in self._edges]
        return w

    def _points(self):
        return self._sample()[0]

    @property
    def Edges(self):
        return [e.copy() for e in self._edges]

    @property
    def OrderedEdges(self):
        return [e.copy() for e in self._edges]

    @property
    def Vertexes(self):
        pts = [self._edges[0]._start()] + [e._end() for e in self._edges]
        if self.isClosed():
            pts = pts[:-1]
        return [Vertex(p) for p in pts]

    @property
    def OrderedVertexes(self):
        return self.Vertexes

    @property
    def Wires(self):
        return [self]

    def isClosed(self):
        return bool(self._edges) and _close(self._edges[0]._start(), self._edges[-1]._end())

    def reverse(self):
        self._edges = [e.reversed() for e in reversed(self._edges)]

    def reversed(self):
        w = self.copy()
        w.reverse()
        return w

    def _sample(self, tolerance=TOLERANCE):
        """(points, unit tangents) along the wire. Where two edges meet, the
        point is kept once and the tangents of both are averaged."""
        pts, tangents = [], []
        for e in self._edges:
            p, t = e._sample(tolerance)
            if pts:
                tangents[-1] = _unit(tangents[-1] + t[0])
                p, t = p[1:], t[1:]
            pts.extend(p)
            tangents.extend(t)
        pts, tangents = np.array(pts), np.array(tangents)
        if self.isClosed() and len(pts) > 2:
            tangents[0] = tangents[-1] = _unit(tangents[0] + tangents[-1])
        return pts, tangents

    def _polygon(self, tolerance=TOLERANCE):
        """The closed wire as a polygon (Nx3, without the repeated end)."""
        pts = self._sample(tolerance)[0]
        if len(pts) > 1 and _close(pts[0], pts[-1]):
            pts = pts[:-1]
        return pts

    def discretize(self, *args, **kwargs):
        return _discretize(self._sample(TOLERANCE / 20.0)[0], *args, **kwargs)

    def makePipeShell(self, profiles, makeSolid=False, isFrenet=False, transition=0):
        from tinyfreecad import sweep
        return sweep.pipe_shell(self, profiles, makeSolid, isFrenet)

    def makePipe(self, profile):
        from tinyfreecad import sweep
        return sweep.pipe_shell(self, [profile], True, False)

    def extrude(self, vector):
        if self.isClosed():
            raise unsupported("extruding a wire into a shell; make a Part.Face(wire) and extrude that")
        raise unsupported("extruding an open wire")


# -- faces --


class Face(Shape):
    """A flat region bounded by closed wires (Part.Face). Part.Face(wire)
    and Part.Face([outer, hole, ...]) are accepted: wires inside other
    wires make holes, as with FreeCAD's face makers."""

    ShapeType = "Face"

    def __init__(self, arg=None, fill_rule="EvenOdd"):
        Shape.__init__(self)
        self._fill = fill_rule
        if arg is None:
            self._wires = []
            return
        if isinstance(arg, Face):
            self._wires = [w.copy() for w in arg._wires]
            self._fill = arg._fill
            return
        items = arg if isinstance(arg, (list, tuple)) else [arg]
        wires = []
        for item in items:
            if isinstance(item, Wire):
                wires.append(item.copy())
            elif isinstance(item, Edge):
                wires.append(Wire(item))
            elif isinstance(item, Face):
                wires.extend(w.copy() for w in item._wires)
            else:
                raise unsupported("faces made from %r" % (item,))
        for w in wires:
            if not w.isClosed():
                raise OCCError("Part.Face needs closed wires")
        self._wires = wires
        self._frame()

    def _apply(self, m):
        for w in self._wires:
            w._apply(m)

    def _copy(self):
        f = Face(fill_rule=self._fill)
        f._wires = [w.copy() for w in self._wires]
        return f

    def _points(self):
        return np.concatenate([w._points() for w in self._wires]) if self._wires else np.zeros((0, 3))

    def _frame(self):
        """(origin, u, v, normal) of the face's plane."""
        loops = [w._polygon() for w in self._wires]
        best, normal = None, None
        for pts in loops:
            n = _newell(pts)
            if best is None or np.linalg.norm(n) > best:
                best, normal = np.linalg.norm(n), n
        if not best or best < 1e-12:
            raise OCCError("the wires don't enclose an area")
        normal = normal / best
        origin = loops[0][0]
        pts = np.concatenate(loops)
        if np.max(np.abs((pts - origin) @ normal)) > 1e-4 * max(1.0, np.ptp(pts, axis=0).max()):
            raise unsupported("faces that aren't flat")
        u = geometry.default_xdir(normal)
        return origin, u, np.cross(normal, u), normal

    def _polygons2d(self, frame, tolerance=TOLERANCE):
        origin, u, v, _ = frame
        out = []
        for w in self._wires:
            d = w._polygon(tolerance) - origin
            out.append(np.stack([d @ u, d @ v], axis=1))
        return out

    def _cross_section(self, frame=None, flip=False):
        frame = frame or self._frame()
        polys = self._polygons2d(frame)
        if flip:
            polys = [p * np.array([1.0, -1.0]) for p in polys]
        return m3.CrossSection(polys, getattr(m3.FillRule, self._fill))

    @property
    def Area(self):
        return self._cross_section().area() if self._wires else 0.0

    @property
    def Wires(self):
        return [w.copy() for w in self._wires]

    @property
    def OuterWire(self):
        frame = self._frame()
        areas = [abs(_area2d(p)) for p in self._polygons2d(frame)]
        return self._wires[int(np.argmax(areas))].copy()

    @property
    def Edges(self):
        return [e for w in self._wires for e in w.Edges]

    @property
    def Vertexes(self):
        return [v for w in self._wires for v in w.Vertexes]

    @property
    def Faces(self):
        return [self]

    def normalAt(self, u=0.0, v=0.0):
        return as_vector(self._frame()[3])

    def extrude(self, vector):
        """A solid swept from the face along `vector`."""
        origin, u, v, n = self._frame()
        d = as_array(vector)
        if abs(np.dot(d, n)) < 1e-12:
            raise OCCError("can't extrude a face along itself")
        flip = np.dot(d, n) < 0
        vv = -v if flip else v
        m = m3.Manifold.extrude(self._cross_section((origin, u, v, n), flip), 1.0)
        affine = np.column_stack([u, vv, d, origin])
        return Solid([m.transform(affine.tolist())])

    def revolve(self, base, axis, angle=360.0):
        """A solid made by turning the face `angle` degrees about the line
        through `base` along `axis`. The face must lie on one side of the
        line, in a plane containing it."""
        origin, u, v, n = self._frame()
        a = _unit(as_array(axis))
        b = as_array(base)
        if abs(np.dot(a, n)) > 1e-9 or abs(np.dot(b - origin, n)) > 1e-6:
            raise OCCError("the axis must lie in the face's plane")
        x = np.cross(a, n)
        frame = (b, x, a, n)
        polys = self._polygons2d(frame)
        if min(p[:, 0].min() for p in polys) < -1e-9:
            x = -x
            frame = (b, x, a, n)
            polys = self._polygons2d(frame)
        cs = m3.CrossSection(polys, getattr(m3.FillRule, self._fill))
        radius = max(p[:, 0].max() for p in polys)
        segs = geometry.circle_segments(radius)
        m = m3.Manifold.revolve(cs, segs, float(angle))
        # revolve() turns the section's X towards local Y, about local Z.
        affine = np.column_stack([x, np.cross(a, x), a, b])
        return Solid([m.transform(affine.tolist())])


def _newell(pts):
    n = np.zeros(3)
    nxt = np.roll(pts, -1, axis=0)
    n[0] = np.sum((pts[:, 1] - nxt[:, 1]) * (pts[:, 2] + nxt[:, 2]))
    n[1] = np.sum((pts[:, 2] - nxt[:, 2]) * (pts[:, 0] + nxt[:, 0]))
    n[2] = np.sum((pts[:, 0] - nxt[:, 0]) * (pts[:, 1] + nxt[:, 1]))
    return n


def _area2d(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


# -- solids --


class Solid(Shape):
    """A solid (or a compound of solids) as closed triangle meshes."""

    def __init__(self, parts=None, compound=False):
        Shape.__init__(self)
        if isinstance(parts, Shape):
            parts, compound = list(_solid_parts(parts)), False
        self._parts = [p for p in (parts or []) if p is not None]
        self._compound = compound
        self._count_cache = None

    @property
    def ShapeType(self):
        # FreeCAD's booleans hand back a compound, even of one solid; so do
        # these, which is what _compound records.
        if self._compound or len(self._parts) > 1:
            return "Compound"
        return "Solid" if self._count() == 1 else "Compound"

    def _count(self):
        if self._count_cache is None:
            self._count_cache = sum(len(_pieces(p)) for p in self._parts)
        return self._count_cache

    def _apply(self, m):
        affine = m[:3, :].tolist()
        self._parts = [p.transform(affine) for p in self._parts]

    def _copy(self):
        return Solid(list(self._parts), self._compound)

    def _composed(self):
        if len(self._parts) == 1:
            return self._parts[0]
        return m3.Manifold.compose(self._parts) if self._parts else m3.Manifold()

    @staticmethod
    def _boolean(shape, others, op):
        """fuse/cut/common. Like OpenCASCADE, each solid in a compound is
        cut (or intersected) on its own, so a compound stays a compound;
        fuse joins everything into one."""
        operands = []
        for o in others:
            operands.extend(o if isinstance(o, (list, tuple)) else [o])
        mine = list(_solid_parts(shape))
        theirs = [p for o in operands if o is not None for p in _solid_parts(o)]
        if op == "fuse":
            parts = mine + theirs
            return Solid([m3.Manifold.batch_boolean(parts, m3.OpType.Add) if len(parts) > 1 else parts[0]],
                         compound=True)
        if not theirs:
            return Solid(mine if op == "cut" else [], compound=True)
        tool_boxes = [_box(t) for t in theirs]
        results = []
        for part in mine:
            box = _box(part)
            tools = [t for t, tb in zip(theirs, tool_boxes) if _overlap(box, tb)]
            if op == "cut":
                result = m3.Manifold.batch_boolean([part] + tools, m3.OpType.Subtract) if tools else part
            elif not tools:
                continue
            else:
                tool = tools[0] if len(tools) == 1 else m3.Manifold.batch_boolean(tools, m3.OpType.Add)
                result = m3.Manifold.batch_boolean([part, tool], m3.OpType.Intersect)
            if not result.is_empty():
                results.append(result)
        return Solid(results, compound=True)

    def _points(self):
        if not self._parts:
            return np.zeros((0, 3))
        boxes = np.array([p.bounding_box() for p in self._parts if not p.is_empty()])
        if len(boxes) == 0:
            return np.zeros((0, 3))
        return np.array([boxes[:, :3].min(axis=0), boxes[:, 3:].max(axis=0)])

    @property
    def Volume(self):
        return float(sum(p.volume() for p in self._parts))

    @property
    def Area(self):
        return float(sum(p.surface_area() for p in self._parts))

    @property
    def Solids(self):
        return [Solid([piece]) for p in self._parts for piece in _pieces(p)]

    @property
    def CenterOfMass(self):
        verts, tris = self._arrays()
        if len(tris) == 0:
            return Vector()
        a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
        vols = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
        total = vols.sum()
        return as_vector(((a + b + c) / 4.0 * vols[:, None]).sum(axis=0) / total)

    CenterOfGravity = CenterOfMass

    def isNull(self):
        return all(p.is_empty() for p in self._parts)

    def isValid(self):
        return not self.isNull() and all(p.status() == m3.Error.NoError for p in self._parts)

    def isClosed(self):
        return True

    @property
    def Faces(self):
        raise unsupported("the faces of a solid (solids are triangle meshes here)")

    @property
    def Edges(self):
        raise unsupported("the edges of a solid (solids are triangle meshes here)")

    @property
    def Vertexes(self):
        raise unsupported("the vertexes of a solid (solids are triangle meshes here)")

    @property
    def Shells(self):
        raise unsupported("the shells of a solid (solids are triangle meshes here)")

    def _arrays(self):
        """(vertices float64 Nx3, triangles int Mx3) of all the parts."""
        mesh = self._composed().to_mesh64()
        verts = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
        return verts, np.asarray(mesh.tri_verts, dtype=np.int64).reshape(-1, 3)

    def tessellate(self, tolerance=TOLERANCE):
        verts, tris = self._arrays()
        return [as_vector(p) for p in verts], [tuple(int(i) for i in t) for t in tris]


def _box(m):
    return m.bounding_box()


def _overlap(a, b):
    return all(a[i] <= b[i + 3] and b[i] <= a[i + 3] for i in range(3))


def _pieces(m):
    """The separate solids in a manifold. A void inside a solid is a
    separate inward-facing mesh; it goes with the solid around it."""
    comps = m.decompose()
    if len(comps) <= 1:
        return comps
    solids = [c for c in comps if c.volume() > 0]
    voids = [c for c in comps if c.volume() <= 0]
    groups = [[s] for s in solids]
    for v in voids:
        vb = _box(v)
        around = [i for i, s in enumerate(solids)
                  if all(_box(s)[k] <= vb[k] and vb[k + 3] <= _box(s)[k + 3] for k in range(3))]
        if around:
            groups[min(around, key=lambda i: solids[i].volume())].append(v)
        else:
            groups.append([v])
    return [g[0] if len(g) == 1 else m3.Manifold.compose(g) for g in groups]


def _solid_parts(shape):
    """The manifold parts of a solid, or of every solid in a compound."""
    if isinstance(shape, Solid):
        return shape._parts
    if isinstance(shape, Compound):
        return [p for c in shape._children for p in _solid_parts(c)]
    raise unsupported("booleans on a %s (only solids)" % shape.ShapeType.lower())


class Compound(Shape):
    """A group of shapes that aren't all solids (Part.Compound) - the
    faces of a ShapeString, for instance."""

    ShapeType = "Compound"

    def __init__(self, shapes=None):
        Shape.__init__(self)
        self._children = [s.copy() for s in (shapes or [])]

    def _apply(self, m):
        for c in self._children:
            c._apply(m)

    def _copy(self):
        return Compound(self._children)

    def _points(self):
        pts = [c._points() for c in self._children]
        pts = [p for p in pts if len(p)]
        return np.concatenate(pts) if pts else np.zeros((0, 3))

    @property
    def SubShapes(self):
        return [c.copy() for c in self._children]

    def _gather(self, name):
        return [s for c in self._children for s in getattr(c, name)]

    @property
    def Vertexes(self):
        return self._gather("Vertexes")

    @property
    def Edges(self):
        return self._gather("Edges")

    @property
    def Wires(self):
        return self._gather("Wires")

    @property
    def Faces(self):
        return self._gather("Faces")

    @property
    def Solids(self):
        return self._gather("Solids")

    @property
    def Area(self):
        return sum(c.Area for c in self._children)

    @property
    def Volume(self):
        return sum(c.Volume for c in self._children)

    def isNull(self):
        return not self._children

    def extrude(self, vector):
        return make_compound([c.extrude(vector) for c in self._children])

    def revolve(self, base, axis, angle=360.0):
        return make_compound([c.revolve(base, axis, angle) for c in self._children])


def make_compound(shapes):
    """Part.makeCompound: solids become one Solid with several parts;
    anything else becomes a Compound."""
    shapes = [s for s in shapes if s is not None]
    if shapes and all(isinstance(s, Solid) for s in shapes):
        return Solid([p for s in shapes for p in s._parts], compound=True)
    return Compound(shapes)
