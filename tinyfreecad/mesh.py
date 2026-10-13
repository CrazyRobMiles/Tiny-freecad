"""The Mesh module: triangle meshes and STL files.

Mesh.export([objects], "file.stl") writes the shapes of document objects
(or shapes themselves) to one binary STL file, as FreeCAD does.
"""
import os
import re
import struct

import numpy as np

from tinyfreecad.base import BoundBox, as_vector

_RECORD = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])


def _arrays_of(item):
    """(vertices, triangles) of a Mesh, a document object or a shape."""
    from tinyfreecad.topo import Solid, Compound
    if isinstance(item, Mesh):
        return item._verts, item._tris
    if hasattr(item, "Mesh") and isinstance(getattr(item, "Mesh", None), Mesh):
        return item.Mesh._verts, item.Mesh._tris
    shape = item.Shape if hasattr(item, "Shape") else item
    if isinstance(shape, Compound):
        solids = shape.Solids
        if not solids:
            raise ValueError("there are no solids to mesh in %r" % (item,))
        shape = Solid([p for s in solids for p in s._parts])
    if not isinstance(shape, Solid):
        raise ValueError("only solids can be written to a mesh file, not a %s" % shape.ShapeType.lower())
    return shape._arrays()


def _triangles(items):
    chunks = [_arrays_of(i) for i in items]
    verts = [v[t] for v, t in chunks if len(t)]
    return np.concatenate(verts) if verts else np.zeros((0, 3, 3))


def write_stl(items, path, name="tiny-freecad"):
    """Write the triangles of `items` to `path` as a binary STL file."""
    tri = _triangles(items)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0)
    rec = np.zeros(len(tri), dtype=_RECORD)
    rec["n"] = normals
    rec["v"] = tri
    with open(path, "wb") as f:
        f.write(name.encode("ascii", "replace")[:80].ljust(80, b" "))
        f.write(struct.pack("<I", len(tri)))
        f.write(rec.tobytes())


def write_obj(items, path):
    tri = _triangles(items).reshape(-1, 3)
    with open(path, "w") as f:
        for p in tri:
            f.write("v %r %r %r\n" % tuple(float(c) for c in p))
        for i in range(0, len(tri), 3):
            f.write("f %d %d %d\n" % (i + 1, i + 2, i + 3))


def export(objects, filename, tolerance=-1, exportAmfCompressed=True):
    """Write objects' shapes to a mesh file (.stl or .obj)."""
    objects = objects if isinstance(objects, (list, tuple)) else [objects]
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".stl":
        write_stl(objects, filename)
    elif ext == ".obj":
        write_obj(objects, filename)
    else:
        raise NotImplementedError("tiny-freecad can only export meshes as .stl or .obj, not %r" % ext)


_FLOAT = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_VERTEX = re.compile(r"vertex\s+(%s)\s+(%s)\s+(%s)" % (_FLOAT, _FLOAT, _FLOAT))


def read_stl(path):
    """(N*3) x 3 corners of the triangles in an STL file."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + 50 * count:
            rec = np.frombuffer(data, dtype=_RECORD, count=count, offset=84)
            return rec["v"].reshape(-1, 3).astype(np.float64)
    corners = _VERTEX.findall(data.decode("ascii", "replace"))
    return np.array(corners, dtype=np.float64).reshape(-1, 3)


class Mesh(object):
    """Mesh.Mesh: a triangle mesh. Mesh(), Mesh("file.stl"),
    Mesh(shape.tessellate(...)) and Mesh([[p1, p2, p3], ...]) work."""

    def __init__(self, source=None):
        self._verts, self._tris = np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
        if source is None:
            return
        if isinstance(source, str):
            corners = read_stl(source)
            self._set_corners(corners)
        elif isinstance(source, Mesh):
            self._verts, self._tris = source._verts.copy(), source._tris.copy()
        elif isinstance(source, tuple) and len(source) == 2:
            self._verts = np.array([[p[0], p[1], p[2]] for p in source[0]], dtype=float)
            self._tris = np.array(source[1], dtype=np.int64).reshape(-1, 3)
        else:
            self._set_corners(np.array([[p[0], p[1], p[2]] for tri in source for p in tri], dtype=float))

    def _set_corners(self, corners):
        keys, inverse = np.unique(np.round(corners, 6), axis=0, return_inverse=True)
        self._verts, self._tris = keys, inverse.reshape(-1, 3)

    @property
    def CountPoints(self):
        return len(self._verts)

    @property
    def CountFacets(self):
        return len(self._tris)

    @property
    def Points(self):
        return [as_vector(p) for p in self._verts]

    @property
    def Topology(self):
        return [as_vector(p) for p in self._verts], [tuple(int(i) for i in t) for t in self._tris]

    @property
    def Volume(self):
        v = self._verts[self._tris]
        return float(np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0)

    @property
    def Area(self):
        v = self._verts[self._tris]
        return float(np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1).sum() / 2.0)

    @property
    def BoundBox(self):
        if not len(self._verts):
            return BoundBox()
        lo, hi = self._verts.min(axis=0), self._verts.max(axis=0)
        return BoundBox(lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])

    def write(self, path):
        export([self], path)

    def addFacets(self, triangles):
        other = Mesh(triangles)
        self._tris = np.concatenate([self._tris, other._tris + len(self._verts)])
        self._verts = np.concatenate([self._verts, other._verts])

    def translate(self, x, y, z):
        self._verts = self._verts + np.array([x, y, z], dtype=float)

    def copy(self):
        return Mesh(self)
