import PIL.Image
from google import genai
import json
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from build_scene.utils import Attributes, get_attr_from_guid
from config import DESCRIPTIONS, API_KEY, OBJ_DATA, ROTATION_DATA
api_key = API_KEY
client = genai.Client(api_key=api_key)
def fix_rotation(image_paths, name):
    prompt = f"""
You are given four images of the same object from different angles. The name of the object is {name}. Your job is to tell me in what image the the object is shown from the front and you can clearly see and identify it. If the object is radially symmetrical regarding their primary structure,
pick an image where the object looks natural. In order to tell me which image you chose, give me as output a number between 1 and 4, which serves as the index for the list of images I provide.
"""

    response_schema = {
        "type": "object",
        "properties": {
            "image_number": {"type": "integer", "description": "The index of the list of images."},
        },
        "required": ["image_number"],
    }

    content = [PIL.Image.open(image_path) for image_path in image_paths] + [prompt]

    response = client.models.generate_content(model="gemini-2.5-flash", contents=content, config={
        'response_mime_type': 'application/json',
        'response_schema': response_schema
    },
                                              )
    print(response.text)
    return json.loads(response.text)
def main():
    with open(OBJ_DATA, 'r') as file:
        rotation_pics = json.load(file)["prefabs"]

    rotation_pics = get_attr_from_guid(Attributes.NAME,rotation_pics,[])

    with open(ROTATION_DATA, 'r') as file:
        already_fixed = json.load(file)
        already_fixed_guids = [a["guid"] for a in already_fixed]
    object_rotation_map = already_fixed
    rotations = [[0,0,0] , [0,90,0] , [0,-90,0] , [0,180,0]]
    for rotation_pic in rotation_pics:
        if rotation_pic["guid"] in already_fixed_guids: continue
        rotation_data = fix_rotation(rotation_pic["rotationPaths"],rotation_pic["name"])
        object_rotation_map.append({"guid": rotation_pic["guid"], "name": rotation_pic["prefabName"], "rotation": rotations[rotation_data["image_number"]-1]})

    with open(ROTATION_DATA, 'w') as file:
        json.dump(object_rotation_map, file, indent=4)

if __name__ == "__main__":
    main()