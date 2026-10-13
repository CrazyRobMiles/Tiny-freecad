"""Curves: Part.LineSegment, Part.Circle, Part.ArcOfCircle (Part.Arc) and
Part.BSplineCurve.

A curve knows its exact shape (value() and derivatives) and how to turn
itself into points no further than TOLERANCE from the true curve, which is
how edges, wires and faces become polygons and meshes.
"""
import math

import numpy as np

from tinyfreecad.base import as_array, as_vector

# Largest distance (mm) a polygon may stray from the curve it stands for.
TOLERANCE = 0.02


# Fewest sides for a full circle: a 48-gon has 0.3% less area than its
# circle, however small the circle is.
MIN_SEGMENTS = 48


def circle_segments(radius, tolerance=TOLERANCE):
    """Sides for a full circle of `radius`: enough to stay within
    `tolerance` of it (and at least MIN_SEGMENTS), rounded up to a
    multiple of 4 so it's symmetric about both axes."""
    if radius <= tolerance:
        return MIN_SEGMENTS
    n = math.ceil(math.pi / math.acos(1.0 - tolerance / radius))
    return int(min(1024, max(MIN_SEGMENTS, 4 * math.ceil(n / 4.0))))


def _unit(a):
    n = np.linalg.norm(a)
    if n == 0:
        raise ValueError("null direction")
    return a / n


def default_xdir(normal):
    """The X direction OpenCASCADE picks for a frame with main direction
    `normal` (gp_Ax2(P, V)), so circles start where FreeCAD's do."""
    vx, vy, vz = normal
    a, b, c = abs(vx), abs(vy), abs(vz)
    if b <= a and b <= c:
        x = (-vz, 0.0, vx) if a > c else (vz, 0.0, -vx)
    elif a <= b and a <= c:
        x = (0.0, -vz, vy) if b > c else (0.0, vz, -vy)
    else:
        x = (-vy, vx, 0.0) if a > b else (vy, -vx, 0.0)
    return _unit(np.array(x, dtype=float))


def _apply_point(m, p):
    return m[:3, :3] @ p + m[:3, 3]


class Curve(object):
    """Base of the curve classes (Part.Geometry)."""

    def value(self, u):
        return as_vector(self._eval(u))

    def tangent(self, u):
        return (as_vector(_unit(self._deriv(u))),)

    def getD1(self, u):
        return as_vector(self._deriv(u))

    @property
    def StartPoint(self):
        return self.value(self.FirstParameter)

    @property
    def EndPoint(self):
        return self.value(self.LastParameter)

    def toShape(self, first=None, last=None):
        from tinyfreecad.topo import Edge
        u0 = self.FirstParameter if first is None else float(first)
        u1 = self.LastParameter if last is None else float(last)
        return Edge(self, u0, u1)

    def isClosed(self):
        return np.linalg.norm(self._eval(self.FirstParameter) - self._eval(self.LastParameter)) < 1e-7

    def copy(self):
        return self._transformed(np.identity(4))

    def transform(self, matrix):
        self.__dict__.update(self._transformed(matrix._a).__dict__)

    def translate(self, v):
        m = np.identity(4)
        m[:3, 3] = as_array(v)
        self.__dict__.update(self._transformed(m).__dict__)

    def length(self, u0=None, u1=None):
        u0 = self.FirstParameter if u0 is None else u0
        u1 = self.LastParameter if u1 is None else u1
        pts = np.array([self._eval(u) for u in self._params(u0, u1, TOLERANCE / 10.0)])
        return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))

    def _params(self, u0, u1, tolerance):
        """Parameters from u0 to u1 whose points stay within `tolerance`."""
        raise NotImplementedError


class LineSegment(Curve):
    """A straight line between two points, parameterised by distance."""

    def __init__(self, p1=None, p2=None):
        self._p1 = as_array(p1) if p1 is not None else np.zeros(3)
        self._p2 = as_array(p2) if p2 is not None else np.array([1.0, 0.0, 0.0])

    @property
    def _len(self):
        return float(np.linalg.norm(self._p2 - self._p1))

    @property
    def FirstParameter(self):
        return 0.0

    @property
    def LastParameter(self):
        return self._len

    def _eval(self, u):
        n = self._len
        return self._p1 + (self._p2 - self._p1) * (u / n if n else 0.0)

    def _deriv(self, u):
        n = self._len
        return (self._p2 - self._p1) / n if n else np.zeros(3)

    def _params(self, u0, u1, tolerance):
        return np.array([u0, u1])

    def length(self, u0=None, u1=None):
        u0 = self.FirstParameter if u0 is None else u0
        u1 = self.LastParameter if u1 is None else u1
        return abs(u1 - u0)

    def _transformed(self, m):
        return LineSegment(_apply_point(m, self._p1), _apply_point(m, self._p2))

    @property
    def Direction(self):
        return as_vector(_unit(self._p2 - self._p1))

    def __repr__(self):
        return "<Line segment (%g,%g,%g) (%g,%g,%g) >" % (tuple(self._p1) + tuple(self._p2))


class Line(LineSegment):
    """Part.Line: FreeCAD's is infinite; here it is the segment between the
    two points it was made from, which is what toShape() gives without
    explicit parameters."""


class Circle(Curve):
    """A full circle: Circle(), Circle(center, normal, radius) or
    Circle(p1, p2, p3) through three points."""

    def __init__(self, *args):
        if len(args) == 3 and isinstance(args[2], (int, float)):
            center, normal, radius = as_array(args[0]), _unit(as_array(args[1])), float(args[2])
            xdir = default_xdir(normal)
        elif len(args) == 3:
            center, normal, radius, xdir = _circle_through(*[as_array(a) for a in args])
        elif not args:
            center, normal, radius = np.zeros(3), np.array([0.0, 0.0, 1.0]), 1.0
            xdir = default_xdir(normal)
        else:
            raise TypeError("Circle(), Circle(center, normal, radius) or Circle(p1, p2, p3)")
        self._set(center, xdir, np.cross(normal, xdir), radius)

    def _set(self, center, xdir, ydir, radius):
        self._c, self._x, self._y, self._r = center, xdir, ydir, float(radius)

    @property
    def Center(self):
        return as_vector(self._c)

    @Center.setter
    def Center(self, v):
        self._c = as_array(v)

    @property
    def Radius(self):
        return self._r

    @Radius.setter
    def Radius(self, r):
        self._r = float(r)

    @property
    def Axis(self):
        return as_vector(np.cross(self._x, self._y))

    @property
    def XAxis(self):
        return as_vector(self._x)

    @property
    def YAxis(self):
        return as_vector(self._y)

    @property
    def FirstParameter(self):
        return 0.0

    @property
    def LastParameter(self):
        return 2.0 * math.pi

    def _eval(self, u):
        return self._c + self._r * (math.cos(u) * self._x + math.sin(u) * self._y)

    def _deriv(self, u):
        return self._r * (-math.sin(u) * self._x + math.cos(u) * self._y)

    def _params(self, u0, u1, tolerance):
        n = max(1, int(math.ceil(circle_segments(self._r, tolerance) * abs(u1 - u0) / (2 * math.pi) - 1e-9)))
        return np.linspace(u0, u1, n + 1)

    def length(self, u0=None, u1=None):
        u0 = self.FirstParameter if u0 is None else u0
        u1 = self.LastParameter if u1 is None else u1
        return self._r * abs(u1 - u0)

    def parameter(self, p):
        d = as_array(p) - self._c
        u = math.atan2(float(np.dot(d, self._y)), float(np.dot(d, self._x)))
        return u if u >= 0 else u + 2 * math.pi

    def _transformed(self, m):
        lin = m[:3, :3]
        x, y = lin @ self._x, lin @ self._y
        sx, sy = np.linalg.norm(x), np.linalg.norm(y)
        if abs(sx - sy) > 1e-9 * max(sx, sy) or abs(np.dot(x, y)) > 1e-9 * sx * sy:
            raise NotImplementedError("a circle can only be moved, turned, mirrored or scaled evenly")
        c = self.__class__.__new__(self.__class__)
        c.__dict__.update(self.__dict__)
        c._set(_apply_point(m, self._c), x / sx, y / sy, self._r * sx)
        return c

    def __repr__(self):
        return "Circle (Radius : %g, Position : (%g, %g, %g), Direction : (%g, %g, %g))" % (
            (self._r,) + tuple(self._c) + tuple(self.Axis))


def _circle_through(p1, p2, p3):
    """(center, normal, radius, xdir) of the circle through three points,
    with xdir pointing at p1 and the points running anticlockwise about
    the normal."""
    a, b = p2 - p1, p3 - p1
    n = np.cross(a, b)
    nn = np.dot(n, n)
    if nn < 1e-24:
        raise ValueError("the three points are on a line")
    center = p1 + (np.dot(b, b) * np.cross(n, a) + np.dot(a, a) * np.cross(b, n)) / (2.0 * nn)
    radius = float(np.linalg.norm(p1 - center))
    return center, _unit(n), radius, _unit(p1 - center)


class ArcOfCircle(Circle):
    """Part of a circle: ArcOfCircle(circle, first, last) (radians) or
    Arc(p1, p2, p3) from p1 through p2 to p3 (Part.Arc)."""

    def __init__(self, *args):
        if len(args) == 3 and isinstance(args[0], Circle):
            circle, u0, u1 = args
            self._set(circle._c.copy(), circle._x.copy(), circle._y.copy(), circle._r)
            self._u0, self._u1 = float(u0), float(u1)
        elif len(args) == 3:
            p1, p2, p3 = (as_array(a) for a in args)
            center, normal, radius, xdir = _circle_through(p1, p2, p3)
            self._set(center, xdir, np.cross(normal, xdir), radius)
            self._u0, self._u1 = 0.0, self.parameter(p3)
        else:
            raise TypeError("ArcOfCircle(circle, first, last) or Arc(p1, p2, p3)")

    @property
    def FirstParameter(self):
        return self._u0

    @property
    def LastParameter(self):
        return self._u1

    @property
    def Circle(self):
        c = Circle.__new__(Circle)
        c._set(self._c.copy(), self._x.copy(), self._y.copy(), self._r)
        return c

    def __repr__(self):
        return "ArcOfCircle (Radius : %g, Position : (%g, %g, %g), Direction : (%g, %g, %g), Parameter : (%g, %g))" % (
            (self._r,) + tuple(self._c) + tuple(self.Axis) + (self._u0, self._u1))


Arc = ArcOfCircle


def _bezier_eval(ctrl, t):
    pts = np.array(ctrl, dtype=float)
    for _ in range(len(pts) - 1):
        pts = pts[:-1] * (1.0 - t) + pts[1:] * t
    return pts[0]


def _bezier_deriv(ctrl, t):
    d = len(ctrl) - 1
    if d == 0:
        return np.zeros(3)
    return d * _bezier_eval(np.diff(ctrl, axis=0), t)


class BSplineCurve(Curve):
    """A smooth curve (Part.BSplineCurve). It is held as a run of Bezier
    pieces, which is exact for any B-spline without weights.

    Make one with interpolate(points, ...) to pass through points, or with
    buildFromPoles(poles, periodic, degree)."""

    def __init__(self, poles=None, *args, **kwargs):
        self._segs = [np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])]
        self._breaks = np.array([0.0, 1.0])
        self._poles = None
        if poles is not None:
            self.buildFromPoles(poles, *args, **kwargs)

    @property
    def FirstParameter(self):
        return float(self._breaks[0])

    @property
    def LastParameter(self):
        return float(self._breaks[-1])

    @property
    def Degree(self):
        return len(self._segs[0]) - 1

    @property
    def NbPoles(self):
        return len(self.getPoles())

    def getPoles(self):
        if self._poles is not None:
            return [as_vector(p) for p in self._poles]
        pts = [self._segs[0][0]]
        for s in self._segs:
            pts.extend(s[1:])
        return [as_vector(p) for p in pts]

    def _locate(self, u):
        i = int(np.searchsorted(self._breaks, u, side="right")) - 1
        i = min(max(i, 0), len(self._segs) - 1)
        h = self._breaks[i + 1] - self._breaks[i]
        return i, (u - self._breaks[i]) / h, h

    def _eval(self, u):
        i, t, _ = self._locate(u)
        return _bezier_eval(self._segs[i], t)

    def _deriv(self, u):
        i, t, h = self._locate(u)
        return _bezier_deriv(self._segs[i], t) / h

    def _params(self, u0, u1, tolerance):
        lo, hi = min(u0, u1), max(u0, u1)
        params = [lo]
        for i, seg in enumerate(self._segs):
            b0, b1 = self._breaks[i], self._breaks[i + 1]
            if b1 <= lo or b0 >= hi:
                continue
            d = len(seg) - 1
            m = float(np.max(np.linalg.norm(np.diff(seg, n=2, axis=0), axis=1))) if d >= 2 else 0.0
            n = max(1, int(math.ceil(math.sqrt(d * (d - 1) * m / (8.0 * tolerance))))) if m > 0 else 1
            for k in range(1, n + 1):
                u = b0 + (b1 - b0) * k / n
                if lo < u < hi:
                    params.append(u)
        params.append(hi)
        params = np.array(params)
        return params if u1 >= u0 else params[::-1]

    def _transformed(self, m):
        c = BSplineCurve()
        c._segs = [np.array([_apply_point(m, p) for p in s]) for s in self._segs]
        c._breaks = self._breaks.copy()
        c._poles = None if self._poles is None else np.array([_apply_point(m, p) for p in self._poles])
        return c

    # -- construction --

    def interpolate(self, Points=None, PeriodicFlag=False, Tolerance=1e-6, InitialTangent=None,
                    FinalTangent=None, Tangents=None, TangentFlags=None, Parameters=None, Scale=True, **kwargs):
        """Pass a curve through Points, like OpenCASCADE's
        GeomAPI_Interpolate: chord-length parameters, a cubic with
        not-a-knot ends, or clamped to InitialTangent/FinalTangent when both
        are given."""
        points = Points if Points is not None else kwargs.get("points")
        pts = np.array([as_array(p) for p in points])
        if PeriodicFlag:
            raise NotImplementedError("periodic interpolation is not supported")
        if Tangents is not None:
            raise NotImplementedError("per-point tangents are not supported")
        if len(pts) < 2:
            raise ValueError("at least two points are needed")
        if Parameters is not None:
            params = np.array([float(p) for p in Parameters])
        else:
            steps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
            params = np.concatenate([[0.0], np.cumsum(steps)])
        h = np.diff(params)
        clamped = InitialTangent is not None and FinalTangent is not None
        n = len(pts)
        if not clamped and n == 2:
            self._from_hermite(pts, params, np.array([(pts[1] - pts[0]) / h[0]] * 2))
            return
        if not clamped and n == 3:
            # OpenCASCADE drops to a parabola through three points.
            t = (params[1] - params[0]) / (params[2] - params[0])
            ctrl = (pts[1] - (1 - t) ** 2 * pts[0] - t * t * pts[2]) / (2 * t * (1 - t))
            quad = np.array([pts[0], ctrl, pts[2]])
            self._segs = [np.array([quad[0], (quad[0] + 2 * quad[1]) / 3, (2 * quad[1] + quad[2]) / 3, quad[2]])]
            self._breaks = np.array([params[0], params[2]])
            self._poles = None
            return
        delta = np.diff(pts, axis=0) / h[:, None]
        a = np.zeros((n, n))
        rhs = np.zeros((n, 3))
        for i in range(1, n - 1):
            a[i, i - 1], a[i, i], a[i, i + 1] = h[i], 2 * (h[i - 1] + h[i]), h[i - 1]
            rhs[i] = 3 * (h[i] * delta[i - 1] + h[i - 1] * delta[i])
        if clamped:
            t0, t1 = as_array(InitialTangent), as_array(FinalTangent)
            if Scale:
                # OpenCASCADE's ScaleTangents: each tangent takes the size
                # (sum of absolute components) of the derivative, at its
                # point, of the polynomial through the first three points.
                k = min(3, n)
                t0 = t0 * np.abs(_poly_deriv(pts[:k], params[:k], params[0])).sum() / np.abs(t0).sum()
                t1 = t1 * np.abs(_poly_deriv(pts[:k], params[:k], params[-1])).sum() / np.abs(t1).sum()
        else:
            # OpenCASCADE's BuildTangents: the end derivatives of the cubics
            # through the first four and the last four points.
            t0 = _poly_deriv(pts[:4], params[:4], params[0])
            t1 = _poly_deriv(pts[-4:], params[-4:], params[-1])
        a[0, 0], rhs[0] = 1.0, t0
        a[-1, -1], rhs[-1] = 1.0, t1
        self._from_hermite(pts, params, np.linalg.solve(a, rhs))

    def _from_hermite(self, pts, params, derivs):
        segs = []
        for i in range(len(pts) - 1):
            h = params[i + 1] - params[i]
            segs.append(np.array([pts[i], pts[i] + h * derivs[i] / 3.0, pts[i + 1] - h * derivs[i + 1] / 3.0,
                                  pts[i + 1]]))
        self._segs, self._breaks, self._poles = segs, np.array(params, dtype=float), None

    def buildFromPoles(self, poles, periodic=False, degree=3, interpolate=False):
        """A clamped, uniform B-spline with these control points."""
        if periodic:
            raise NotImplementedError("periodic B-splines are not supported")
        p = np.array([as_array(v) for v in poles])
        degree = min(int(degree), len(p) - 1)
        inner = len(p) - degree - 1
        knots = [0.0] * (degree + 1) + [float(k) for k in range(1, inner + 1)] + [float(inner + 1)] * (degree + 1)
        self._set_from_bspline(p, knots, degree)

    def buildFromPolesMultsKnots(self, poles, mults=None, knots=None, periodic=False, degree=3, weights=None,
                                 CheckRational=False):
        if weights is not None and len(set(weights)) > 1:
            raise NotImplementedError("rational B-splines are not supported")
        if periodic:
            raise NotImplementedError("periodic B-splines are not supported")
        p = np.array([as_array(v) for v in poles])
        flat = []
        for k, m in zip(knots, mults):
            flat.extend([float(k)] * int(m))
        self._set_from_bspline(p, flat, int(degree))

    def _set_from_bspline(self, poles, knots, degree):
        """Split a clamped B-spline into Bezier pieces by knot insertion."""
        knots = list(knots)
        ctrl = [np.array(c) for c in poles]
        distinct = sorted(set(knots[degree + 1:-degree - 1]))
        for k in distinct:
            while knots.count(k) < degree:
                ctrl, knots = _insert_knot(ctrl, knots, degree, k)
        breaks = sorted(set(knots))
        segs = [np.array(ctrl[i * degree:i * degree + degree + 1]) for i in range(len(breaks) - 1)]
        self._segs, self._breaks, self._poles = segs, np.array(breaks), poles


def _poly_deriv(pts, params, at):
    """Derivative at `at` of the polynomial through `pts` at `params`
    (Lagrange interpolation, as OpenCASCADE's PLib::EvalLagrange)."""
    total = np.zeros(3)
    for i in range(len(pts)):
        others = [j for j in range(len(pts)) if j != i]
        denom = np.prod([params[i] - params[j] for j in others])
        numer = sum(np.prod([at - params[j] for j in others if j != k]) for k in others)
        total += pts[i] * numer / denom
    return total


def _insert_knot(ctrl, knots, degree, u):
    """Boehm's knot insertion: one more knot at u."""
    k = max(i for i in range(len(knots) - 1) if knots[i] <= u < knots[i + 1])
    new = []
    for i in range(len(ctrl) + 1):
        if i <= k - degree:
            new.append(ctrl[i])
        elif i > k:
            new.append(ctrl[i - 1])
        else:
            a = (u - knots[i]) / (knots[i + degree] - knots[i])
            new.append((1 - a) * ctrl[i - 1] + a * ctrl[i])
    return new, knots[:k + 1] + [u] + knots[k + 1:]
