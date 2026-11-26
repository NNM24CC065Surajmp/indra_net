"""Floor-area and crowd-density calculation from a single photo.

Idea: if you know the real size of one rectangle on the floor (for example a
marked 6 m x 4 m patch, or four floor tiles), you can map any point in the
photo to real floor coordinates in metres. From that you get zone areas,
capacity, persons per square metre, and a density grid (heatmap).

Assumes the floor is flat and the camera does not move after calibration.
"""
from __future__ import annotations
import numpy as np
import cv2

def calibrate(image_points, real_width_m: float, real_length_m: float) -> np.ndarray:
    """Return homography H (image pixels -> floor metres).

    image_points: 4 pixel points of a floor rectangle, in this order:
        top-left, top-right, bottom-right, bottom-left (as seen in the photo).
    real_width_m:  real distance top-left -> top-right.
    real_length_m: real distance top-left -> bottom-left.
    """
    src = np.asarray(image_points, dtype=np.float32).reshape(4, 2)
    dst = np.array([[0, 0], [real_width_m, 0],
                    [real_width_m, real_length_m], [0, real_length_m]], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)

def to_floor(H: np.ndarray, image_points) -> np.ndarray:
    """Convert pixel points (N,2) to floor coordinates in metres (N,2)."""
    pts = np.asarray(image_points, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)

def polygon_area_m2(H: np.ndarray, image_polygon) -> float:
    """Area in square metres of a zone drawn on the photo (list of pixel points)."""
    p = to_floor(H, image_polygon)
    x, y = p[:, 0], p[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)

def capacity(area_m2: float, max_density: float) -> int:
    """Maximum people allowed in a zone = area x allowed persons per m2."""
    return int(area_m2 * max_density)

def density(count: int, area_m2: float) -> float:
    """Persons per square metre."""
    return count / area_m2 if area_m2 > 0 else 0.0

def foot_point(box_xyxy):
    """Bottom-centre of a person box (x1,y1,x2,y2): where the feet touch the floor."""
    x1, y1, x2, y2 = box_xyxy
    return ((x1 + x2) / 2.0, y2)

def grid_density(H: np.ndarray, foot_points_px, width_m: float, length_m: float, cell_m: float = 1.0) -> np.ndarray:
    """Density heatmap: persons per m2 in each cell of a floor grid.

    Returns an array of shape (rows, cols); rows run along length, cols along width.
    People standing outside the calibrated floor rectangle are ignored.
    """
    cols, rows = int(np.ceil(width_m / cell_m)), int(np.ceil(length_m / cell_m))
    grid = np.zeros((rows, cols), dtype=float)
    if len(foot_points_px):
        for fx, fy in to_floor(H, foot_points_px):
            c, r = int(fx // cell_m), int(fy // cell_m)
            if 0 <= r < rows and 0 <= c < cols:
                grid[r, c] += 1
    return grid / (cell_m * cell_m)
