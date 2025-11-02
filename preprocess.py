import subprocess
import argparse
import os
def main():
    parser = argparse.ArgumentParser(description="Preprocess objects")
    parser.add_argument("--skip-rotation", help="Skip the rotation alignment step.", action="store_true")
    args = parser.parse_args()
    # Resolve absolute paths based on the current file
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Blender script
    blender_script = os.path.join(script_dir, "preprocessing", "image_render.py")
    subprocess.run(["blender", "--background", "--python", blender_script], check=True)

    # Python preprocessing scripts
    subprocess.run(["python", os.path.join(script_dir, "preprocessing", "CreateDescriptions.py")], check=True)
    subprocess.run(["python", os.path.join(script_dir, "preprocessing", "CreateEmbeddings.py")], check=True)

    # Optional rotation script
    if not args.skip_rotation:
        subprocess.run(["python", os.path.join(script_dir, "preprocessing", "fixRotation.py")], check=True)

    print("Preprocessing done.")