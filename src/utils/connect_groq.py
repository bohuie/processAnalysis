import os
import time
from typing import Optional
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL_NAME", "llama-3.1-8b-instant")

_client = None


def _get_groq_client() -> Groq:
    """Create/reuse a single Groq client instance."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set in environment.")
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def connect_groq(
    prompt: str,
    max_tokens: int = 200,
    model: Optional[str] = None,
    system_message: str = "You are a precise text classifier and explainer.",
) -> str:
    """
    Call Groq chat completion and return the response text.
    Handles rate limits and transient errors with retries.
    """
    # Get the Groq client
    client = _get_groq_client()
    model_name = model or DEFAULT_GROQ_MODEL

    while True:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                print("⚠️ Groq rate-limit — sleeping 5s...")
                time.sleep(5)
                continue
            print(f"⚠️ Groq transient error: {err} — retrying in 3s...")
            time.sleep(3)