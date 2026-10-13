"""FreeCAD's Base types: Vector, Matrix, Rotation, Placement and BoundBox.

These follow FreeCAD's behaviour where scripts can see it (Vector * Vector
is a dot product, normalize() works in place, Matrix.rotateZ() applies its
rotation after whatever the matrix already does, and so on).
"""
import math

import numpy as np


class Vector(object):
    """A 3D point or direction (FreeCAD.Vector / FreeCAD.Base.Vector)."""

    __slots__ = ("x", "y", "z")
    __hash__ = None

    def __init__(self, x=0.0, y=0.0, z=0.0):
        if not isinstance(x, (int, float, np.floating, np.integer)):
            x, y, z = (list(x) + [0.0, 0.0, 0.0])[:3]
        self.x, self.y, self.z = float(x), float(y), float(z)

    # -- sequence behaviour --

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __len__(self):
        return 3

    def __getitem__(self, i):
        return (self.x, self.y, self.z)[i]

    def __setitem__(self, i, value):
        setattr(self, "xyz"[i], float(value))

    # -- arithmetic --

    def __add__(self, o):
        return Vector(self.x + o[0], self.y + o[1], self.z + o[2])

    def __sub__(self, o):
        return Vector(self.x - o[0], self.y - o[1], self.z - o[2])

    def __neg__(self):
        return Vector(-self.x, -self.y, -self.z)

    def __mul__(self, o):
        if isinstance(o, Vector):
            return self.dot(o)
        return Vector(self.x * o, self.y * o, self.z * o)

    def __rmul__(self, k):
        return Vector(self.x * k, self.y * k, self.z * k)

    def __truediv__(self, k):
        return Vector(self.x / k, self.y / k, self.z / k)

    def __eq__(self, o):
        if not isinstance(o, Vector):
            return NotImplemented
        return self.x == o.x and self.y == o.y and self.z == o.z

    def __ne__(self, o):
        result = self.__eq__(o)
        return result if result is NotImplemented else not result

    def __repr__(self):
        return "Vector (%r, %r, %r)" % (self.x, self.y, self.z)

    def __copy__(self):
        return Vector(self.x, self.y, self.z)

    def __deepcopy__(self, memo):
        return Vector(self.x, self.y, self.z)

    def __reduce__(self):
        return (Vector, (self.x, self.y, self.z))

    # -- FreeCAD's methods --

    def add(self, o):
        return self + o

    def sub(self, o):
        return self - o

    def negative(self):
        return -self

    def dot(self, o):
        return self.x * o[0] + self.y * o[1] + self.z * o[2]

    def cross(self, o):
        return Vector(self.y * o[2] - self.z * o[1],
                      self.z * o[0] - self.x * o[2],
                      self.x * o[1] - self.y * o[0])

    @property
    def Length(self):
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    @Length.setter
    def Length(self, value):
        n = self.Length
        if n == 0:
            raise ValueError("Cannot set the length of a null vector")
        self.multiply(value / n)

    def normalize(self):
        n = self.Length
        if n == 0:
            raise ValueError("Cannot normalize null vector")
        self.x, self.y, self.z = self.x / n, self.y / n, self.z / n
        return self

    def multiply(self, k):
        self.x, self.y, self.z = self.x * k, self.y * k, self.z * k
        return self

    def scale(self, x, y, z):
        self.x, self.y, self.z = self.x * x, self.y * y, self.z * z
        return self

    def distanceToPoint(self, p):
        return (self - p).Length

    def getAngle(self, o):
        a, b = self.Length, Vector(*o).Length
        if a == 0 or b == 0:
            return float("nan")
        return math.acos(max(-1.0, min(1.0, self.dot(o) / (a * b))))

    def isEqual(self, o, tolerance=0.0):
        return (self - o).Length <= tolerance

    def isParallel(self, o, tolerance=1e-7):
        return self.cross(o).Length <= tolerance * self.Length * Vector(*o).Length

    def projectToPlane(self, base, normal):
        n = Vector(*normal).normalize()
        d = (self - base).dot(n)
        self.x, self.y, self.z = self.x - d * n.x, self.y - d * n.y, self.z - d * n.z
        return self

    def distanceToPlane(self, base, normal):
        n = Vector(*normal).normalize()
        return (self - base).dot(n)


def as_array(v):
    """A Vector (or any 3-sequence, or None for the origin) as a numpy array."""
    if v is None:
        return np.zeros(3)
    return np.array([float(v[0]), float(v[1]), float(v[2])])


def as_vector(a):
    return Vector(float(a[0]), float(a[1]), float(a[2]))


class Matrix(object):
    """A 4x4 transformation matrix (FreeCAD.Matrix)."""

    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Matrix):
            self._a = args[0]._a.copy()
        elif len(args) == 1 and isinstance(args[0], np.ndarray):
            self._a = np.array(args[0], dtype=float).reshape(4, 4)
        elif args:
            values = [float(v) for v in args] + [0.0] * (16 - len(args))
            self._a = np.array(values).reshape(4, 4)
            if len(args) < 16:
                self._a[3, 3] = 1.0
        else:
            self._a = np.identity(4)

    @property
    def A(self):
        return tuple(self._a.flatten())

    @A.setter
    def A(self, values):
        self._a = np.array([float(v) for v in values]).reshape(4, 4)

    def __getattr__(self, name):
        if len(name) == 3 and name[0] == "A" and name[1:].isdigit():
            return float(self._a[int(name[1]) - 1, int(name[2]) - 1])
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if len(name) == 3 and name[0] == "A" and name[1:].isdigit():
            self._a[int(name[1]) - 1, int(name[2]) - 1] = float(value)
        else:
            object.__setattr__(self, name, value)

    def __mul__(self, o):
        if isinstance(o, Matrix):
            return Matrix(self._a @ o._a)
        if isinstance(o, Vector):
            return self.multVec(o)
        raise TypeError("Matrix can only be multiplied by a Matrix or a Vector")

    def __eq__(self, o):
        return isinstance(o, Matrix) and np.array_equal(self._a, o._a)

    __hash__ = None

    def __repr__(self):
        return "Matrix (%s)" % ", ".join("(%s)" % ",".join(repr(float(v)) for v in row) for row in self._a)

    def multiply(self, o):
        return self * o

    def multVec(self, v):
        p = self._a @ np.array([v[0], v[1], v[2], 1.0])
        return Vector(p[0], p[1], p[2])

    def _pre(self, m):
        self._a = m @ self._a
        return self

    def move(self, *args):
        v = args[0] if len(args) == 1 else args
        self._a[0, 3] += v[0]
        self._a[1, 3] += v[1]
        self._a[2, 3] += v[2]
        return self

    def rotateX(self, angle):
        c, s = math.cos(angle), math.sin(angle)
        return self._pre(np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1.0]]))

    def rotateY(self, angle):
        c, s = math.cos(angle), math.sin(angle)
        return self._pre(np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]]))

    def rotateZ(self, angle):
        c, s = math.cos(angle), math.sin(angle)
        return self._pre(np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0]]))

    def scale(self, *args):
        if len(args) == 1:
            a = args[0]
            sx, sy, sz = (a, a, a) if isinstance(a, (int, float)) else (a[0], a[1], a[2])
        else:
            sx, sy, sz = args
        return self._pre(np.diag([float(sx), float(sy), float(sz), 1.0]))

    def inverse(self):
        return Matrix(np.linalg.inv(self._a))

    def transposed(self):
        return Matrix(self._a.T.copy())

    def transpose(self):
        self._a = self._a.T.copy()

    def determinant(self):
        return float(np.linalg.det(self._a))

    def unity(self):
        self._a = np.identity(4)

    def isUnity(self):
        return np.allclose(self._a, np.identity(4))

    def copy(self):
        return Matrix(self)


def _quat_from_axis_angle(axis, angle):
    a = as_array(axis)
    n = np.linalg.norm(a)
    if n == 0:
        return np.array([0.0, 0.0, 0.0, 1.0])
    a = a / n
    s = math.sin(angle / 2.0)
    return np.array([a[0] * s, a[1] * s, a[2] * s, math.cos(angle / 2.0)])


def _quat_mul(q, r):
    x1, y1, z1, w1 = q
    x2, y2, z2, w2 = r
    return np.array([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
                     w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2])


def _quat_from_matrix(m):
    m = np.asarray(m)[:3, :3]
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    return q / np.linalg.norm(q)


class Rotation(object):
    """A rotation (FreeCAD.Rotation), held as a quaternion (x, y, z, w).

    Rotation(), Rotation(axis, degrees), Rotation(yaw, pitch, roll),
    Rotation(x, y, z, w), Rotation(Matrix) and Rotation(from, to) are
    accepted."""

    def __init__(self, *args):
        if not args:
            q = [0.0, 0.0, 0.0, 1.0]
        elif len(args) == 1 and isinstance(args[0], Rotation):
            q = args[0]._q
        elif len(args) == 1 and isinstance(args[0], Matrix):
            q = _quat_from_matrix(args[0]._a)
        elif len(args) == 2 and isinstance(args[1], (int, float)):
            q = _quat_from_axis_angle(args[0], math.radians(args[1]))
        elif len(args) == 2:
            a, b = as_array(args[0]), as_array(args[1])
            a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
            axis = np.cross(a, b)
            if np.linalg.norm(axis) < 1e-12:
                if np.dot(a, b) > 0:
                    q = [0.0, 0.0, 0.0, 1.0]
                else:
                    perp = np.cross(a, [1.0, 0.0, 0.0])
                    if np.linalg.norm(perp) < 1e-6:
                        perp = np.cross(a, [0.0, 1.0, 0.0])
                    q = _quat_from_axis_angle(perp, math.pi)
            else:
                q = _quat_from_axis_angle(axis, math.acos(max(-1.0, min(1.0, float(np.dot(a, b))))))
        elif len(args) == 3:
            yaw, pitch, roll = (math.radians(a) for a in args)
            q = _quat_mul(_quat_mul(_quat_from_axis_angle((0, 0, 1), yaw), _quat_from_axis_angle((0, 1, 0), pitch)),
                          _quat_from_axis_angle((1, 0, 0), roll))
        elif len(args) == 4:
            q = np.array([float(a) for a in args])
            q = q / np.linalg.norm(q)
        else:
            raise TypeError("Unsupported Rotation arguments %r" % (args,))
        self._q = np.array(q, dtype=float)

    @property
    def Q(self):
        return tuple(float(v) for v in self._q)

    @property
    def Angle(self):
        return 2.0 * math.acos(max(-1.0, min(1.0, self._q[3])))

    @property
    def Axis(self):
        v = self._q[:3]
        n = np.linalg.norm(v)
        return Vector(0, 0, 1) if n < 1e-15 else as_vector(v / n)

    def _matrix3(self):
        x, y, z, w = self._q
        return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])

    def toMatrix(self):
        m = np.identity(4)
        m[:3, :3] = self._matrix3()
        return Matrix(m)

    def multVec(self, v):
        return as_vector(self._matrix3() @ as_array(v))

    def multiply(self, o):
        return Rotation(*_quat_mul(self._q, o._q))

    __mul__ = multiply

    def inverted(self):
        x, y, z, w = self._q
        return Rotation(-x, -y, -z, w)

    def isIdentity(self):
        return abs(abs(self._q[3]) - 1.0) < 1e-12

    def toEuler(self):
        m = self._matrix3()
        pitch = math.asin(max(-1.0, min(1.0, -m[2, 0])))
        yaw = math.atan2(m[1, 0], m[0, 0])
        roll = math.atan2(m[2, 1], m[2, 2])
        return tuple(math.degrees(a) for a in (yaw, pitch, roll))

    getYawPitchRoll = toEuler

    def __repr__(self):
        return "Rotation (%r, %r, %r, %r)" % self.Q


class Placement(object):
    """A position and a rotation (FreeCAD.Placement)."""

    def __init__(self, *args):
        if not args:
            self.Base, self.Rotation = Vector(), Rotation()
        elif len(args) == 1 and isinstance(args[0], Placement):
            self.Base, self.Rotation = Vector(*args[0].Base), Rotation(args[0].Rotation)
        elif len(args) == 1 and isinstance(args[0], Matrix):
            a = args[0]._a
            self.Base, self.Rotation = Vector(a[0, 3], a[1, 3], a[2, 3]), Rotation(args[0])
        elif len(args) == 2:
            self.Base, self.Rotation = Vector(*args[0]), Rotation(args[1])
        elif len(args) == 3 and isinstance(args[1], Rotation):
            # Placement(base, rotation, center)
            base, rot, center = Vector(*args[0]), args[1], Vector(*args[2])
            self.Base, self.Rotation = base + center - rot.multVec(center), Rotation(rot)
        elif len(args) == 3:
            self.Base, self.Rotation = Vector(*args[0]), Rotation(args[1], args[2])
        else:
            raise TypeError("Unsupported Placement arguments %r" % (args,))

    def toMatrix(self):
        m = self.Rotation.toMatrix()
        m._a[:3, 3] = as_array(self.Base)
        return m

    @property
    def Matrix(self):
        return self.toMatrix()

    @Matrix.setter
    def Matrix(self, m):
        p = Placement(m)
        self.Base, self.Rotation = p.Base, p.Rotation

    def multVec(self, v):
        return self.Rotation.multVec(v) + self.Base

    def multiply(self, o):
        return Placement(self.toMatrix() * o.toMatrix())

    __mul__ = multiply

    def inverse(self):
        return Placement(self.toMatrix().inverse())

    def move(self, v):
        self.Base = self.Base + v

    def isIdentity(self):
        return self.Base.Length == 0 and self.Rotation.isIdentity()

    def copy(self):
        return Placement(self)

    def __repr__(self):
        return "Placement [Pos=(%g,%g,%g), Yaw-Pitch-Roll=(%g,%g,%g)]" % (
            tuple(self.Base) + self.Rotation.toEuler())


class BoundBox(object):
    """An axis-aligned bounding box (FreeCAD.BoundBox)."""

    def __init__(self, *args):
        inf = float("inf")
        self.XMin = self.YMin = self.ZMin = inf
        self.XMax = self.YMax = self.ZMax = -inf
        if len(args) == 6:
            self.XMin, self.YMin, self.ZMin, self.XMax, self.YMax, self.ZMax = (float(a) for a in args)
        elif len(args) == 2:
            self.add(args[0])
            self.add(args[1])
        elif len(args) == 1 and isinstance(args[0], BoundBox):
            self.add(args[0])

    def isValid(self):
        return self.XMin <= self.XMax and self.YMin <= self.YMax and self.ZMin <= self.ZMax

    def add(self, o):
        if isinstance(o, BoundBox):
            if not o.isValid():
                return
            lo, hi = (o.XMin, o.YMin, o.ZMin), (o.XMax, o.YMax, o.ZMax)
        else:
            lo = hi = (float(o[0]), float(o[1]), float(o[2]))
        self.XMin, self.YMin, self.ZMin = min(self.XMin, lo[0]), min(self.YMin, lo[1]), min(self.ZMin, lo[2])
        self.XMax, self.YMax, self.ZMax = max(self.XMax, hi[0]), max(self.YMax, hi[1]), max(self.ZMax, hi[2])

    @property
    def XLength(self):
        return self.XMax - self.XMin

    @property
    def YLength(self):
        return self.YMax - self.YMin

    @property
    def ZLength(self):
        return self.ZMax - self.ZMin

    @property
    def Center(self):
        return Vector((self.XMin + self.XMax) / 2, (self.YMin + self.YMax) / 2, (self.ZMin + self.ZMax) / 2)

    @property
    def DiagonalLength(self):
        return math.sqrt(self.XLength ** 2 + self.YLength ** 2 + self.ZLength ** 2)

    def enlarge(self, d):
        self.XMin, self.YMin, self.ZMin = self.XMin - d, self.YMin - d, self.ZMin - d
        self.XMax, self.YMax, self.ZMax = self.XMax + d, self.YMax + d, self.ZMax + d

    def isInside(self, o):
        if isinstance(o, BoundBox):
            return self.isInside((o.XMin, o.YMin, o.ZMin)) and self.isInside((o.XMax, o.YMax, o.ZMax))
        return (self.XMin <= o[0] <= self.XMax and self.YMin <= o[1] <= self.YMax
                and self.ZMin <= o[2] <= self.ZMax)

    def intersect(self, o):
        return (self.XMin <= o.XMax and o.XMin <= self.XMax and self.YMin <= o.YMax and o.YMin <= self.YMax
                and self.ZMin <= o.ZMax and o.ZMin <= self.ZMax)

    def __repr__(self):
        return "BoundBox (%g, %g, %g, %g, %g, %g)" % (self.XMin, self.YMin, self.ZMin,
                                                     self.XMax, self.YMax, self.ZMax)
