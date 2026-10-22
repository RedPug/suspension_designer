
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
from suspension_designer.elements.geometry import LineReferenceElement, PlaneReferenceElement, PointReferenceElement
from suspension_designer.math import get_rotation_matrix_from_quaternion, quaternion_from_direction, mult_quaternions
from suspension_designer.elements.nodes import NodeGroup
from suspension_designer.user_interface.selection import SelectionManager
from suspension_designer.editor.scene import SceneState
from suspension_designer.user_interface.ui_config import ColorPalette, RenderingConfig
from suspension_designer.rendering.camera import Camera, CameraBasis


# Create one reusable sphere
SPHERE_QUADRIC = gluNewQuadric()
gluQuadricNormals(SPHERE_QUADRIC, GLU_SMOOTH)

# Create one reusable quadric for cylinders
CYLINDER_QUADRIC = gluNewQuadric()
gluQuadricNormals(CYLINDER_QUADRIC, GLU_SMOOTH)

def draw_cylinder(viewport, p1, p2, radius):

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
        CYLINDER_QUADRIC,
        radius,
        radius,
        length,
        12,
        1
    )

    glPopMatrix()

def draw_nodes(viewport):
    points = np.array([node.world_position for node in viewport.scene_state.nodes])
    if len(points) == 0:
        return

    cam_pts = viewport.camera.world_to_camera(points)

    edges = viewport.scene_state.edges
    selected = viewport.selection_manager.get_selected()
    selected_group_node_ids = None

    if type(selected) == NodeGroup:
        selected_group_node_ids = {node.id for node in selected.nodes}

    glLoadIdentity()

    for i, p in enumerate(cam_pts):

        glPushMatrix()

        glTranslatef(p[0], p[1], p[2])

        node = viewport.scene_state.nodes[i]
        is_selected = selected is node
        is_group_selected = False
        if selected_group_node_ids is not None:
            is_group_selected = node.id in selected_group_node_ids

        is_subselection = node in viewport.selection_manager.subselections

        if is_selected or is_group_selected:
            glColor3f(*ColorPalette.NODE_SELECTED)  # Blue for selected nodes
        elif is_subselection:
            glColor3f(*ColorPalette.NODE_SUBSELECTION)  # Cyan for subselections
        else:
            glColor3f(*ColorPalette.NODE_UNSELECTED)  # Orange for unselected nodes

        gluSphere(
            SPHERE_QUADRIC,
            0.025,   # radius
            40,     # longitude slices
            10      # latitude stacks
        )

        glPopMatrix()

    glColor3f(*ColorPalette.NODE_EDGE)
    for i, j in edges:
        draw_cylinder(viewport, cam_pts[i], cam_pts[j], radius=0.01)

def draw_plane(viewport, plane_element: PlaneReferenceElement):
    assert isinstance(plane_element, PlaneReferenceElement), "Expected a PlaneReferenceElement object"
    plane = plane_element._geometry
    if plane.point is None or plane.normal is None:
        return
    
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

    # ---- project to camera space ----
    c = viewport.camera.world_to_camera(corners)

    # =========================================================
    # 1. FILL (translucent plane)
    # =========================================================
    if plane_element == viewport.selection_manager.get_selected():
        glColor4f(*ColorPalette.REFERENCE_GEOMETRY_SELECTED)
    else:
        glColor4f(*ColorPalette.REFERENCE_GEOMETRY)
    

    glBegin(GL_TRIANGLES)
    glVertex3f(*c[0]); glVertex3f(*c[1]); glVertex3f(*c[2])
    if len(c) == 4:
        glVertex3f(*c[0]); glVertex3f(*c[2]); glVertex3f(*c[3])
    glEnd()

    glBegin(GL_TRIANGLES)
    glVertex3f(*c[2]); glVertex3f(*c[1]); glVertex3f(*c[0])
    if len(c) == 4:
        glVertex3f(*c[3]); glVertex3f(*c[2]); glVertex3f(*c[0])
    glEnd()

    # =========================================================
    # 2. OUTLINE (thin border)
    # =========================================================
    if plane_element == viewport.selection_manager.get_selected():
        glColor4f(*ColorPalette.REFERENCE_GEOMETRY_OUTLINE_SELECTED)
    else:
        glColor4f(*ColorPalette.REFERENCE_GEOMETRY_OUTLINE)

    glLineWidth(RenderingConfig.REFERENCE_PLANE_OUTLINE_WIDTH)
    glBegin(GL_LINE_LOOP)
    for p in c:
        glVertex3f(*p)
    glEnd()

def draw_point(viewport, point: PointReferenceElement):
    assert isinstance(point, PointReferenceElement), "Expected a PointReferenceElement object"

    # ---- project to camera space ----
    c = viewport.camera.world_to_camera(np.array([point._geometry.pos]))

    glPushMatrix()
    glTranslatef(c[0][0], c[0][1], c[0][2])

    if point == viewport.selection_manager.get_selected():
        glColor4f(*ColorPalette.REFERENCE_GEOMETRY_SELECTED)  # Blue for selected points
    else:
        glColor4f(*ColorPalette.REFERENCE_GEOMETRY)  # Orange for unselected points

    n = 40
    radius = RenderingConfig.REFERENCE_POINT_RADIUS

    gluSphere(
        SPHERE_QUADRIC,
        radius,   # radius
        n,     # longitude slices
        10      # latitude stacks
    )

    outline_vertices = []
    for i in range(n):
        angle = 2 * np.pi * i / n
        x = radius * np.cos(angle)
        y = radius * np.sin(angle)
        outline_vertices.append([x, y, 0])

    if point == viewport.selection_manager.get_selected():
        glColor4f(*ColorPalette.REFERENCE_GEOMETRY_OUTLINE_SELECTED)  # Blue for selected points
    else:
        glColor4f(*ColorPalette.REFERENCE_GEOMETRY_OUTLINE)  # Orange for unselected points

    glLineWidth(RenderingConfig.REFERENCE_POINT_OUTLINE_WIDTH)
    glBegin(GL_LINE_LOOP)
    for vertex in outline_vertices:
        glVertex3f(*vertex)
    glEnd()

    glPopMatrix()

def draw_line(viewport, line: LineReferenceElement):
    assert isinstance(line, LineReferenceElement), "Expected a LineReferenceElement object"

    # ---- project to camera space ----
    c = viewport.camera.world_to_camera(np.array([line._geometry.point, line._geometry.direction * 1 + line._geometry.point]))

    if line == viewport.selection_manager.get_selected():
        glColor4f(*ColorPalette.REFERENCE_LINE_SELECTED)
    else:
        glColor4f(*ColorPalette.REFERENCE_LINE)


    glLineWidth(5.0)

    start_point = line._geometry.point
    direction = line._geometry.direction
    
    dash_length = RenderingConfig.REFERENCE_LINE_DASH_LENGTH  # Length of a visible dash in world units
    gap_length = RenderingConfig.REFERENCE_LINE_GAP_LENGTH   # Length of an empty gap in world units
    step = dash_length + gap_length
    total_length = 1.0  # Your current hardcoded line length

    # Generate the start distances for each dash segment
    dash_starts = np.arange(0, total_length, step)

    glBegin(GL_LINES)
    for t_start in dash_starts:
        # Clamp the dash end so it doesn't overshoot the total 1.0 unit length
        t_end = min(t_start + dash_length, total_length)
        
        # Calculate 3D world space points for this specific dash chunk
        p3d_start = start_point + direction * t_start
        p3d_end = start_point + direction * t_end

        # Project this specific dash to camera space
        c_dash = viewport.camera.world_to_camera(np.array([p3d_start, p3d_end]))

        # Draw the single dash chunk
        glVertex3f(*c_dash[0])
        glVertex3f(*c_dash[1])
    glEnd()

    # viewport.draw_cylinder(c[0], c[1], radius=0.002)

def draw_reference_geometry(viewport, grid_n=10):
    # glDisable(GL_LIGHTING)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDepthMask(GL_FALSE)

    for plane in [geo for geo in viewport.scene_state._reference_geometry if isinstance(geo, PlaneReferenceElement)]:
        draw_plane(viewport, plane)

    # glEnable(GL_LIGHTING)
    
    for point in [geo for geo in viewport.scene_state._reference_geometry if isinstance(geo, PointReferenceElement)]:
        draw_point(viewport, point)

    for line in [geo for geo in viewport.scene_state._reference_geometry if isinstance(geo, LineReferenceElement)]:
        draw_line(viewport, line)

    glDepthMask(GL_TRUE)



    # glDisable(GL_BLEND)

def draw_raycast(viewport):
    # Endpoints in world space
    p0 = viewport.raycast_origin
    p1 = viewport.raycast_origin + 2.0 * viewport.raycast_direction

    # Transform to camera space
    line = viewport.camera.world_to_camera(np.array([p0, p1]))

    glDisable(GL_LIGHTING)

    glColor3f(1.0, 0.0, 0.0)  # Red

    glLineWidth(2.0)

    glBegin(GL_LINES)
    glVertex3f(*line[0])
    glVertex3f(*line[1])
    glEnd()

    glEnable(GL_LIGHTING)