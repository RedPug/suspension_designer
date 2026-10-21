
import numpy as np
import time

from PySide6.QtCore import QPointF, Qt

from PySide6.QtWidgets import QWidget

from PySide6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPen, QPixmap, QPolygonF, QRadialGradient

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *

from PySide6.QtGui import QSurfaceFormat

from suspension_designer.geometry_core import PlaneGeometry, PointGeometry
from suspension_designer.rendering.render_providers import draw_nodes, draw_reference_geometry

fmt = QSurfaceFormat()
fmt.setDepthBufferSize(24)
fmt.setStencilBufferSize(8)
fmt.setSamples(4)          # 4× MSAA (try 8 if desired)

QSurfaceFormat.setDefaultFormat(fmt)


from suspension_designer.elements.geometry import LineReferenceElement, PlaneReferenceElement, PointReferenceElement
from suspension_designer.math import get_rotation_matrix_from_quaternion, quaternion_from_direction, mult_quaternions
from suspension_designer.elements.nodes import NodeGroup
from suspension_designer.user_interface.selection import SelectionManager
from suspension_designer.editor.scene import SceneState
from suspension_designer.user_interface.colorpalette import ColorPalette, RenderingConfig
from suspension_designer.rendering.camera import Camera, CameraBasis


class AxesGizmo(QWidget):
    def __init__(self, parent, camera: Camera):
        super().__init__(parent)
        self.camera = camera
        self.setFixedSize(150, 150)  # Fixed size for the gizmo

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        size = 40

        origin = np.array([self.width()/2, self.height()/2])

        axes = {
            "X": (np.array([1, 0, 0]), Qt.red),
            "Y": (np.array([0, 1, 0]), Qt.green),
            "Z": (np.array([0, 0, 1]), Qt.blue),
        }

        directions = [
            np.array([1.0, 0, 0]),  # Right
            np.array([-1.0, 0, 0]),  # Left
            np.array([0, 1.0, 0]),  # Up
            np.array([0, -1.0, 0]),  # Down
            np.array([0, 0, 1.0]),  # Front
            np.array([0, 0, -1.0]),  # Back
        ]

        painter.setRenderHint(QPainter.Antialiasing)

        axis_items = []

        for label, (axis, color) in axes.items():
            rotation_matrix = get_rotation_matrix_from_quaternion(self.camera.rotation)
            cam_pt = axis @ rotation_matrix  # rotate into camera space

            # f = 1.0 / np.tan(np.radians(self.camera.fov) * 0.5)

            if self.camera.perspective:
                # apply perspective divide
                perspective_dist = 4
                z = -cam_pt[2] + perspective_dist
                z = max(z, 1e-6)  # prevent division by zero and negative depth
                scale = (perspective_dist-0.707)/z
            else:
                scale = 1

            cam_pt[:2] *= scale

            # ignore depth scaling → normalize direction
            dir2d = cam_pt[:2]

            axis_items.append((cam_pt[2], label, dir2d, color))

        # depth sort (back → front)
        axis_items.sort()

        for _, label, dir2d, color in axis_items:
            end = origin + np.array([dir2d[0] * size, -dir2d[1] * size])

            pen = QPen(color)
            pen.setWidth(2)
            painter.setPen(pen)

            painter.drawLine(int(origin[0]), int(origin[1]),
                            int(end[0]), int(end[1]))

            # arrow
            direction = end - origin
            if np.linalg.norm(direction) > 0:
                d = direction / np.linalg.norm(direction)
                perp = np.array([-d[1], d[0]])

                arrow_size = 6
                p1 = end - d * arrow_size + perp * arrow_size * 0.5
                p2 = end - d * arrow_size - perp * arrow_size * 0.5

                painter.drawLine(int(end[0]), int(end[1]), int(p1[0]), int(p1[1]))
                painter.drawLine(int(end[0]), int(end[1]), int(p2[0]), int(p2[1]))

            painter.drawText(int(end[0] + 4), int(end[1] + 4), label)

class Viewport3D(QOpenGLWidget):

    def __init__(self, parent=None, *, scene_state: SceneState, selection_manager: SelectionManager):
        super().__init__(parent)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # -------- Scene --------
        self.scene_state = scene_state
        self.selection_manager = selection_manager

        self.node_radius = 0.02 #m
        self.edge_width = 5 #px

        self.camera = Camera(
            viewport=self,
            focus = np.array([0.0, 0.0, 0.0]),
            distance = 5.0,
            rotation = quaternion_from_direction(CameraBasis.ISOMETRIC, up=CameraBasis.UP),
            perspective = False,
            fov = 60.0,
            near_clip = 0.01,
            far_clip = 100.0
        )

        self.raycast_origin = np.array([0.0, 0.0, 0.0])
        self.raycast_direction = np.array([0.0, 0.0, -1.0])

        self.axes_gizmo = AxesGizmo(self, camera=self.camera)

        # -------- Interaction --------
        self._last_mouse = None
        self._mode = None  # "rotate", "pan", "zoom"
        self._did_mouse_move = False
        # self._in_view_cube = False

        self.setMouseTracking(True)

        self.selection_manager.selection_changed.connect(lambda: self.update())
        self.scene_state.did_change.connect(lambda: self.update())

    def set_scene(self, points, lines):
        self.scene_state = SceneState(points=points, edges=lines)

        self.update()

    def initializeGL(self):

        glClearColor(*ColorPalette.BACKGROUND)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_MULTISAMPLE)
        glEnable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Enable lighting
        glEnable(GL_LIGHTING)
        self.update_lighting()

        # Material colour
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_COLOR_MATERIAL)

    def update_projection(self):
        # print("updating projection")
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()

        # print("dist:", self.camera.distance)

        if "aspect" not in self.__dict__:
            print("aspect not set, using default 1.0")
            aspect = 1.0
        else:
            aspect = self.aspect

        if self.camera.perspective:
            # print("perspective")
            gluPerspective(
                self.camera.fov, #fov
                aspect, #aspect ratio
                self.camera.near_clip, #near clip
                self.camera.far_clip, #far clip
            )
        else:
            # print("orthographic")
            f = 1.0 / np.tan(np.radians(self.camera.fov) * 0.5)
            d = self.camera.distance
            s = d/f
            glOrtho(
                -s * aspect, #left
                s * aspect, #right
                -s, #bottom
                s, #top
                -self.camera.far_clip, #near clip
                self.camera.far_clip, #far clip
            )

        glMatrixMode(GL_MODELVIEW)

    def update_lighting(self):
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        #ambient light
        glEnable(GL_LIGHT0)
        ambient_brightness = 0.2
        glLightfv(GL_LIGHT0, GL_AMBIENT, (ambient_brightness, ambient_brightness, ambient_brightness, 1.0))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.0, 0.0, 0.0, 1.0))

        # headlight
        # glEnable(GL_LIGHT1)
        # head_brightness = 0.5
        # glLightfv(GL_LIGHT1, GL_POSITION, (0.0, 0.0, 1.0, 0.0))
        # glLightfv(GL_LIGHT1, GL_DIFFUSE, (head_brightness, head_brightness, head_brightness, 1.0))

        # trimetric light
        glEnable(GL_LIGHT2)
        tri_brightness = 0.5
        dir = self.camera.apply_rotation([CameraBasis.TRIMETRIC])[0]
        glLightfv(GL_LIGHT2, GL_POSITION, (*dir, 0.0))
        glLightfv(GL_LIGHT2, GL_DIFFUSE, (tri_brightness, tri_brightness, tri_brightness, 1.0))

        # back light
        glEnable(GL_LIGHT3)
        tri2_brightness = 0.3
        dir = self.camera.apply_rotation([CameraBasis.BACK])[0]
        glLightfv(GL_LIGHT3, GL_POSITION, (*(dir), 0.0))
        glLightfv(GL_LIGHT3, GL_DIFFUSE, (tri2_brightness, tri2_brightness, tri2_brightness, 1.0))

        # top(ish) light
        glEnable(GL_LIGHT4)
        tri3_brightness = 0.3
        dir = self.camera.apply_rotation(np.array([-0.35*CameraBasis.RIGHT + 0.93*CameraBasis.UP + 0.65*CameraBasis.FRONT]))[0]
        glLightfv(GL_LIGHT4, GL_POSITION, (*(dir), 0.0))
        glLightfv(GL_LIGHT4, GL_DIFFUSE, (tri3_brightness, tri3_brightness, tri3_brightness, 1.0))

    def resizeGL(self, w, h):
        # print("resizing")

        glViewport(0, 0, w, h)

        self.aspect = w / max(1, h)

        self.update_projection()

        self.axes_gizmo.move(0, self.height() - self.axes_gizmo.height())


    def paintGL(self):
        # print("painting")
        t0 = time.perf_counter()

        self.update_projection()
        self.update_lighting()
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        draw_nodes(self)

        draw_reference_geometry(self)

        # self.draw_raycast()

        # if self._in_view_cube:
        #     self.draw_view_cube()

        self.axes_gizmo.update()

        t1 = time.perf_counter()
        # print(f"paintGL took {(t1-t0)*1000:.4f} ms")

    def raycast(self, origin: np.ndarray, dir: np.ndarray):
        points = np.array([node.world_position for node in self.scene_state.nodes])
        radii = np.ones_like(points[:, 0], dtype=float) * 0.025

        oc = points - origin

        # Distance along the ray
        t = oc @ dir

        # Ignore spheres behind the camera
        if self.camera.perspective:
            front = t > 0
        else:
            front = np.ones_like(t, dtype=bool)

        if not np.any(front):
            return None, None

        oc = oc[front]
        t = t[front]

        # Closest point on the ray to each sphere center
        closest = origin + t[:, None] * dir

        # Squared perpendicular distance
        d2 = np.sum((points[front] - closest) ** 2, axis=1)

        hits = d2 <= radii**2
        if not np.any(hits):
            return None, None

        indices = np.where(front)[0][hits]
        distances = t[hits]

        i = np.argmin(distances)
        return indices[i], distances[i]


    def check_node_selection(self, x, y):
        # print(f"Checking node selection at ({x}, {y})")

        origin, dir = self.camera.get_ray_direction(x, y)
        index, distance = self.raycast(origin, dir)

        self.update()

        # print(f"Raycast result: index={index}, distance={distance}")

        if index is not None:
            # print(f"Selected node: {index}")
            self.selection_manager.set_selected(self.scene_state.nodes[index])
        else:
            # print("No node selected")
            self.selection_manager.set_selected(None)

    # ============================
    # INPUT HANDLING
    # ============================

    def mousePressEvent(self, event):

        self._last_mouse = np.array([event.x(), event.y()])
        self._did_mouse_move = False
        
        # print(f"Press Modifiers: {event.modifiers()}")

        btn = event.button()

        ctrl = event.modifiers() & Qt.ControlModifier
        shift = event.modifiers() & Qt.ShiftModifier

        if (btn == Qt.MiddleButton) or (btn == Qt.LeftButton and ctrl):
            self._mode = "pan"
        elif btn == Qt.LeftButton:
            self._mode = "rotate"
        
        event.accept()

    def mouseMoveEvent(self, event):
        if self._last_mouse is None:
            return

        pos = np.array([event.x(), event.y()])
        delta = pos - self._last_mouse
        self._last_mouse = pos
        self._did_mouse_move = True

        if self._mode == "rotate":
            self._rotate(-delta)
        elif self._mode == "pan":
            self._pan(delta)

        self.update()

        event.accept()

    def mouseReleaseEvent(self, event):
        if not self._did_mouse_move:
            self.check_node_selection(event.x(), event.y())

        self._mode = None
        self._last_mouse = None
        self._did_mouse_move = False

        event.accept()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self._zoom(delta * 0.01)

        self.update()

        event.accept()

    # ============================
    # CAMERA CONTROLS
    # ============================

    def _rotate(self, delta):
        dx, dy = delta * 0.005

        right, up, _ = self.camera.get_camera_basis()

        # normalize (important for stability)
        right = right / np.linalg.norm(right)
        up = up / np.linalg.norm(up)

        # build quaternions from axis-angle
        q_yaw = np.array([
            np.cos(dx / 2),
            *(up * np.sin(dx / 2))
        ])

        q_pitch = np.array([
            np.cos(dy / 2),
            *(right * np.sin(dy / 2))
        ])

        # apply rotations in local space
        self.camera.rotation = mult_quaternions(q_yaw, self.camera.rotation)
        self.camera.rotation = mult_quaternions(q_pitch, self.camera.rotation)

        # normalize quaternion (prevents drift)
        self.camera.rotation /= np.linalg.norm(self.camera.rotation)

    def _pan(self, delta):
        right, up, _ = self.camera.get_camera_basis()

        scale = self.camera.distance * 0.002

        move = (-delta[0] * right + delta[1] * up) * scale
        self.camera.focus += move


    def _zoom(self, amount):
        self.camera.distance *= (1.0 + amount * 0.1)
        self.camera.distance = max(0.1, min(100.0, self.camera.distance))