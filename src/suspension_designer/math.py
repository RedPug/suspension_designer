import numpy as np
from numba import njit, float64

@njit(float64[:,:](float64[:]))
def get_rotation_matrix_from_quaternion(q: np.ndarray) -> np.ndarray:
    """Converts a quaternion (w, x, y, z) to a 3x3 rotation matrix."""
    w, x, y, z = q[0], q[1], q[2], q[3]
    return np.array([
        [1 - 2*y**2 - 2*z**2,     2*x*y - 2*z*w,         2*x*z + 2*y*w],
        [2*x*y + 2*z*w,           1 - 2*x**2 - 2*z**2,   2*y*z - 2*x*w],
        [2*x*z - 2*y*w,           2*y*z + 2*x*w,         1 - 2*x**2 - 2*y**2]
    ])

@njit(float64[:](float64[:], float64[:]))
def mult_quaternions(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Multiplies two quaternions p and q."""
    return np.array([
        p[0]*q[0] - p[1]*q[1] - p[2]*q[2] - p[3]*q[3],
        p[0]*q[1] + p[1]*q[0] + p[2]*q[3] - p[3]*q[2],
        p[0]*q[2] - p[1]*q[3] + p[2]*q[0] + p[3]*q[1],
        p[0]*q[3] + p[1]*q[2] - p[2]*q[1] + p[3]*q[0]
    ])

@njit(float64[:](float64[:,:]))
def quat_from_matrix(m):
    t = m[0][0] + m[1][1] + m[2][2]

    if t > 0:
        s = 2 * np.sqrt(t + 1)
        w = 0.25 * s
        x = (m[2][1] - m[1][2]) / s
        y = (m[0][2] - m[2][0]) / s
        z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = 2 * np.sqrt(1 + m[0][0] - m[1][1] - m[2][2])
        w = (m[2][1] - m[1][2]) / s
        x = 0.25 * s
        y = (m[0][1] + m[1][0]) / s
        z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = 2 * np.sqrt(1 + m[1][1] - m[0][0] - m[2][2])
        w = (m[0][2] - m[2][0]) / s
        x = (m[0][1] + m[1][0]) / s
        y = 0.25 * s
        z = (m[1][2] + m[2][1]) / s
    else:
        s = 2 * np.sqrt(1 + m[2][2] - m[0][0] - m[1][1])
        w = (m[1][0] - m[0][1]) / s
        x = (m[0][2] + m[2][0]) / s
        y = (m[1][2] + m[2][1]) / s
        z = 0.25 * s

    result = np.array([w, x, y, z])
    result /= np.linalg.norm(result)
    return result

# @njit(float64[:](float64[:], float64[:]))
def quaternion_from_direction(direction: np.ndarray, up: np.ndarray = np.array([0.0, 1.0, 0.0])) -> np.ndarray:
    """Creates a quaternion that represents the rotation from the world forward vector to the given direction."""
    direction = direction / np.linalg.norm(direction)
    right = np.cross(up, direction)
    right /= np.linalg.norm(right)
    up_corrected = np.cross(direction, right)

    rotation_matrix = np.array([
        [right[0], up_corrected[0], direction[0]],
        [right[1], up_corrected[1], direction[1]],
        [right[2], up_corrected[2], direction[2]]
    ])

    return quat_from_matrix(rotation_matrix)