import numpy as np

from PySide6.QtWidgets import QWidget

from suspension_designer.math import get_rotation_matrix_from_quaternion, quaternion_from_direction


class CameraBasis:
    FRONT = np.array([1,0,0])
    RIGHT = np.array([0,1,0])
    UP = np.array([0,0,1])

    BACK = -FRONT
    LEFT = -RIGHT
    DOWN = -UP

    ISOMETRIC = FRONT + RIGHT + UP
    DIMETRIC = 0.333 * FRONT + 0.333 * RIGHT + 0.882 * UP
    TRIMETRIC = 0.393 * FRONT + 0.518 * RIGHT + 0.761 * UP

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