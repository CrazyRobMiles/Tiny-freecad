"""Sweeps (Wire.makePipeShell) and lofts (Part.makeLoft) as meshes.

A sweep carries the profile along the path on rotation-minimising frames,
which is what OpenCASCADE's "corrected Frenet" mode approximates: the
profile doesn't twist about the path. A loft joins each section to the
next with straight rulings.

Either way the rings of points are stitched into one closed mesh. As in
FreeCAD, a path that bends tighter than the profile is wide, or runs back
through itself, gives a solid that overlaps itself.
"""
import numpy as np
import manifold3d as m3

from tinyfreecad import geometry
from tinyfreecad.topo import OCCError, Solid, Wire, unsupported, _unit, _newell


def _frames(points, tangents, frenet=False):
    """A unit normal for each path point (double reflection, Wang et al.
    2008), so the frame turns as little as possible along the path."""
    normals = [geometry.default_xdir(tangents[0])]
    for i in range(len(points) - 1):
        v1 = points[i + 1] - points[i]
        c1 = np.dot(v1, v1)
        if c1 < 1e-24:
            normals.append(normals[-1])
            continue
        r_l = normals[-1] - (2.0 / c1) * np.dot(v1, normals[-1]) * v1
        t_l = tangents[i] - (2.0 / c1) * np.dot(v1, tangents[i]) * v1
        v2 = tangents[i + 1] - t_l
        c2 = np.dot(v2, v2)
        r_next = r_l - (2.0 / c2) * np.dot(v2, r_l) * v2 if c2 > 1e-24 else r_l
        r_next = r_next - np.dot(r_next, tangents[i + 1]) * tangents[i + 1]
        normals.append(_unit(r_next))
    return np.array(normals)


def _plane_coords(poly):
    """A planar polygon (Nx3) in 2D coordinates of its own plane."""
    n = _unit(_newell(poly))
    u = geometry.default_xdir(n)
    v = np.cross(n, u)
    d = poly - poly[0]
    return np.stack([d @ u, d @ v], axis=1)


def _stitch(rings, closed):
    """A closed mesh joining rings of equal size, capped at the ends
    unless the rings go round in a loop."""
    count, n = len(rings), len(rings[0])
    verts = np.concatenate(rings)
    tris = []
    last = count if closed else count - 1
    for i in range(last):
        a, b = i * n, ((i + 1) % count) * n
        for j in range(n):
            k = (j + 1) % n
            tris.append((a + j, b + k, b + j))
            tris.append((a + j, a + k, b + k))
    if not closed:
        for t in np.asarray(m3.triangulate([_plane_coords(rings[0])])).reshape(-1, 3):
            tris.append((int(t[0]), int(t[2]), int(t[1])))
        end = (count - 1) * n
        for t in np.asarray(m3.triangulate([_plane_coords(rings[-1])])).reshape(-1, 3):
            tris.append((end + int(t[0]), end + int(t[1]), end + int(t[2])))
    tris = np.array(tris, dtype=np.int64)
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    if np.einsum("ij,ij->", a, np.cross(b, c)) < 0:
        tris = tris[:, ::-1]
    # Double precision, so faces meant to be flush with other solids are.
    m = m3.Manifold(m3.Mesh64(vert_properties=np.ascontiguousarray(verts, dtype=np.float64),
                              tri_verts=np.ascontiguousarray(tris, dtype=np.uint64)))
    if m.status() != m3.Error.NoError:
        raise OCCError("the sweep couldn't be made into a solid (%s)" % m.status())
    return m


def pipe_shell(path, profiles, make_solid=True, frenet=False):
    """Sweep a closed profile wire along a path wire (or edge)."""
    if not isinstance(path, Wire):
        path = Wire(path)
    profiles = profiles if isinstance(profiles, (list, tuple)) else [profiles]
    if len(profiles) != 1:
        raise unsupported("sweeps through more than one profile")
    profile = profiles[0] if isinstance(profiles[0], Wire) else Wire(profiles[0])
    if not profile.isClosed():
        raise unsupported("sweeping open profiles (the result would be a shell, not a solid)")

    points, tangents = path._sample(geometry.TOLERANCE / 4.0)
    closed = path.isClosed()
    if closed:
        points, tangents = points[:-1], tangents[:-1]
    normals = _frames(points, tangents, frenet)
    binormals = np.cross(tangents, normals)

    # The profile, in the path's frame at its start.
    ring = profile._polygon()
    rel = ring - points[0]
    local = np.stack([rel @ normals[0], rel @ binormals[0], rel @ tangents[0]], axis=1)
    rings = [p + local[:, 0:1] * n + local[:, 1:2] * b + local[:, 2:3] * t
             for p, n, b, t in zip(points, normals, binormals, tangents)]

    return Solid([_stitch(rings, closed)])


def _ring(wire, count=None):
    """A closed wire as `count` points spread by length (or its corners,
    if it is a polygon and count is None)."""
    if count is None:
        return wire._polygon()
    pts = wire._sample(geometry.TOLERANCE / 4.0)[0]
    if np.linalg.norm(pts[0] - pts[-1]) > 1e-9:
        pts = np.concatenate([pts, pts[:1]])
    from tinyfreecad.topo import _discretize
    return np.array([list(v) for v in _discretize(pts, count + 1)])[:-1]


def loft(sections, solid=True, ruled=False, closed=False):
    """Part.makeLoft: join closed wires with ruled surfaces."""
    wires = [s if isinstance(s, Wire) else Wire(s) for s in sections]
    if len(wires) < 2:
        raise OCCError("a loft needs at least two sections")
    if not all(w.isClosed() for w in wires):
        raise unsupported("lofting open wires (the result would be a shell, not a solid)")
    corners = [w._polygon() for w in wires]
    polygons = all(all(isinstance(e.Curve, geometry.LineSegment) for e in w._edges) for w in wires)
    if polygons and len(set(len(c) for c in corners)) == 1:
        rings = corners
    else:
        count = max(len(w._polygon()) for w in wires)
        rings = [_ring(w, count) for w in wires]
    # Run every ring the same way round as the first.
    ref = _newell(rings[0])
    rings = [r if np.dot(_newell(r), ref) >= 0 else np.concatenate([r[:1], r[1:][::-1]]) for r in rings]
    return Solid([_stitch(rings, closed)])
