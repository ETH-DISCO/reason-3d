from google import genai
import PIL.Image
import os
import json
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OBJ_DATA, DESCRIPTIONS, API_KEY
# Set your API key
api_key = API_KEY
client = genai.Client(api_key=api_key)


def get_structured_description(image_path1, image_path2,  name):
    """
    Get a structured description of an object from two images using Gemini.
    
    Args:
        image_path1: Path to the first image file
        image_path2: Path to the second image file
        
    Returns:
        Dictionary containing structured description with physical, functional, 
        and contextual properties
    """
    # Load the images
    image1 = PIL.Image.open(image_path1)
    image2 = PIL.Image.open(image_path2)

    # Prepare the prompt for structured description
    prompt = f"""
    The two images show the same object from different angles/perspectives.
    Please provide a detailed structured description of this object divided into these three categories:
    
    1. Physical properties (size, shape, color, material, parts/components)
    2. Functional properties (purpose, how it's used, what it does)
    3. Contextual properties (where it might be found, what settings it belongs in)
    
    You may use the name of the object as a hint, if it is helpful: {name}.
    Also name what the object is don't copy the input name.
    """

    response_schema = {
        "type": "object",
            "properties": {
                "Physical properties": {"type": "string"},
                "Functional properties": {"type": "string"},
                "Contextual properties": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["Physical properties", "Functional properties","Contextual properties","name"]

    }

    response = client.models.generate_content(
        model="gemini-2.0-flash", contents=[image1, image2, prompt], config={
            'response_mime_type': 'application/json',
            'response_schema': response_schema
        },
    )
    return json.loads(response.text)


def process_prefabs(json_file_path):
    """
    Process all prefabs in the JSON file and generate structured descriptions for each
    
    Args:
        json_file_path: Path to the prefab_data.json file
        
    Returns:
        Dictionary with prefab structured descriptions
    """

    # Set default output path if not provided
    output_file_path = DESCRIPTIONS

    # Load prefab data
    with open(json_file_path, 'r') as file:
        prefab_data = json.load(file)

    # Check if description file already exists and load it
    existing_descriptions = {}
    if os.path.exists(output_file_path):
        print(f"Found existing descriptions file: {output_file_path}")
        with open(output_file_path, 'r') as file:
            try:
                existing_descriptions = json.load(file)
                print(f"Loaded {len(existing_descriptions)} existing descriptions")
            except json.JSONDecodeError:
                print("Error loading existing descriptions. Starting fresh.")

    guids = [a["guid"] for a in existing_descriptions.values()]
    # Process each prefab
    new_count = 0
    for prefab in prefab_data["prefabs"]:
        prefab_name = prefab["prefabName"]
        guid = prefab["guid"]

        # Skip if already processed
        if guid in guids:
            continue

        print(f"Processing new prefab: {prefab_name}")
        new_count += 1

        # Extract image paths
        image_path1 = prefab["imagePaths"][0]
        image_path2 = prefab["imagePaths"][1]

        try:
            # Get structured description
            description = get_structured_description(image_path1, image_path2, prefab_name)

            # Store result
            existing_descriptions[prefab_name] = {
                "guid": guid,
                "physical_properties": description.get("Physical properties"),
                "functional_properties": description.get("Functional properties"),
                "contextual_properties": description.get("Contextual properties"),
                "name": description.get("name"),
            }

            print(f"✓ Successfully processed {prefab_name}")
            with open(output_file_path, 'w') as file:
                json.dump(existing_descriptions, file, indent=4)
            # Add a short delay between API calls to avoid rate limiting

        except Exception as e:
            print(f"✗ Error processing {prefab_name}: {str(e)}")

    print(f"\nStructured descriptions saved to {output_file_path}")
    return existing_descriptions


# Run the script
if __name__ == "__main__":
    json_file_path = OBJ_DATA
    structured_descriptions = process_prefabs(json_file_path)