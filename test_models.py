import time
from google import genai
from google.genai import types

models = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
]

client = genai.Client()
cfg = types.GenerateContentConfig(http_options=types.HttpOptions(timeout=20000))

for m in models:
    t = time.time()
    try:
        r = client.models.generate_content(
            model=m, contents="Reply with the single word: ok", config=cfg)
        print(f"OK    {m:30s} {time.time()-t:5.1f}s  {r.text.strip()[:20]!r}")
    except Exception as e:
        print(f"FAIL  {m:30s} {time.time()-t:5.1f}s  {str(e)[:70]}")