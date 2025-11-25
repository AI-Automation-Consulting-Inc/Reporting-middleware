import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv is optional—only used if installed
    pass

key = os.getenv("OPENAI_API_KEY")
if not key:
    print("OPENAI_API_KEY not set. Create a `.env` file or set the env var.")
else:
    print("OPENAI_API_KEY is set. (showing first 8 chars):", key[:8])

# Optional: quick OpenAI SDK configuration check (won't call the API)
try:
    import openai
    if key:
        openai.api_key = key
        print("OpenAI SDK configured (no API call made).")
except Exception:
    pass
