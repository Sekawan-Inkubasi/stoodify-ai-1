from llm import load_env, get_api_key
from google import genai

load_env()
client = genai.Client(api_key=get_api_key())

for m in client.models.list():
    aksi = getattr(m, "supported_actions", None) or []
    if "generateContent" in aksi:
        print(m.name.replace("models/", ""))