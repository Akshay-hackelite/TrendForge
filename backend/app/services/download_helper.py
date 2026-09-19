import gdown
import uuid
import os
import requests

def download_from_drive(drive_url: str) -> str:
    output_path = f"/tmp/{uuid.uuid4()}.mp4"
    gdown.download(drive_url, output_path, fuzzy=True, quiet=False)
    if not os.path.exists(output_path):
        raise ValueError("Failed to download video from Drive.")
    return output_path

def download_image(image_url: str) -> str:
    output_path = f"/tmp/{uuid.uuid4()}.jpg"
    response = requests.get(image_url)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(response.content)
    return output_path
