from google import genai
import numpy as np
import json
from sklearn.metrics.pairwise import cosine_similarity
from preprocessing.CreateEmbeddings import  get_embedding
from utils import Attributes, get_attr_from_guid
from config import API_KEY
# Set your API key
api_key = API_KEY
client = genai.Client(api_key=api_key)


def get_scene_objects(scene_description, num_obj):
    text_prompt = f"Given the following scene description: {scene_description}"
    prompt = f"""
    {text_prompt}
    Please follow these steps:
    Step 1: Identify {num_obj} objects in the scene. If you think there are more objects focus on the most important ones. Try to be a bit broad and don't pick objects that that are part of any other objects that you picked. E.g. Don't pick a bed and then pillows and blanket.
    The objects can't be entire rooms or places. The objects also cannot be walls, floors, ceilings, doors, curtains, windows or anything else that has to do with the frame of the room. It also can't be the ground, water, sky or the sun.
    Step 2: Without the context of the scene, describe each object, focusing on its physical properties, functional properties, and contextual properties. Be detailed.
    Step 3: Tell me how many duplicates of the object are required.
    """

    response_schema = {
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The name of the object."},
                        "Physical properties": {"type": "string", "description": "The description of the physical properties of the object. These may include color, shape, material and texture."},
                        "Functional properties": {"type": "string", "description": "The description of the functional properties of the object. What are its purpose, how it's used, and what it does?"},
                        "Contextual properties": {"type": "string", "description": "The description of the contextual properties of the object. In what settings is it used, in which context might it be found, and what settings it belongs in?"},
                        "quantity": {"type": "number", "description": "The amount of this object.",}
                    },
                    "required": ["name", "Physical properties", "Functional properties", "Contextual properties", "quantity"]
                },
            }
        },
        "required": ["objects"]
    }

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt, config={
        'response_mime_type': 'application/json',
        'response_schema': response_schema
        },
    )

    return json.loads(response.text)


def find_assets_for_scene(scene_description, embeddings_data, top_n):
    """
    Generate 10 descriptions of assets required for the scene and return best matches.

    Args:
        scene_description: Description of the scene
        embeddings_data: Dictionary containing prefab embeddings
        top_n: Number of objects to return

    Returns:
        List of top matching prefabs
    """
    #Get objects needed for scene
    scene_objects = get_scene_objects(scene_description, top_n)

    # Calculate similarity with each prefab

    chosen_assets = []
    top5 = []
    for asset in scene_objects.get("objects", scene_objects):
        similarities = []
        name = asset.get("name")
        phys_desc, func_desc, cont_desc = asset.get("Physical properties"), asset.get("Functional properties"), asset.get("Contextual properties")
        object_phys_embedding, object_func_embedding, object_cont_embedding = get_embedding(f"{name}: {phys_desc}"), get_embedding(f"{name}: {func_desc}"), get_embedding(f"{name}: {cont_desc}")
        for prefab_name, data in embeddings_data.items():
            prefab_embedding_phys = np.array(data["embedding_phys"])
            prefab_embedding_func = np.array(data["embedding_func"])
            prefab_embedding_cont = np.array(data["embedding_cont"])

            # Calculate cosine similarity
            similarity = (cosine_similarity([object_phys_embedding], [prefab_embedding_phys])[0][0]/3 + cosine_similarity([object_func_embedding],[prefab_embedding_func])[0][0]/3
                          + cosine_similarity([object_cont_embedding], [prefab_embedding_cont])[0][0]/3)

            similarities.append({
                "prefab_name": prefab_name,
                "guid": data["guid"],
                "quantity": asset.get("quantity"),
                "similarity": similarity
            })

        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x["similarity"], reverse=True)

        top5.append(similarities[:5])
        #############
        # Let LLM decide from top5
        #############
        get_attr_from_guid(Attributes.FULL_DESCRIPTION, top5[-1],[])
        get_attr_from_guid(Attributes.NAME, top5[-1], [])
        index = pick_best_choice(f"{name}: {phys_desc} {func_desc} {cont_desc}", [{k : v for k, v in a.items() if k == "Full description" or k == "name"} for a in top5[-1]])
        if 0 < index < 6: chosen_assets.append(top5[-1][index - 1])
        else:
            chosen_assets.append({"guid": 0, "reason": f"Object not found. No matches exist for '{name}' in your database."})
            print(f"Object not found. No matches exist for '{name}' in your database.")
    return chosen_assets

def pick_best_choice(target_object, top5):
    prompt = """
    You are given a description of a target object and a list of five objects with their descriptions. Your task is to tell me which one of the five objects in the list matches the description of the target object best. 
    Do this by giving me a number between 1 and 5, which serves as an index of the list.
    If you think that no object in the list can be can be used as a substitution for the target object, please output a 0.
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash", contents=[prompt, str(target_object), str(top5)],
        config={
            'response_mime_type': 'application/json',
            'response_schema': int
        },
    )
    return int(response.text)