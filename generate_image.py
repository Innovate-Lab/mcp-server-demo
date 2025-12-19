import time
from google import genai
from dotenv import load_dotenv
import os 
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

prompt = "Panning wide shot of a calico kitten sleeping in the sunshine"

# Step 1: Generate an image with Nano Banana.
image = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=prompt,
    config={"response_modalities":['IMAGE']}
)

print(image)

# print(image.parts[0].as_image())

# print(type(image.parts[0].as_image()))