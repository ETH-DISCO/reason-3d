from google import genai
import numpy as np
import json
import os
import time
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DESCRIPTIONS, EMBEDDINGS, API_KEY

# Set your API key
api_key = API_KEY
client = genai.Client(api_key=api_key)


def get_embedding(text):
    """
    Get embedding for text using Gemini API

    Args:
        text: The text to embed

    Returns:
        Embedding array
    """
    # Using Gemini's embedding model
    result = client.models.embed_content(model='text-embedding-004', contents=text)

    # Return the embedding values as a numpy array
    return np.array(result.embeddings[0].values)


def embed_descriptions(descriptions_file, embedding_file_path):
    """
    Embed all prefab descriptions and save the embeddings

    Args:
        descriptions_file: Path to the JSON file with prefab descriptions

    Returns:
        Dictionary with prefab embeddings
    """
    # Load the descriptions
    with open(descriptions_file, 'r') as file:
        prefab_desc = json.load(file)

    embeddings_data = {}
    if os.path.exists(embedding_file_path):
        print(f"Found existing descriptions file: {embedding_file_path}")
        with open(embedding_file_path, 'r') as file:
            try:
                embeddings_data = json.load(file)
                print(f"Loaded {len(embeddings_data)} existing descriptions")
            except json.JSONDecodeError:
                print("Error loading existing descriptions. Starting fresh.")
    guids = [a["guid"] for a in embeddings_data.values()]
    # Process each prefab
    for prefab_name, data in prefab_desc.items():
        try:
            phys = data["physical_properties"]
            func = data["functional_properties"]
            cont = data["contextual_properties"]
            guid = data["guid"]

            #Check if embedding already exists
            if guid in guids:
                continue

            print(f"Generating embedding for: {prefab_name}")
            embedding_phys = get_embedding(phys).tolist()  # Convert to list for JSON serialization
            embedding_func = get_embedding(func).tolist()
            embedding_cont = get_embedding(cont).tolist()

            # Store embedding with other data
            embeddings_data[prefab_name] = {
                "guid": guid,
                "embedding_phys": embedding_phys,
                "embedding_func": embedding_func,
                "embedding_cont": embedding_cont
            }

        except Exception as e:
            print(f"Error processing {prefab_name}: {str(e)}")

        time.sleep(0.8)

    # Save embeddings to a file
    with open(embedding_file_path, 'w') as file:
        json.dump(embeddings_data, file, indent=4)

    print(f"Embeddings saved to {embedding_file_path}")

def main():
    descriptions_file = DESCRIPTIONS
    embedding_file_path = EMBEDDINGS
    embed_descriptions(descriptions_file, embedding_file_path)

if __name__ == "__main__":
    main()