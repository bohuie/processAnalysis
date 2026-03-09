import os
import re
from dotenv import load_dotenv

from src.utils.connect_groq import connect_groq
from src.utils.ollama_offline import connect_ollama_offline

load_dotenv()

AI_MODE = os.getenv("AI_MODE", "online").lower()
ask_llm = connect_ollama_offline if AI_MODE == "offline" else connect_groq


_WORD_ONLY = re.compile(r"[^a-z]+")


def classify_commit_message(msg: str) -> tuple[str, str]:
    """
    Returns: (event_label, llm_raw_output)

    The label is one of:
      - commit_informative
      - commit_uninformative
    """
    msg = str(msg).strip()
    if msg == "" or msg.lower() == "nan":
        return "commit_uninformative", ""

    prompt = f"""
Determine if the following commit message contains both a verb and a noun.
If it does, respond ONLY with 'informative'. If not, respond ONLY with 'uninformative'.

Commit message: \"\"\"{msg}\"\"\"
""".strip()

    llm_output = ask_llm(prompt, max_tokens=20)
    raw = (llm_output or "").strip().lower()

    # normalize to letters only (defensive against punctuation/newlines)
    normalized = _WORD_ONLY.sub("", raw)

    if normalized.startswith("uninformative"):
        return "commit_uninformative", llm_output
    if normalized.startswith("informative"):
        return "commit_informative", llm_output

    # fallback heuristic
    if "uninformative" in raw:
        return "commit_uninformative", llm_output
    if "informative" in raw:
        return "commit_informative", llm_output

    # if model doesn't follow instructions, default conservative
    return "commit_uninformative", llm_output