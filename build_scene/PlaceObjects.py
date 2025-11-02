
import json
from collections import Counter
import argparse
from google import genai
import subprocess
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Object_retriever import find_assets_for_scene
from utils import get_attr_from_guid, get_rotated_bounding_box, boxes_intersect, calculate_pivot_placement
from utils import Attributes
from config import API_KEY, ROTATION_DATA, EMBEDDINGS
# Set your API key
api_key = API_KEY
client = genai.Client(api_key=api_key)
model = "gemini-2.5-flash"
def get_constraints(scene_description, object_list):
    prompt = ("You are given a scene description and a list of objects that are part of that scene. Your task is to give me positional and rotational constraints regarding the objects. If the scene description is vague and doesn't contain any positional and rotational information, I "
              "need you to add this information to create a scene that makes sense. Especially important is where the objects are placed upon or if they are against a wall and if there should be space between them. There should be a constraint for each object about this. E.g. the object is standing on the ground. The object is on the table. "
              "The object is against the north wall. etc. You are only allowed to use objects from the list to write constraints. Refrain from absolute measurements like 6 feet and so on. Only output the constraints. It may be a long list. Under no circumstances should you contradict constraints from the scene description. "
              "Start by extracting the constraints that are already part of the scene description and then add the other constraints.")

    response = client.models.generate_content(
        model="gemini-2.5-flash", contents=[prompt, str(scene_description), str(object_list)]
    )

    return response.text
def rescale_prefabs(objs):
    objs = get_attr_from_guid(Attributes.SIZE, objs, [])
    objs = get_attr_from_guid(Attributes.CENTER, objs, [])
    for obj in objs:
        scale_factor = 1 # Legacy value
        obj["scale_factor"] = scale_factor
        obj["boundsCenter"] = [v*scale_factor for k, v in obj["boundsCenter"].items()] # Pivot adjusted for scaling
        obj["boundsSize"] = [round(v*scale_factor, 3) for k, v in obj["boundsSize"].items()] # Size adjusted for scaling
    return objs # guid, name, size, boundsSize, boundsCenter, scale_factor

def get_order(constraints, objects):
    prompt = ("You are given a list of constraints on objects about their placements and rotations. You also get the list containing all the objects. Your goal is to sort the list such that "
              "placing the objects one by one is easiest. For example, if you have a constraint: The cup is on the table. You want to place the table before the cup."
              "IMPORTANT: Under no circumstances should you add or remove any objects from the list.")

    response = client.models.generate_content(
        model="gemini-2.5-flash", contents=[prompt, str(constraints), str(objects)],
        config={
            'response_mime_type': 'application/json',
            'response_schema': list[str]
        },
    )

    return json.loads(response.text)
def place_objects(scene_description, object_name, object_size, placed_objects, constraints):
    system_instructions = "You are an expert AI assistant specializing in 3D object placement for the Unity game engine. Your task is to determine the correct position and rotation for a new object based on a scene description and a list of existing objects. This task requires a lot of complex reasoning and some math."
    prompt = f"""
    CRITICAL CONTEXT: UNITY'S 3D SPACE:
    You MUST adhere to these rules at all times. All calculations and outputs must conform to Unity's coordinate system.
    
    Coordinate System: Left-Hand System (LHS).
    +X axis: Right
    +Y axis: Up
    +Z axis: Forward
    Default Object Orientation: An object with zero rotation (0, 0, 0) faces the positive Z-axis (0, 0, 1) (+Z).
    Rotation Rule: Rotations are Euler angles (X, Y, Z) in degrees.
    A positive rotation of 90 degrees around the Y-axis rotates an object from the Forward direction (Z+) towards the Right direction (X+).
    A negative rotation of 90 degrees around the Y-axis rotates an object from the Forward direction (Z+) towards the Left direction (X-).
    The floor is at Y = 0.
    The center of the room is at X = Z = 0
    
    YOUR TASK:
    1.  Analyze the Scene: Read the scene_description and the already_placed_objects list.
    2.  Determine Placement: Calculate the position and rotation for the new object, {object_name}, which has a bounding box size of {object_size}. Think where this object should be naturally placed and which way it should be facing, if there are no specific constraints on that matter..
    3.  Adhere to Constraints: Ensure the placement satisfies all layout rules from the scene_description and the constraints list. But ALWAYS prioritize the scene_description, when there are contradictions.
    4.  Output JSON: Generate a single, clean JSON object with the final position and rotation.
    INPUT DATA:
    Scene Description: {scene_description}
    Constraints: {constraints}
    New Object to Place:
    name: {object_name}
    size: {object_size}
    Already Placed Objects: {placed_objects}
    Each object in the list has a name, center, size, size_after_rotation and rotation.
    The size_after_rotation field is the original size of the bounding box with the applied rotation. This is to save you the trouble of doing the math yourself.
    
    """
    response_schema = {
        "type": "object",
            "properties": {
                "center": {"type": "array",
                                 "description": "The center of the object as a 3d vector.",
                                 "items": {"type": "number"}
                                 },
                "rotation": {"type": "array", "description": "The rotation of the object as a 3d vector using degrees.",
                             "items": {"type": "number"}
                             }
            },
        "required": ["center", "rotation"]
    }

    global model

    response = client.models.generate_content(
        model=model, contents=[prompt],
        config={
            'response_mime_type': 'application/json',
            'response_schema': response_schema,
            'system_instruction': system_instructions
        },
    )

    obj = json.loads(response.text)
    obj["name"] = object_name
    obj["size"] = object_size
    obj["size_after_rotation"] = get_rotated_bounding_box(object_size, obj["rotation"])
    return obj
def update_object(scene_description, object_name, placed_objects, constraints, intersection_object):
    system_instructions = "You are an expert AI assistant specializing in 3D object placement for the Unity game engine. Your task is to determine the correct position and rotation for a single object in the scene, based on a scene description and a list of existing objects. This task requires a lot of complex reasoning and some math."
    intersection_prompt = "The objects bounding box is intersecting other objects bounding boxes. Analyze these intersections in the list and ask yourself, if that makes sense."
    intersection_data = f"Intersecting objects list: {intersection_object}. All objects in this list have a non negligible intersecting bounding box with the {object_name}, whether this makes sense or not, is your task to figure out."
    prompt = f"""
        CRITICAL CONTEXT: UNITY'S 3D SPACE:
        You MUST adhere to these rules at all times. All calculations and outputs must conform to Unity's coordinate system.

        Coordinate System: Left-Hand System (LHS).
        +X axis: Right
        +Y axis: Up
        +Z axis: Forward
        Default Object Orientation: An object with zero rotation (0, 0, 0) faces the positive Z-axis (0, 0, 1).
        Rotation Rule: Rotations are Euler angles (X, Y, Z) in degrees.
        A positive rotation around the Y-axis rotates an object from the Forward direction (Z+) towards the Right direction (X+).
        A negative rotation around the Y-axis rotates an object from the Forward direction (Z+) towards the Left direction (X-).
        Bounding Boxes: An object's bounding box rotates with the object. When placing an object relative to another, you must use the existing object's rotation to determine the true world-space orientation and boundaries of its bounding box.
        The floor is at Y = 0.
        The center of the room is at X = Z = 0

        YOUR TASK:
        1.  Analyze the Scene: Read the scene_description and the already_placed_objects list.
        2.  Analyze specific object: Look at the {object_name}. Ignore all other objects. Focus only on the {object_name} and check if it satisfies the constraints. Then update it's position and rotation in the output.
        3.  Adhere to Constraints: Ensure the placement satisfies all layout rules from the scene_description and the constraints list. But ALWAYS prioritize the scene_description, when there are contradictions. {intersection_prompt if len(intersection_object)>0 else ""}
        4.  Output JSON: Generate a single, clean JSON object with the final position and rotation.
        INPUT DATA:
        Scene Description: {scene_description}
        Constraints: {constraints}
        Already Placed Objects: {placed_objects}
        Each object in the list has a name, center, size, size_after_rotation and rotation.
        The size_after_rotation field is the original size of the bounding box with the applied rotation. This is to save you the trouble of doing the math yourself.
        {intersection_data if len(intersection_object)>0 else ""}
        """
    response_schema = {
        "type": "object",
            "properties": {
                "center": {"type": "array",
                                 "description": "The center of the object as a 3d vector.",
                                 "items": {"type": "number"}
                                 },
                "rotation": {"type": "array", "description": "The rotation of the object as a 3d vector using degrees.",
                             "items": {"type": "number"}
                             }
            },
        "required": ["center", "rotation"]
    }
    global model
    response = client.models.generate_content(
        model=model, contents=[prompt, str(constraints) ,str(placed_objects)],
        config={
            'response_mime_type': 'application/json',
            'response_schema': response_schema,
            'system_instruction': system_instructions
        },
    )
    obj = json.loads(response.text)
    return obj

def place_objects_from_list(scene_description, obj_list, skip_refinement=False):
    with open(ROTATION_DATA, 'r') as file:
        rotation_data = json.load(file)
    sizes = obj_list

    names = [obj["name"] for obj in sizes]

    constraints = get_constraints(scene_description, names)
    objs = rescale_prefabs(sizes)
    obj_mod = []
    for obj in objs:
        new_obj = {"size" if k == "boundsSize" else k: v for k, v in obj.items()}
        rotation = [a["rotation"] for a in rotation_data if a["guid"] == obj["guid"]] # [[0,0,0]] or [] depending on, if rotation was fixed
        if len(rotation) > 0:
            swap = False if (rotation[0][1]/90)%2 == 0 else True
            if swap:
                new_obj["size"][0], new_obj["size"][-1] = new_obj["size"][-1], new_obj["size"][0]
        obj_mod.append(new_obj)
    objs = obj_mod
    # name, guid, size, scale_factor, boundsCenter
    order = get_order(constraints,names)
    objs.sort(key=lambda _obj: order.index(_obj["name"]))
    #########
    # Place objects one by one
    ########
    placed_objects = []

    for obj in objs:
        placed_objects.append(place_objects(scene_description, obj["name"], obj["size"], placed_objects, constraints))
    # name, size, center, rotation, size_after_rotation

    # for obj_data, obj_transform in zip(objs, placed_objects):
    #     rots = [a["rotation"] for a in rotation_data if a["guid"] == obj_data["guid"]]
    #     if len(rots)>0:
    #         new_rotation = [a + b for a, b in zip(obj_transform["rotation"], rots[0])]
    #     else: new_rotation = obj_transform["rotation"]
    #     output0.append({"guid": obj_data["guid"], "center": calculate_pivot_placement(obj_transform["center"], new_rotation, [a for a in obj_data["boundsCenter"]]),
    #                    "rotation": new_rotation, "scale_factor": obj_data["scale_factor"]})
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Build absolute path to placed_objects.json in the same directory
    json_path = os.path.join(script_dir, "placed_objects.json")
    json_data_path = os.path.join(script_dir, "placed_objects_data.json")
    if skip_refinement:
        # Write JSON
        with open(json_path, 'w') as file:
            json.dump(placed_objects, file, indent=4)
        with open(json_data_path, 'w') as file:
            json.dump(objs, file, indent=4)
        return

    #########################
    # Refinement step
    #########################

    for obj in placed_objects:
        intersections = []
        for _obj in placed_objects:
            if _obj["name"] == obj["name"]: continue
            if boxes_intersect(obj["center"], obj["size_after_rotation"], _obj["center"], _obj["size_after_rotation"]):
                intersections.append(_obj["name"])
        if not intersections: continue
        new_values = update_object(scene_description, obj["name"], placed_objects, constraints, intersections)

        obj["center"] = new_values["center"]
        obj["rotation"] = new_values["rotation"]
        obj["size_after_rotation"] = get_rotated_bounding_box(obj["size"], new_values["rotation"])

    # for obj_data, obj_transform in zip(objs, placed_objects):
    #     rots = [a["rotation"] for a in rotation_data if a["guid"] == obj_data["guid"]]
    #     if len(rots)>0:
    #         obj_transform["rotation"] = [a + b for a, b in zip(obj_transform["rotation"], rots[0])]
    #     output.append({"guid": obj_data["guid"], "center": calculate_pivot_placement(obj_transform["center"],obj_transform["rotation"], [a for a in obj_data["boundsCenter"]]),
    #                    "rotation": obj_transform["rotation"], "scale_factor": obj_data["scale_factor"]})

    with open(json_path, 'w') as file:
        json.dump(placed_objects, file, indent=4)
    with open(json_data_path, 'w') as file:
        json.dump(objs, file, indent=4)

    return
def main():
    parser = argparse.ArgumentParser(description="Build scene.")
    parser.add_argument("--prompt", help="The input prompt.", required=True)
    parser.add_argument("--no-refinement", help="Skip the refinement step.", action="store_true")
    parser.add_argument("--num-objects", help="Override the number of different objects to use.", default="")
    parser.add_argument("--model", help="The gemini model used.", default="gemini-2.5-flash")
    args = parser.parse_args()
    skip_refinement = args.no_refinement
    global model
    model = args.model
    with open(EMBEDDINGS, 'r') as file:
        embeddings_data = json.load(file)

    prompt = args.prompt
    retrieved_objs = find_assets_for_scene(prompt, embeddings_data,args.num_objects)
    retrieved_objs = get_attr_from_guid(Attributes.NAME, retrieved_objs, [])
    scene_guids = sum([[data["guid"] for a in range(data["quantity"])] for data in retrieved_objs if data["guid"] != 0], [])
    counter = Counter(scene_guids)
    seen=[]
    input_objects = []
    for o in retrieved_objs:
        if o["guid"] in seen: continue
        seen.append(o["guid"])
        for i in range(counter[o["guid"]]):
            input_objects.append({"guid": o["guid"], "name": o["name"]+str(i+1) if i>0 else o["name"]})

    place_objects_from_list(prompt, input_objects, skip_refinement)
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../rendering/convert_for_blender.py"))
    subprocess.run(["python", script_path], check=True)
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../rendering/render_layout.py"))
    subprocess.run(["blender", "--background", "--python", script_path], check=True)
if __name__ == "__main__":
    main()