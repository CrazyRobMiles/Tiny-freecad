"""A 3D view of a document, like the one FreeCAD shows after a script runs.

Every visible object is drawn where the script put it, in its
ViewObject.ShapeColor (and Transparency), with dark lines along the
creases between faces as FreeCAD outlines its faces. Draft text labels
are shown as text. The camera starts the way the script left FreeCAD's
(isometric, unless it asked for viewTop() and so on) and orthographic,
fitted to the whole document.

Keys (FreeCAD's own view shortcuts):
    0  isometric      1  front     2  top      3  right
    4  rear           5  bottom    6  left     v  fit all
    r  fit all        q  close the window
Mouse: left-drag rotates, shift + left-drag or middle-drag pans, the
wheel or right-drag zooms.

Needs pyvista (pip install pyvista).
"""
import os
import time
import traceback

import numpy as np

# Where the camera looks from, and which way is up, for each of FreeCAD's
# standard views.
VIEWS = {
    "viewIsometric": ((1, -1, 1), (0, 0, 1)),
    "viewFront": ((0, -1, 0), (0, 0, 1)),
    "viewRear": ((0, 1, 0), (0, 0, 1)),
    "viewTop": ((0, 0, 1), (0, 1, 0)),
    "viewBottom": ((0, 0, -1), (0, 1, 0)),
    "viewRight": ((1, 0, 0), (0, 0, 1)),
    "viewLeft": ((-1, 0, 0), (0, 0, 1)),
}
VIEWS["viewAxonometric"] = VIEWS["viewAxometric"] = VIEWS["viewDimetric"] = VIEWS["viewTrimetric"] = \
    VIEWS["viewIsometric"]
KEYS = {"0": "viewIsometric", "1": "viewFront", "2": "viewTop", "3": "viewRight", "4": "viewRear",
        "5": "viewBottom", "6": "viewLeft"}

# A soft blue-grey gradient behind the model, much like FreeCAD's.
BACKGROUND_TOP, BACKGROUND_BOTTOM = "#e8ecf2", "#9aa8bf"
# Lines are drawn along edges where the faces either side meet at more
# than this many degrees, which picks out a mesh's real corners and not
# the facets of its curved surfaces.
CREASE_ANGLE = 30.0


def _pyvista():
    try:
        import pyvista
    except ImportError:
        raise ImportError("showing the 3D view needs pyvista: pip install pyvista")
    return pyvista


# -- turning shapes into meshes pyvista can draw --


def _solid_mesh(pv, shape):
    verts, tris = shape._arrays()
    if len(tris) == 0:
        return None
    return pv.PolyData.from_regular_faces(verts, tris)


def _face_mesh(pv, face):
    import manifold3d as m3
    origin, u, v, _ = face._frame()
    section = face._cross_section((origin, u, v, _))
    polys = [np.asarray(p, dtype=float) for p in section.to_polygons()]
    if not polys:
        return None
    flat = np.concatenate(polys)
    tris = np.asarray(m3.triangulate(polys)).reshape(-1, 3)
    verts = origin + flat[:, :1] * u + flat[:, 1:2] * v
    return pv.PolyData.from_regular_faces(verts, tris)


def _line_mesh(pv, edge_or_wire):
    pts = edge_or_wire._sample()[0]
    return pv.lines_from_points(pts) if len(pts) > 1 else None


def shape_meshes(pv, shape):
    """(surfaces, lines) pyvista meshes for a shape."""
    from tinyfreecad.topo import Compound, Edge, Face, Solid, Wire
    if isinstance(shape, Solid):
        if shape.isNull():
            return [], []
        mesh = _solid_mesh(pv, shape)
        if mesh is None:
            return [], []
        return [mesh], [mesh.extract_feature_edges(feature_angle=CREASE_ANGLE, boundary_edges=True,
                                                   non_manifold_edges=False, manifold_edges=False)]
    if isinstance(shape, Face):
        mesh = _face_mesh(pv, shape)
        return ([mesh] if mesh is not None else []), [m for m in (_line_mesh(pv, w) for w in shape._wires) if m]
    if isinstance(shape, (Edge, Wire)):
        line = _line_mesh(pv, shape)
        return [], [line] if line is not None else []
    if isinstance(shape, Compound):
        surfaces, lines = [], []
        for child in shape._children:
            s, l = shape_meshes(pv, child)
            surfaces += s
            lines += l
        return surfaces, lines
    return [], []


def _rgb(color):
    return tuple(float(c) for c in color[:3])


# -- the viewer --


class Viewer(object):
    """A window showing one document. reload() redraws it (keeping the
    camera) after the document has been made again."""

    def __init__(self, off_screen=False, size=(1024, 768)):
        self.pv = _pyvista()
        self.plotter = self.pv.Plotter(off_screen=off_screen, window_size=list(size))
        self.plotter.set_background(BACKGROUND_BOTTOM, top=BACKGROUND_TOP)
        self.plotter.add_axes()  # the small X/Y/Z marker in the corner, as FreeCAD has
        self.names = []
        for key, view in KEYS.items():
            self.plotter.add_key_event(key, lambda view=view: self.set_view(view))
        self.plotter.add_key_event("v", self.fit)

    def show_document(self, doc, reset_camera=True):
        """Draw `doc`'s visible objects."""
        from tinyfreecad import gui
        for name in self.names:
            self.plotter.remove_actor(name, render=False)
        self.names = []
        if doc is None:
            self._status("No document")
            return
        for obj in doc.Objects:
            try:
                self._add_object(obj)
            except NotImplementedError as e:
                print("Can't show %s: %s" % (obj.Label, e))
        self._status("")
        self.plotter.title = "%s - tiny-freecad" % doc.Label
        view = gui.getDocument(doc).ActiveView
        if reset_camera:
            if view.camera_type == "Perspective":
                self.plotter.disable_parallel_projection()
            else:
                self.plotter.enable_parallel_projection()
            self.set_view(view.orientation)

    def _add_object(self, obj):
        vo = obj.ViewObject
        if not getattr(vo, "Visibility", True):
            return
        if hasattr(obj, "Text") and obj.TypeId == "App::FeaturePython":
            self._add_text(obj)
            return
        shape = getattr(obj, "Shape", None)
        if shape is None:
            return
        props = vo._props
        color = _rgb(props.get("ShapeColor", (0.8, 0.8, 0.8)))
        opacity = 1.0 - float(props.get("Transparency", 0)) / 100.0
        line_color = _rgb(props.get("LineColor", (0.1, 0.1, 0.1)))
        line_width = float(props.get("LineWidth", 2.0)) * 0.75
        surfaces, lines = shape_meshes(self.pv, shape)
        for i, mesh in enumerate(surfaces):
            name = "%s#surface%d" % (obj.Name, i)
            self.plotter.add_mesh(mesh, color=color, opacity=opacity, smooth_shading=False, name=name,
                                  render=False, reset_camera=False)
            self.names.append(name)
        for i, mesh in enumerate(lines):
            if mesh.n_points == 0:
                continue
            name = "%s#lines%d" % (obj.Name, i)
            self.plotter.add_mesh(mesh, color=line_color, line_width=line_width, name=name, render=False,
                                  reset_camera=False)
            self.names.append(name)

    def _add_text(self, obj):
        placement = obj._props.get("Placement")
        base = placement.Base if placement is not None else (0, 0, 0)
        text = "\n".join(obj.Text)
        color = _rgb(obj.ViewObject._props.get("TextColor", (0.0, 0.0, 0.0)))
        name = "%s#text" % obj.Name
        self.plotter.add_point_labels(np.array([[base[0], base[1], base[2]]]), [text], point_size=0,
                                      font_size=14, text_color=color, shape=None, show_points=False,
                                      always_visible=True, name=name, render=False, reset_camera=False)
        self.names.append(name)

    def _status(self, message):
        self.plotter.add_text(message, position="lower_left", font_size=9, color="black", name="status",
                              render=False)

    def set_view(self, view):
        direction, up = VIEWS.get(view, VIEWS["viewIsometric"])
        self.plotter.view_vector(direction, viewup=up)
        self.fit()

    def fit(self):
        if self.names:
            self.plotter.reset_camera(render=False)
        self.plotter.render()


def show(doc=None, watch=None, poll_ms=500):
    """Open a window showing `doc` (default: the active document) and wait
    until it is closed.

    With watch=(path, rerun), the script at `path` is run again by
    calling rerun() whenever the file changes, and the window redrawn
    with what it made, keeping the camera where you left it."""
    from tinyfreecad import app
    viewer = Viewer()
    viewer.show_document(doc or app.activeDocument())
    if watch is not None:
        path, rerun = watch
        state = {"mtime": os.path.getmtime(path)}

        def check(step=None):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                return
            if mtime == state["mtime"]:
                return
            state["mtime"] = mtime
            print("Re-running %s (%s)" % (os.path.basename(path), time.strftime("%H:%M:%S")))
            try:
                rerun()
            except Exception:
                traceback.print_exc()
            if app.activeDocument() is None:
                print("(nothing made; still showing the last run)")
                return
            viewer.show_document(app.activeDocument(), reset_camera=False)
            viewer.plotter.render()

        # On Windows a timer only works once the window exists, so open
        # the window first and start the timer and the event loop after.
        viewer.plotter.show(interactive_update=True)
        viewer.plotter.add_timer_event(max_steps=2 ** 31 - 1, duration=poll_ms, callback=check)
        viewer.plotter.iren.start()
    else:
        viewer.plotter.show()


def screenshot(filename, width=1024, height=768, doc=None):
    """Save a picture of `doc` (default: the active document) as the view
    would show it, without opening a window."""
    from tinyfreecad import app
    viewer = Viewer(off_screen=True, size=(int(width), int(height)))
    viewer.show_document(doc or app.activeDocument())
    viewer.plotter.screenshot(filename)
    viewer.plotter.close()
