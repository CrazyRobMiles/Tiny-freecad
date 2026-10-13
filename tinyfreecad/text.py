"""Text as faces, the way Draft.makeShapeString lays it out.

Glyph outlines come from the font file (TrueType or OpenType, read with
fontTools), with the font's kerning. Like FreeCAD 1.0's ShapeString
(Justification "Bottom-Left", "Scale to size" with the cap height as
reference), the text is scaled so that a capital letter is `size` tall,
sits on the baseline at y = 0 and starts at x = 0.
"""
import math

import numpy as np

from tinyfreecad import geometry
from tinyfreecad.part import makePolygon
from tinyfreecad.topo import Compound, Face

# FreeCAD loads glyphs through FreeType at 60 pixels per em and scales by
# the cap height rounded to whole pixels; doing the same keeps text the
# same width as FreeCAD's to within a few microns.
_FT_PIXELS_PER_EM = 60.0

_fonts = {}


def _font(path):
    if path not in _fonts:
        import io
        from fontTools.ttLib import TTFont
        with open(path, "rb") as f:  # read it all, so the file isn't left open
            _fonts[path] = TTFont(io.BytesIO(f.read()), lazy=True)
    return _fonts[path]


def _cap_height(font):
    cap = getattr(font.get("OS/2"), "sCapHeight", 0) if "OS/2" in font else 0
    if not cap:
        glyphs = font.getGlyphSet()
        name = font.getBestCmap().get(ord("H"))
        if name is None:
            return font["head"].unitsPerEm * 0.7
        from fontTools.pens.boundsPen import BoundsPen
        pen = BoundsPen(glyphs)
        glyphs[name].draw(pen)
        cap = pen.bounds[3]
    return cap


def _kerning(font):
    pairs = {}
    if "kern" in font:
        for table in font["kern"].kernTables:
            pairs.update(getattr(table, "kernTable", {}))
    return pairs


def _make_pen(glyphs, tolerance_units):
    from fontTools.pens.basePen import BasePen

    class FlatPen(BasePen):
        """Collects each contour as a list of points, curves flattened."""

        def __init__(self):
            BasePen.__init__(self, glyphs)
            self.contours, self._points = [], None

        def _moveTo(self, p):
            self._points = [p]

        def _lineTo(self, p):
            self._points.append(p)

        def _flatten(self, ctrl):
            ctrl = np.array([self._points[-1]] + list(ctrl), dtype=float)
            d = len(ctrl) - 1
            m = float(np.max(np.linalg.norm(np.diff(ctrl, n=2, axis=0), axis=1)))
            n = max(1, int(math.ceil(math.sqrt(d * (d - 1) * m / (8.0 * tolerance_units)))))
            for k in range(1, n + 1):
                self._points.append(tuple(geometry._bezier_eval(ctrl, k / float(n))))

        def _qCurveToOne(self, p1, p2):
            self._flatten([p1, p2])

        def _curveToOne(self, p1, p2, p3):
            self._flatten([p1, p2, p3])

        def _closePath(self):
            if self._points and len(self._points) > 2:
                self.contours.append(np.array(self._points, dtype=float))
            self._points = None

        _endPath = _closePath

    return FlatPen()


def _inside(point, poly):
    x, y = point
    xs, ys = poly[:, 0], poly[:, 1]
    xn, yn = np.roll(xs, -1), np.roll(ys, -1)
    crosses = ((ys > y) != (yn > y)) & (x < (xn - xs) * (y - ys) / np.where(yn != ys, yn - ys, 1e-300) + xs)
    return bool(np.count_nonzero(crosses) % 2)


def _faces(contours):
    """One face per outer contour, with the contours inside it as holes."""
    depth = [sum(1 for j, other in enumerate(contours) if j != i and _inside(c[0], other))
             for i, c in enumerate(contours)]
    faces = []
    for i, outer in enumerate(contours):
        if depth[i] % 2:
            continue
        holes = [c for j, c in enumerate(contours)
                 if depth[j] == depth[i] + 1 and _inside(c[0], outer)]
        wires = [makePolygon([(p[0], p[1], 0.0) for p in loop], True) for loop in [outer] + holes]
        faces.append(Face(wires))
    return faces


def shape_string(text, font_file, size, tracking=0.0):
    """A Compound of faces spelling `text` in the XY plane."""
    font = _font(font_file)
    upem = float(font["head"].unitsPerEm)
    cap_pixels = round(_cap_height(font) * _FT_PIXELS_PER_EM / upem) or 1.0
    scale = float(size) / cap_pixels * _FT_PIXELS_PER_EM / upem
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    kerning = _kerning(font)
    hmtx = font["hmtx"]

    contours, x, previous = [], 0.0, None
    for ch in text:
        if ch in "\r\n":
            continue
        name = cmap.get(ord(ch), ".notdef")
        if previous is not None:
            x += kerning.get((previous, name), 0)
        pen = _make_pen(glyphs, geometry.TOLERANCE / scale)
        glyphs[name].draw(pen)
        for c in pen.contours:
            contours.append((c + np.array([x, 0.0])) * scale)
        x += hmtx[name][0] + float(tracking) / scale
        previous = name
    if not contours:
        return Compound([])
    left = min(c[:, 0].min() for c in contours)
    contours = [c - np.array([left, 0.0]) for c in contours]
    return Compound(_faces(contours))
