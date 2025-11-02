import bpy
import json
import os
import math
from mathutils import Euler, Vector
import sys
sys.path.append(os.path.abspath('.'))
from config import BLENDER_FILE, RENDERS, ASSETS

# === CONFIG ===
unity_layout_file = BLENDER_FILE
asset_base_path = ASSETS
material_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'materials')
floor_filepath = os.path.join(material_dir,"wood_floor_worn_1k.blend/wood_floor_worn_1k.blend")
wall_blend_filepath = os.path.join(material_dir,"beige_wall_001_1k.blend/beige_wall_001_1k.blend")
floor_path = floor_filepath
wall_path = wall_blend_filepath
material_name = os.path.basename(floor_path)[:-9]
wall_material_name = os.path.basename(wall_path)[:-9]


output_folder = RENDERS

with bpy.data.libraries.load(floor_path, link=False) as (data_from, data_to):
    if material_name in data_from.materials:
        data_to.materials.append(material_name)
    else:
        print(f"Error: Material '{material_name}' not found in '{floor_path}'")
with bpy.data.libraries.load(wall_path, link=False) as (data_from, data_to):
    if wall_material_name in data_from.materials:
        data_to.materials.append(wall_material_name)
    else:
        print(f"Error: Material '{wall_material_name}' not found in '{wall_blend_filepath}'")

# === CLEAR DEFAULT SCENE ===
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# === IMPORT LAYOUT ===
with open(unity_layout_file, 'r') as f:
    layout = json.load(f)

for info in layout:
    uid = info['uid']
    position = info['position']
    rotation_deg = info['rotation']
    rotation_rad = [math.radians(r) for r in rotation_deg]
    pre_rotation_deg = info['pre_rotation'][1]
    pre_rot_rad = math.radians(pre_rotation_deg)

    # Supported extensions in priority order
    extensions = [".glb", ".fbx", ".obj", ".blend"]
    file_path = None

    # Look for the first existing file with any supported extension
    for ext in extensions:
        candidate = os.path.join(asset_base_path, f"{uid}{ext}")
        if os.path.isfile(candidate):
            file_path = candidate
            break

    if not file_path:
        print(f"❌ No supported file found for UID: {uid}")
        continue
    else:
        print(f"📦 Importing: {file_path}")

        # Track objects before import
        objects_before_import = set(bpy.context.scene.objects)

        # Determine which importer to use
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".glb" or ext == ".gltf":
            bpy.ops.import_scene.gltf(filepath=file_path)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=file_path)
        elif ext == ".obj":
            bpy.ops.import_scene.obj(filepath=file_path)
        elif ext == ".blend":
            with bpy.data.libraries.load(file_path, link=False) as (data_from, data_to):
                data_to.objects = [name for name in data_from.objects]
            for obj in data_to.objects:
                if obj:
                    bpy.context.collection.objects.link(obj)

    objects_after_import = set(bpy.context.scene.objects)
    new_objects = objects_after_import - objects_before_import
    # 1. Filter out non-mesh objects and identify the target objects for joining
    mesh_objects_to_join = [obj for obj in new_objects if obj.type == 'MESH']

    # if len(mesh_objects_to_join) < 2:
    #     print("Not enough mesh objects to perform a join operation.")

    # 2. Deselect everything
    bpy.ops.object.select_all(action='DESELECT')

    # 3. Choose the active object for the join operation
    # It's often good practice to pick an object that is NOT parented,
    # or clear its parent beforehand.
    # Let's pick the first eligible mesh object as the active one.
    active_join_obj = None
    for obj in mesh_objects_to_join:
        if obj.parent is None:  # Prioritize unparented objects
            active_join_obj = obj
            break
    if active_join_obj is None:  # If all are parented, just pick the first one
        active_join_obj = mesh_objects_to_join[0]

    # Clear parent of the chosen active object if it has one (keeping its world transform)
    if active_join_obj.parent:
        print(f"Clearing parent of active object '{active_join_obj.name}' before join.")
        # Ensure it's active and selected for the parent_clear operator
        bpy.context.view_layer.objects.active = active_join_obj
        active_join_obj.select_set(True)
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
        active_join_obj.select_set(False)  # Deselect it again for now

    # Now select all objects to be joined, ensuring the chosen active object is last selected/set active
    bpy.context.view_layer.objects.active = active_join_obj  # Make it active first
    active_join_obj.select_set(True)  # Select it

    for obj in mesh_objects_to_join:
        if obj != active_join_obj:
            # Clear parent of other objects to be joined (keeping their world transform)
            if obj.parent:
                print(f"Clearing parent of object '{obj.name}' before join.")
                # To clear parent, obj must be active and selected
                current_active = bpy.context.view_layer.objects.active  # Store current active
                current_selected = [o for o in bpy.context.selected_objects]  # Store current selection

                bpy.ops.object.select_all(action='DESELECT')
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

                # Restore previous active and selection for the join op
                bpy.ops.object.select_all(action='DESELECT')
                for sel_obj in current_selected:
                    sel_obj.select_set(True)
                bpy.context.view_layer.objects.active = current_active

            obj.select_set(True)  # Select the object for joining

    try:
        # Switch to Object Mode if not already to ensure join operation works
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.join()
        print("Objects joined successfully.")
        loaded = bpy.context.view_layer.objects.active
    except Exception as e:
        print(f"Error joining objects: {e}. Ignoring the join operation.")
        loaded = None  # Set to None if join failed

    # Might be unnecessary
    bpy.ops.object.select_all(action='DESELECT')
    loaded.select_set(True)
    # 2. Calculate the world-space bounding box center of the object
    # obj.bound_box gives local coordinates of the 8 corners
    # obj.matrix_world transforms these local coordinates to world coordinates
    bbox_corners_world = [loaded.matrix_world @ Vector(corner) for corner in loaded.bound_box]
    bbox_center_world = sum(bbox_corners_world, Vector()) / 8

    # 3. Set the 3D cursor to this calculated world-space center
    bpy.context.scene.cursor.location = bbox_center_world

    # 4. Set the object's origin to the 3D cursor
    # This operation is generally less context-sensitive than view3d operators
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    #bpy.ops.object.origin_set(type='GEOMETRY_ORIGIN', center='BOUNDS')
    bpy.ops.transform.rotate(value=-math.radians(pre_rot_rad), orient_axis='Z')
    # Apply transform here.
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    bpy.context.object.rotation_mode = "YXZ"
    for i in range(3):
        loaded.rotation_euler[i] += rotation_rad[i]

    # Set position
    loaded.location = position
    print(loaded.location)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


# === ADD DYNAMIC FLOOR PLANE ===
# Compute bounds from all mesh objects
all_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']

if not all_objs:
    raise RuntimeError("No mesh objects found in scene.")

# Let's refine the bound_box calculation for more accuracy.
# This calculates the global min/max for all objects.
bbox_min = Vector((float('inf'), float('inf'), float('inf')))
bbox_max = Vector((float('-inf'), float('-inf'), float('-inf')))

for obj in all_objs:
    # Ensure object is in world space for bound_box calculation
    bpy.context.view_layer.update() # Update scene data for correct bounds

    # Iterate through object's bounding box corners and transform them to world space
    for corner in obj.bound_box:
        world_corner = obj.matrix_world @ Vector(corner)
        for i in range(3):
            bbox_min[i] = min(bbox_min[i], world_corner[i])
            bbox_max[i] = max(bbox_max[i], world_corner[i])

min_coord = bbox_min
max_coord = bbox_max

center = (max_coord-min_coord) / 2
min_z = min_coord.z # This is the absolute lowest point of any object

# Calculate the center of the bounding box for placing the floor
floor_center_x = (min_coord.x + max_coord.x) / 2
floor_center_y = (min_coord.y + max_coord.y) / 2

# Calculate extents
x_extent = max_coord.x - min_coord.x
y_extent = max_coord.y - min_coord.y

bpy.ops.mesh.primitive_plane_add(size=1, location=(floor_center_x, floor_center_y, 0))
floor = bpy.context.active_object
floor.name = "Floor"
floor.scale = (x_extent, y_extent, 1)


# Assign material to floor object
floor = bpy.context.object  # Or explicitly: bpy.data.objects["Floor"]
if floor.data.materials:
    #floor.data.materials[0] = mat
    floor.data.materials[0] = bpy.data.materials[material_name]
else:
    floor.data.materials.append(bpy.data.materials[material_name])



# === ADD FOUR WALLS ===

wall_height = 2.7  # Add some height margin
scene_width = (max_coord.x - min_coord.x)
scene_depth = (max_coord.y - min_coord.y)



# The name of the existing Poly Haven material you want to use for the front faces.
# IMPORTANT: This material must already be present in your Blender file.
polyhaven_material_name = wall_material_name # <-- Make sure this matches the name in your file

# --- Check for the existence of the Poly Haven material ---
polyhaven_mat = bpy.data.materials.get(polyhaven_material_name)

if not polyhaven_mat:
    # If the source material doesn't exist, stop and raise an error.
    raise NameError(f"Error: Material '{polyhaven_material_name}' not found. "
                    "Please ensure it's loaded in the blend file before running the script.")

def create_wall(name, location, rotation, length_scale): # Add length_scale parameter
    bpy.ops.mesh.primitive_plane_add(size=1, location=location, rotation=rotation)
    wall = bpy.context.active_object
    wall.name = name
    wall.scale = (length_scale, wall_height, 1) # Use length_scale for width
    print("wall instantiated")
    if wall.data.materials:
        wall.data.materials[0] = polyhaven_mat
    else:
        wall.data.materials.append(polyhaven_mat)
    return wall

# UNCOMMENT THIS BLOCK IF YOU WANT WALLS
# =========================
# # Back wall (Y+), facing -Y (inward)
# create_wall("BackWall", (offset_x,offset_y + y / 2, wall_height / 2), (math.radians(90), 0, 0), x)
#
# # Front wall (Y-), facing +Y (inward)
# create_wall("FrontWall", (offset_x, -y / 2 + offset_y, wall_height / 2), (math.radians(90), 0, math.radians(180)), x)
#
# # Left wall (X-), facing +X (inward)
# create_wall("LeftWall", (-x / 2 + offset_x, offset_y, wall_height / 2), (math.radians(90), 0, math.radians(90)), y)
#
# # Right wall (X+), facing -X (inward)
# create_wall("RightWall", (x / 2 + offset_x, offset_y, wall_height / 2), (math.radians(90), 0, math.radians(-90)), y)
# ========================

# === SET UP CAMERA ===
# Add camera above all objects
scene = bpy.context.scene
cam_data = bpy.data.cameras.new("OverheadCamera")
cam_obj = bpy.data.objects.new("OverheadCamera", cam_data)
scene.collection.objects.link(cam_obj)
scene.camera = cam_obj

# Calculate scene bounds
all_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
if not all_objs:
    raise RuntimeError("No mesh objects found in scene.")

min_coord = Vector((min(o.location.x for o in all_objs),
                    min(o.location.y for o in all_objs),
                    min(o.location.z for o in all_objs)))
max_coord = Vector((max(o.location.x for o in all_objs),
                    max(o.location.y for o in all_objs),
                    max(o.location.z for o in all_objs)))
center = (min_coord + max_coord) / 2
width = (max_coord - min_coord).length
print(width, width)
# === SET CAMERA: ANGLED SIDE VIEW ===
cam_data.type = 'PERSP'
cam_obj.location = (
    floor_center_x - scene_width * 1.8,
    floor_center_y - scene_width * 1.8,
    scene_width * 1.8
)

# Point camera toward the center of the scene
direction = Vector((floor_center_x, floor_center_y, 0)) - cam_obj.location
cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# === DELETE ALL EXISTING LIGHTS ===
for obj in [o for o in bpy.data.objects if o.type == 'LIGHT']:
    bpy.data.objects.remove(obj, do_unlink=True)

# === SET UP LIGHT ===

scene.world.use_nodes = True
bg = scene.world.node_tree.nodes['Background']
bg.inputs[1].default_value = 0.1

# Create new Light data of type 'AREA'
area_light_name = "RoomAreaLight"
light_data = bpy.data.lights.new(name=area_light_name, type='AREA')

# Set the energy (intensity) of the area light
# Area lights usually need much higher energy than point lights for similar brightness
light_data.energy = 1000 # Adjust this value (e.g., from 1000 to 10000) as needed for brightness
# Larger size = softer shadows, Smaller size = sharper shadows
light_data.size = 10 # Example size in Blender Units (meters). Adjust as desired.

# Create a new object with the area light data
light = bpy.data.objects.new(name=area_light_name, object_data=light_data)


scene.collection.objects.link(light)

light.location = (floor_center_x, floor_center_y, 4)
# === RENDER SETTINGS ===
scene.render.engine = 'CYCLES'  # Or 'BLENDER_EEVEE'
bpy.context.scene.cycles.samples = 128
bpy.context.view_layer.use_pass_ambient_occlusion = True
# scene.render.filepath = output_path
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024

# === ENABLE TRANSPARENT BACKGROUND ===
scene.render.film_transparent = True

# === RENDER ===
scene.render.filepath = os.path.join(output_folder, "final_render.png")
bpy.ops.render.render(write_still=True)

