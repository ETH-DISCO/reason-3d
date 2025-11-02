import bpy
import os
import json
import mathutils
import uuid
import sys
sys.path.append(os.path.abspath('.'))
from config import ASSETS, OBJ_DATA, IMAGES

# === CONFIGURATION ===
TARGET_FOLDER = ASSETS      # 🔹 Folder with .blend, .fbx, .obj, .glb, .gltf
SAVE_PATH = IMAGES           # 🔹 Output thumbnails here
JSON_FILE_PATH = OBJ_DATA # 🔹 Output JSON metadata
IMAGE_SIZE = 512

# === DATA STRUCTURES ===
class Vector3Data:
    def __init__(self, v):
        self.x = v.x
        self.y = v.y
        self.z = v.z

    def to_dict(self):
        return {'x': self.x, 'y': self.y, 'z': self.z}

class PrefabData:
    def __init__(self, name, image_paths, rotation_paths, bounds_center, bounds_size):
        self.guid = str(uuid.uuid4())
        self.prefabName = name
        self.imagePaths = image_paths
        self.rotationPaths = rotation_paths
        self.boundsCenter = bounds_center.to_dict()
        self.boundsSize = bounds_size.to_dict()

# === IMPORT HANDLERS ===
def import_model(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.import_scene.obj(filepath=path)
    elif ext == ".glb" or ext == ".gltf":
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".blend":
        with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
            data_to.objects = [name for name in data_from.objects]
        for obj in data_to.objects:
            if obj:
                bpy.context.collection.objects.link(obj)

# === SCENE CLEANUP ===
def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)

# === BOUNDS ===
def get_bounds(obj):
    bpy.context.view_layer.update()

    meshes = []
    if obj.type == 'MESH':
        meshes.append(obj)
    elif obj.children:
        meshes += [child for child in obj.children_recursive if child.type == 'MESH']

    if not meshes:
        return mathutils.Vector((0, 0, 0)), mathutils.Vector((0, 0, 0))

    verts = []
    for mesh_obj in meshes:
        if mesh_obj.data:
            verts.extend([mesh_obj.matrix_world @ v.co for v in mesh_obj.data.vertices])

    min_corner = mathutils.Vector((min(v[i] for v in verts) for i in range(3)))
    max_corner = mathutils.Vector((max(v[i] for v in verts) for i in range(3)))
    center = (min_corner + max_corner) / 2
    size = max_corner - min_corner
    return center, size


# === THUMBNAIL RENDERING ===
def render_thumbnail(obj, angle_name, camera_offset):
    center, size = get_bounds(obj)

    # Setup camera
    cam_data = bpy.data.cameras.new(name='ThumbnailCamera')
    cam = bpy.data.objects.new('ThumbnailCamera', cam_data)
    bpy.context.scene.collection.objects.link(cam)

    cam.location = center + camera_offset.normalized() * size.length * 2.5
    cam.data.type = 'PERSP'
    cam.data.lens = 50
    cam.data.clip_end = 10000

    cam.rotation_euler = (0, 0, 0)
    cam.constraints.new(type='TRACK_TO')
    cam.constraints["Track To"].target = obj
    cam.constraints["Track To"].track_axis = 'TRACK_NEGATIVE_Z'
    cam.constraints["Track To"].up_axis = 'UP_Y'

    # Render settings
    bpy.context.scene.camera = cam
    bpy.context.scene.render.resolution_x = IMAGE_SIZE
    bpy.context.scene.render.resolution_y = IMAGE_SIZE
    bpy.context.scene.render.film_transparent = True
    bpy.context.scene.render.image_settings.color_mode = 'RGBA'
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.filepath = os.path.join(SAVE_PATH, f"{obj.name}_{angle_name}.png")

    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)

    return bpy.context.scene.render.filepath

# === PREFAB PROCESSOR ===
def process_prefabs():
    os.makedirs(SAVE_PATH, exist_ok=True)
    prefab_data_list = []

    for file in os.listdir(TARGET_FOLDER):
        if not file.lower().endswith((".blend", ".fbx", ".obj", ".glb", ".gltf")):
            continue

        print(f"📦 Processing {file}")
        clear_scene()
        full_path = os.path.join(TARGET_FOLDER, file)
        import_model(full_path)

        mesh_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        if not mesh_objs:
            print(f"⚠️ Skipped: No mesh found in {file}")
            continue

        # Group all meshes under an empty
        bpy.ops.object.select_all(action='DESELECT')
        for obj in mesh_objs:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_objs[0]

        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
        prefab_root = bpy.context.object
        prefab_root.name = os.path.splitext(file)[0]

        for obj in mesh_objs:
            obj.parent = prefab_root

        # Render two diagonal thumbnails
        image1 = render_thumbnail(prefab_root, "TopLeft", mathutils.Vector((-1, -1, 2)))
        image2 = render_thumbnail(prefab_root, "BottomRight", mathutils.Vector((1, 1, 1)))
        image3 = render_thumbnail(prefab_root, "(0,0,-1)", mathutils.Vector((0, 1, 0)))
        image4 = render_thumbnail(prefab_root, "(1,0,0)", mathutils.Vector((-1, 0, 0)))
        image5 = render_thumbnail(prefab_root, "(-1,0,0)", mathutils.Vector((1, 0, 0)))
        image6 = render_thumbnail(prefab_root, "(0,0,1)", mathutils.Vector((0, -1, 0)))
        # Get bounds
        center, size = get_bounds(prefab_root)

        # Store metadata
        prefab = PrefabData(
            name=prefab_root.name,
            image_paths=[image1, image2],
            rotation_paths=[image3, image4, image5, image6],
            bounds_center=Vector3Data(-center),
            bounds_size=Vector3Data(size)
        )
        prefab_data_list.append(prefab.__dict__)

    # Save JSON
    with open(JSON_FILE_PATH, 'w') as f:
        json.dump({'prefabs': prefab_data_list}, f, indent=4)
    print(f"✅ JSON saved to {JSON_FILE_PATH}")

# === RUN ===
if __name__ == "__main__":
    bpy.context.scene.world.use_nodes = True
    bg = bpy.context.scene.world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (1, 1, 1, 1)  # White light
    bg.inputs[1].default_value = 0.7  # Strength

    process_prefabs()
