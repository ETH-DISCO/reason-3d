from enum import Enum
import json
import math
import numpy as np
from config import DESCRIPTIONS, OBJ_DATA
class Attributes(Enum):
    FULL_DESCRIPTION = "Full description"
    PHYSICAL_PROPERTIES = "physical_properties"
    FUNCTIONAL_PROPERTIES = "functional_properties"
    CONTEXTUAL_PROPERTIES = "contextual_properties"
    CENTER = "boundsCenter"
    SIZE = "boundsSize"
    NAME = "name"
def get_attr_from_guid(attr, objs, rm_keys):

    # Load correct data
    if attr in [Attributes.CENTER, Attributes.SIZE]:
        attr = attr.value
        with open(OBJ_DATA, 'r') as file:
            bounds_data = json.load(file)["prefabs"]

        for obj in objs:
            for data in bounds_data:
                if data["guid"] ==  obj["guid"]: obj[attr] = data[attr]
            for key in rm_keys:
                del obj[key]

    else:
        with open(DESCRIPTIONS, 'r') as file:
            descriptions_data = json.load(file)
        attr = attr.value
        for obj in objs:
            for k, data in descriptions_data.items():
                if data["guid"] == obj["guid"]:
                    if attr == Attributes.FULL_DESCRIPTION.value: obj[attr] = data[Attributes.PHYSICAL_PROPERTIES.value] + data[Attributes.FUNCTIONAL_PROPERTIES.value] + data[Attributes.CONTEXTUAL_PROPERTIES.value]
                    else: obj[attr] = data[attr]
            for key in rm_keys:
                del obj[key]

    return objs


def calculate_pivot_placement(original_center, original_rotation_degrees, pivot_offset):
    """
    Calculates where to place a new object's pivot so its center aligns
    with an original object's center.

    This function assumes a Left-Hand Coordinate system (like Unity).

    Args:
        original_center (tuple or list or np.ndarray): The world-space position of the
                                                      original box's center.
        original_rotation_degrees (tuple or list or np.ndarray): The world-space rotation
                                                               (Euler angles x, y, z)
                                                               of the original box.
        pivot_offset (tuple or list or np.ndarray): The local-space vector from the
                                                    new box's pivot to its center.

    Returns:
        numpy.ndarray: The world-space position where the new box's pivot
                       should be placed.
    """
    # Ensure inputs are numpy arrays for vector operations
    original_center = np.array(original_center)
    pivot_offset = np.array(pivot_offset)

    # --- Step 1: Create a rotation matrix from the Euler angles ---
    # This matrix will transform the local offset vector into a world-space vector.
    rotation_rad = np.radians(original_rotation_degrees)
    rx, ry, rz = rotation_rad

    rot_x = np.array([
        [1, 0, 0],
        [0, np.cos(rx), -np.sin(rx)],
        [0, np.sin(rx), np.cos(rx)]
    ])
    rot_y = np.array([
        [np.cos(ry), 0, np.sin(ry)],
        [0, 1, 0],
        [-np.sin(ry), 0, np.cos(ry)]
    ])
    rot_z = np.array([
        [np.cos(rz), -np.sin(rz), 0],
        [np.sin(rz), np.cos(rz), 0],
        [0, 0, 1]
    ])

    # Combine matrices (common order: Z, then X, then Y)
    rotation_matrix = rot_y @ rot_x @ rot_z

    # --- Step 2: Rotate the local pivot offset vector ---
    # This tells us the offset direction and distance in world space.
    rotated_offset = rotation_matrix @ pivot_offset

    # --- Step 3: Calculate the new pivot position ---
    # New Pivot Position = Target Center Position - Rotated Offset Vector
    new_pivot_position = original_center - rotated_offset

    return [round(float(a),3) for a in list(new_pivot_position)]

def boxes_intersect(center1, size1, center2, size2):
    """
    Checks if two 3D axis-aligned bounding boxes intersect.

    Parameters:
    - center1, center2: Lists or tuples of (x, y, z) representing the center of each box.
    - size1, size2: Lists or tuples of (width, height, depth) representing the dimensions of each box.

    Returns:
    - True if the boxes intersect, False otherwise.
    """
    error_correction = 0.1
    for i in range(3):  # 0 = x, 1 = y, 2 = z
        min1 = center1[i] - size1[i] / 2
        max1 = center1[i] + size1[i] / 2
        min2 = center2[i] - size2[i] / 2
        max2 = center2[i] + size2[i] / 2

        if max1 < min2 + error_correction or max2 < min1 + error_correction:
            return False  # No overlap on this axis

    return True  # Overlaps on all three axes


def get_rotated_bounding_box(size, rotation_degrees):
    """
    Calculates the new axis-aligned bounding box (AABB) for a box that has been rotated.

    This function operates in a Left-Hand Coordinate System (LHS), consistent
    with engines like Unity.

    Args:
        size (tuple or list or np.ndarray): The original size (width, height, depth)
                                            of the box as a 3D vector.
        rotation_degrees (tuple or list or np.ndarray): The rotation to apply as
                                                        Euler angles (x, y, z) in degrees.

    Returns:
        numpy.ndarray: The size of the new AABB as a 3D vector (width, height, depth).
    """
    # 1. Get the 8 corners of the original AABB centered at the origin.
    half_size = np.array(size) / 2.0

    # Create all 8 corners of the box
    corners = np.array([
        [-half_size[0], -half_size[1], -half_size[2]],
        [-half_size[0], -half_size[1], half_size[2]],
        [-half_size[0], half_size[1], -half_size[2]],
        [-half_size[0], half_size[1], half_size[2]],
        [half_size[0], -half_size[1], -half_size[2]],
        [half_size[0], -half_size[1], half_size[2]],
        [half_size[0], half_size[1], -half_size[2]],
        [half_size[0], half_size[1], half_size[2]]
    ])

    # 2. Create a rotation matrix from the Euler angles (in degrees)
    # Convert degrees to radians for numpy's trig functions
    rotation_rad = np.radians(rotation_degrees)
    rx, ry, rz = rotation_rad

    # Rotation matrix for X-axis
    rot_x = np.array([
        [1, 0, 0],
        [0, np.cos(rx), -np.sin(rx)],
        [0, np.sin(rx), np.cos(rx)]
    ])

    # Rotation matrix for Y-axis
    # This matrix is standard for both LHS and RHS. In LHS, a positive rotation
    # correctly maps the Z+ axis towards the X+ axis.
    rot_y = np.array([
        [np.cos(ry), 0, np.sin(ry)],
        [0, 1, 0],
        [-np.sin(ry), 0, np.cos(ry)]
    ])

    # Rotation matrix for Z-axis
    rot_z = np.array([
        [np.cos(rz), -np.sin(rz), 0],
        [np.sin(rz), np.cos(rz), 0],
        [0, 0, 1]
    ])

    # Combine the rotation matrices. A common order is Z, then X, then Y.
    # This means we apply Z first, then X, then Y to the vectors.
    # The combined matrix is R = Ry * Rx * Rz
    rotation_matrix = rot_y @ rot_x @ rot_z

    # 3. Apply this rotation to all 8 corners
    # We use np.dot for matrix multiplication. The .T transposes the matrices
    # for the correct multiplication shape.
    rotated_corners = np.dot(rotation_matrix, corners.T).T

    # 4. Find the minimum and maximum extents of the new rotated corners
    min_corner = rotated_corners.min(axis=0)
    max_corner = rotated_corners.max(axis=0)

    # 5. The new bounding box size is the difference between the max and min corners
    new_size = max_corner - min_corner

    return [round(a,3) for a in list(new_size)]