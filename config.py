import os
# Global variables
API_KEY = ""

# Paths
git_root = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.expanduser("~/reason_assets/") # PATH to your folder with 3d objects (.fbx, .obj, .glb, .blend)
IMAGES = os.path.expanduser("~/reason_images/") # PATH where to save all images from the preprocessing
DESCRIPTIONS = os.path.join(git_root, "data/descriptions.json") # PATH to object descriptions
EMBEDDINGS = os.path.join(git_root, "data/embeddings.json") # PATH to description embeddings
OBJ_DATA = os.path.join(git_root, "data/object_data.json") # PATH to object metadata
ROTATION_DATA = os.path.join(git_root, "data/rotation_data.json") # PATH to fixed rotation data
RESULTS = os.path.join(git_root, "results") # PATH to the results folder
OUTPUT = os.path.join(RESULTS, "raw_outputs") # Raw pipeline output
BLENDER_FILE = os.path.join(RESULTS, "raw_blender.json") # Converted for blender
RENDERS = os.path.join(RESULTS, "final_renders") # Final renders
