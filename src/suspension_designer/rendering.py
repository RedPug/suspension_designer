
import numpy as np
import time

from PySide6.QtCore import QPointF, Qt

from PySide6.QtWidgets import QWidget

from PySide6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPen, QPixmap, QPolygonF, QRadialGradient

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *

from PySide6.QtGui import QSurfaceFormat

fmt = QSurfaceFormat()
fmt.setDepthBufferSize(24)
fmt.setStencilBufferSize(8)
fmt.setSamples(4)          # 4× MSAA (try 8 if desired)

QSurfaceFormat.setDefaultFormat(fmt)



from suspension_designer.math import get_rotation_matrix_from_quaternion, quaternion_from_direction, mult_quaternions
from suspension_designer.structures import NodeGroup, ReferencePlane, SelectionManager
from suspension_designer.scene import SceneState

class Camera:
    def __init__(self, viewport: QWidget, *,
                 focus: np.ndarray,
                 distance:float,
                 rotation: np.ndarray,
                 perspective: bool = False,
                 fov: float = 60.0,
                 far_clip: float = 100.0,
                 near_clip: float = 0.01):
        
        self.focus = focus
        self.distance = distance
        self.rotation = rotation
        self.perspective = perspective
        self.fov = fov
        self.near_clip = near_clip
        self.far_clip = far_clip
        self.viewport = viewport

    def get_camera_basis(self):
        R = get_rotation_matrix_from_quaternion(self.rotation)

        # camera looks down -Z in local space
        forward = R @ np.array([0, 0, -1])
        right = R @ np.array([1, 0, 0])
        up = R @ np.array([0, 1, 0])

        return right, up, forward

    def world_to_camera(self, pts):
        right, up, forward = self.get_camera_basis()

        cam_pos = self.focus - forward * self.distance

        rel = pts - cam_pos

        x = rel @ right
        y = rel @ up
        z = rel @ (-forward)

        return np.stack([x, y, z], axis=1)
    
    def apply_rotation(self, pts):
        right, up, forward = self.get_camera_basis()

        # cam_pos = self.focus - forward * self.distance

        # rel = pts - cam_pos

        x = pts @ right
        y = pts @ up
        z = pts @ (-forward)

        return np.stack([x, y, z], axis=1)

    def project(self, pts):
        scales = self.get_pixels_per_unit(np.abs(pts[:, 2]))
        
        screen_x = pts[:, 0] * scales + self.viewport.width() * 0.5
        screen_y = -pts[:, 1] * scales + self.viewport.height() * 0.5
        screen_z = pts[:, 2]

        return np.stack([screen_x, screen_y, screen_z], axis=1)

    def get_pixels_per_unit(self, depths: np.ndarray) -> np.ndarray:
        w, h = self.viewport.width(), self.viewport.height()

        depths = np.abs(depths)

        # pts = pts[pts[:, 2] > 1e-6]  # simple near plane clipping
        f = 1.0 / np.tan(np.radians(self.fov) * 0.5)

        if self.perspective:
            z = depths
            z[z < self.near_clip] = self.near_clip  # prevent division by zero and negative depth
            scale = f/z
        else:
            # scaled to keep constant projection at the focus point.
            scale = np.ones_like(depths) * (f / self.distance)
            
        scale *= min(w, h) * 0.5

        return scale

    def world_to_screen(self, world_points):
        return self.project(self.world_to_camera(world_points))
    
    def get_ray_direction(self, x: float, y: float)->tuple[np.ndarray, np.ndarray]:
        """Get the direction of the ray from the camera through the screen point.

        Args:
            x (float): The x-coordinate of the screen point.
            y (float): The y-coordinate of the screen point.

        Returns:
            tuple[np.ndarray, np.ndarray]: Origin, Direction
        """
        # Convert screen coordinates to normalized device coordinates
        ndc_x = (x / self.viewport.width()) * 2 - 1
        ndc_y = 1 - (y / self.viewport.height()) * 2

        right, up, forward = self.get_camera_basis()

        cam_pos = self.focus - forward * self.distance

        f = 1.0 / np.tan(np.radians(self.fov) * 0.5)

        # height and width at the focus point, constant for perspective and orthographic
        view_height = 2 * self.distance / f
        view_width = view_height * self.viewport.width() / self.viewport.height()

        if self.perspective:
            origin = cam_pos
            dir = forward + view_width*0.5/self.distance*right*ndc_x + view_height/self.distance*0.5*up*ndc_y
        else:
            origin = cam_pos + view_width*0.5*right*ndc_x + view_height*0.5*up*ndc_y
            dir = forward # Forward direction
        # Create a ray from the camera through the screen point
        # This is a simplified approach; a more accurate implementation would consider the camera's position and orientation
        return origin, dir / np.linalg.norm(dir)  # Normalize the direction

    def set_view_direction(self, direction: np.ndarray, up: np.ndarray = None):
        if up is None:
            if direction[1] > 0.9:
                up = np.array([0, 0, -1])
            elif direction[1] < -0.9:
                up = np.array([0, 0, 1])
            else:
                up = np.array([0, 1, 0])

        self.rotation = quaternion_from_direction(direction, up=up)

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
            rotation = quaternion_from_direction(np.array([1.0,1.0,1.0])),
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
        self.scene_state.scene_changed.connect(lambda: self.update())


    # ============================
    # PUBLIC API
    # ============================

    def set_scene(self, points, lines):
        self.scene_state = SceneState(points=points, edges=lines)

        self.update()

    # ============================
    # RENDER
    # ============================

    def initializeGL(self):
        print("initializing")

        glClearColor(0.8, 0.8, 0.8, 1.0)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_MULTISAMPLE)
        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Enable lighting
        glEnable(GL_LIGHTING)
        self.update_lighting()

        # Material colour
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_COLOR_MATERIAL)

        # Create one reusable sphere
        self.sphere = gluNewQuadric()
        gluQuadricNormals(self.sphere, GLU_SMOOTH)

        self.quadric = gluNewQuadric()
        gluQuadricNormals(self.quadric, GLU_SMOOTH)

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
        dir = self.camera.apply_rotation(np.array([[0.35, 0.93, 0.65]]))[0]
        glLightfv(GL_LIGHT2, GL_POSITION, (*dir, 0.0))
        glLightfv(GL_LIGHT2, GL_DIFFUSE, (tri_brightness, tri_brightness, tri_brightness, 1.0))

        # back light
        glEnable(GL_LIGHT3)
        tri2_brightness = 0.3
        dir = self.camera.apply_rotation(np.array([[0.0, 1.0, -1.0]]))[0]
        glLightfv(GL_LIGHT3, GL_POSITION, (*(dir), 0.0))
        glLightfv(GL_LIGHT3, GL_DIFFUSE, (tri2_brightness, tri2_brightness, tri2_brightness, 1.0))

        # back light
        glEnable(GL_LIGHT4)
        tri3_brightness = 0.3
        dir = self.camera.apply_rotation(np.array([[-0.35, 0.93, 0.65]]))[0]
        glLightfv(GL_LIGHT4, GL_POSITION, (*(dir), 0.0))
        glLightfv(GL_LIGHT4, GL_DIFFUSE, (tri3_brightness, tri3_brightness, tri3_brightness, 1.0))

    def resizeGL(self, w, h):
        # print("resizing")

        glViewport(0, 0, w, h)

        self.aspect = w / max(1, h)

        self.update_projection()

        self.axes_gizmo.move(0, self.height() - self.axes_gizmo.height())

    def cube_corners(self, center, size):
        x, y, z = center
        s = size / 2.0

        return np.array([
            [x - s, y - s, z - s],
            [x + s, y - s, z - s],
            [x + s, y + s, z - s],
            [x - s, y + s, z - s],

            [x - s, y - s, z + s],
            [x + s, y - s, z + s],
            [x + s, y + s, z + s],
            [x - s, y + s, z + s],
        ], dtype=np.float32)

    def draw_cube(self, center, size):
        world_pts = self.cube_corners(center, size)

        cam_pts = self.camera.world_to_camera(world_pts)

        edges = [
            (0,1),(1,2),(2,3),(3,0),
            (4,5),(5,6),(6,7),(7,4),
            (0,4),(1,5),(2,6),(3,7)
        ]

        glColor3f(1, 1, 0)

        glBegin(GL_LINES)

        for a, b in edges:
            glVertex3f(*cam_pts[a])
            glVertex3f(*cam_pts[b])

        glEnd()

        faces = [
            # face, normal
            ((0,1,2,3), (0,0,-1)),  # back
            ((4,5,6,7), (0,0,1)),   # front
            ((0,1,5,4), (0,-1,0)),  # bottom
            ((2,3,7,6), (0,1,0)),   # top
            ((1,2,6,5), (1,0,0)),   # right
            ((0,3,7,4), (-1,0,0)),  # left
        ]

        glColor3f(1, 0, 0)

        glBegin(GL_QUADS)

        for verts, normal in faces:
            norm = self.camera.apply_rotation(np.array([normal]))[0]
            glNormal3f(*norm)   # IMPORTANT

            for idx in verts:
                glVertex3f(*cam_pts[idx])

        glEnd()

    def draw_cylinder(self, p1, p2, radius):

        p1 = np.asarray(p1, float)
        p2 = np.asarray(p2, float)

        d = p2 - p1
        length = np.linalg.norm(d)

        if length < 1e-6:
            return

        d /= length

        glPushMatrix()

        glTranslatef(*p1)

        z = np.array([0,0,1], float)

        axis = np.cross(z, d)
        axis_len = np.linalg.norm(axis)

        if axis_len > 1e-6:
            axis /= axis_len
            angle = np.degrees(np.arccos(np.clip(np.dot(z,d),-1,1)))
            glRotatef(angle, axis[0], axis[1], axis[2])

        elif d[2] < 0:
            glRotatef(180,1,0,0)

        gluCylinder(
            self.quadric,
            radius,
            radius,
            length,
            12,
            1
        )

        glPopMatrix()

    def draw_nodes(self):
        points = np.array([node.world_position for node in self.scene_state.nodes])
        if len(points) == 0:
            return

        cam_pts = self.camera.world_to_camera(points)

        edges = self.scene_state.edges
        selected = self.selection_manager.get_selected()
        selected_group_node_ids = None

        if type(selected) == NodeGroup:
            selected_group_node_ids = {node.id for node in selected.nodes}

        glLoadIdentity()

        for i, p in enumerate(cam_pts):

            glPushMatrix()

            glTranslatef(p[0], p[1], p[2])

            node = self.scene_state.nodes[i]
            is_selected = selected is node
            is_group_selected = False
            if selected_group_node_ids is not None:
                is_group_selected = node.id in selected_group_node_ids

            is_subselection = node in self.selection_manager.subselections

            if is_selected or is_group_selected:
                glColor3f(0.0, 0.6, 1.0)  # Blue for selected nodes
            elif is_subselection:
                glColor3f(1.0, 0.0, 0.0)  # Red for subselections
            else:
                glColor3f(1.0, 0.63, 0.0)  # Orange for unselected nodes

            gluSphere(
                self.sphere,
                0.025,   # radius
                20,     # longitude slices
                20      # latitude stacks
            )

            glPopMatrix()

        glColor3f(0.8, 0.4, 0.1)
        for i, j in edges:
            self.draw_cylinder(cam_pts[i], cam_pts[j], radius=0.01)

    def draw_reference_geometry(self, grid_n=10):
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)

        for plane in self.scene_state.reference_planes:
            
            if plane.mode == ReferencePlane.Mode.PERPENDICULAR:
                # ---- build basis in world space ----
                max_val = np.max(np.abs(plane.normal))

                if np.abs(plane.normal[0]) == max_val:
                    dir0 = np.cross(plane.normal, np.array([0.0, 1.0, 0.0]))
                elif np.abs(plane.normal[1]) == max_val:
                    dir0 = np.cross(plane.normal, np.array([1.0, 0.0, 0.0]))
                else:
                    dir0 = np.cross(plane.normal, np.array([1.0, 0.0, 0.0]))

                dir1 = np.cross(plane.normal, dir0)

                dir0 /= np.linalg.norm(dir0)
                dir1 /= np.linalg.norm(dir1)

                # ---- corners in world space ----
                corners = np.array([
                    plane.point + dir0 * 0.5 + dir1 * 0.5,
                    plane.point - dir0 * 0.5 + dir1 * 0.5,
                    plane.point - dir0 * 0.5 - dir1 * 0.5,
                    plane.point + dir0 * 0.5 - dir1 * 0.5
                ], dtype=np.float32)

            elif plane.mode == ReferencePlane.Mode.CONTAINING:
                corners = np.array([
                    plane.p0,
                    plane.p1,
                    plane.p2
                ])
            else:
                print("Unknown plane mode:", plane.mode)

            # ---- project to camera space ----
            c = self.camera.world_to_camera(corners)

            # =========================================================
            # 1. FILL (translucent plane)
            # =========================================================
            if plane == self.selection_manager.get_selected():
                glColor4f(0.0, 0.6, 1.0, 0.25)
            else:
                glColor4f(0.0, 0.0, 1.0, 0.25)
            

            glBegin(GL_TRIANGLES)
            glVertex3f(*c[0]); glVertex3f(*c[1]); glVertex3f(*c[2])
            if len(c) == 4:
                glVertex3f(*c[0]); glVertex3f(*c[2]); glVertex3f(*c[3])
            glEnd()

            # =========================================================
            # 2. OUTLINE (thin border)
            # =========================================================
            if plane == self.selection_manager.get_selected():
                glColor4f(0.0, 0.6, 1.0, 0.9)
            else:
                glColor4f(0.0, 0.0, 1.0, 0.9)
            glLineWidth(1.5)

            glBegin(GL_LINE_LOOP)
            for p in c:
                glVertex3f(*p)
            glEnd()

            # =========================================================
            # 3. GRID (NxN subdivision)
            # =========================================================
            # glColor4f(0.0, 0.0, 1.0, 0.35)

            # for i in range(1, grid_n):

            #     t = i / grid_n

            #     # interpolate edges
            #     a = c[0] * (1 - t) + c[1] * t
            #     b = c[3] * (1 - t) + c[2] * t

            #     c0 = c[0] * (1 - t) + c[3] * t
            #     c1 = c[1] * (1 - t) + c[2] * t

            #     # horizontal lines
            #     glBegin(GL_LINES)
            #     glVertex3f(*a); glVertex3f(*b)
            #     glEnd()

            #     # vertical lines
            #     glBegin(GL_LINES)
            #     glVertex3f(*c0); glVertex3f(*c1)
            #     glEnd()

        glDepthMask(GL_TRUE)
        glEnable(GL_LIGHTING)
        # glDisable(GL_BLEND)

    def draw_raycast(self):
        # Endpoints in world space
        p0 = self.raycast_origin
        p1 = self.raycast_origin + 2.0 * self.raycast_direction

        # Transform to camera space
        line = self.camera.world_to_camera(np.array([p0, p1]))

        glDisable(GL_LIGHTING)

        glColor3f(1.0, 0.0, 0.0)  # Red

        glLineWidth(2.0)

        glBegin(GL_LINES)
        glVertex3f(*line[0])
        glVertex3f(*line[1])
        glEnd()

        glEnable(GL_LIGHTING)

    def draw_view_cube(self):
        glDepthMask(GL_FALSE)
        glDisable(GL_LIGHTING)

        points = np.array([node.world_position for node in self.scene_state.nodes])

        min_x, min_y, min_z = points.min(axis=0)
        max_x, max_y, max_z = points.max(axis=0)

        center = np.array([(min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2])
        size = max(max_x - min_x, max_y - min_y, max_z - min_z) * 4.0
        face_size = size * 0.7

        # self.draw_cube(center, size)
        directions = [
            np.array([1.0, 0, 0]),  # Right
            np.array([-1.0, 0, 0]),  # Left
            np.array([0, 1.0, 0]),  # Up
            np.array([0, -1.0, 0]),  # Down
            np.array([0, 0, 1.0]),  # Forward
            np.array([0, 0, -1.0]),  # Backward
        ]

        for direction in directions:
            face_center = center + direction * size * 0.5

            # create two directions perpendicular to the face normal
            if direction[0] != 0:
                perp1 = np.array([0, 1, 0])
                perp2 = np.array([0, 0, 1])
            elif direction[1] != 0:
                perp1 = np.array([1, 0, 0])
                perp2 = np.array([0, 0, 1])
            else:
                perp1 = np.array([1, 0, 0])
                perp2 = np.array([0, 1, 0])

            vertices = np.array([face_center + (perp1 * face_size * 0.5 * x) + (perp2 * face_size * 0.5 * y) for x,y in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])

            c = self.camera.world_to_camera(vertices)

            # Draw the face
            glColor4f(0.2, 0.2, 1.0, 0.125)
            glBegin(GL_QUADS)
            glVertex3f(*c[0])
            glVertex3f(*c[1])
            glVertex3f(*c[2])
            glVertex3f(*c[3])
            glEnd()

            glColor4f(0.0, 0.0, 0.0, 1.0)
            glBegin(GL_LINE_LOOP)
            glVertex3f(*c[0])
            glVertex3f(*c[1])
            glVertex3f(*c[2])
            glVertex3f(*c[3])
            glEnd()


        glEnable(GL_LIGHTING)
        glDepthMask(GL_TRUE)


    def paintGL(self):
        # print("painting")
        t0 = time.perf_counter()

        self.update_projection()
        self.update_lighting()
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        self.draw_nodes()

        self.draw_reference_geometry()

        # self.draw_raycast()

        # if self._in_view_cube:
        #     self.draw_view_cube()

        self.axes_gizmo.update()

        t1 = time.perf_counter()
        # print(f"paintGL took {(t1-t0)*1000:.4f} ms")

    def raycast(self, origin: np.ndarray, dir: np.ndarray):
        radius = 0.025
        points = np.array([node.world_position for node in self.scene_state.nodes])

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

        hits = d2 <= radius**2
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

    # def keyPressEvent(self, event: QKeyEvent):
        # if event.key() == Qt.Key.Key_P:
        #     self.perspective = not self.perspective
        #     if self.perspective:
        #         print("Switched to perspective mode")
        #     else:
        #         print("Switched to orthographic mode")
        #     self.update()

        # if event.key() == Qt.Key.Key_Space:
        #     self._in_view_cube = not self._in_view_cube
        #     self.update()

        # event.accept()

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