import time
from typing import Dict, Any, Optional

import ollama


# Default model + options (you can tweak or override via parameters)
DEFAULT_MODEL_NAME = "llama3.2:3b"
DEFAULT_SYSTEM_PROMPT = "You are a concise text classifier."
DEFAULT_OPTIONS: Dict[str, Any] = {
    "temperature": 0.2,
    "num_predict": 200,
}


def connect_ollama(
    prompt: str,
    model_name: str = DEFAULT_MODEL_NAME,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    options: Optional[Dict[str, Any]] = None,
    retry_delay_seconds: float = 3.0,
) -> str:
    """
    Send a prompt to a local Ollama model and return the response content as a string.

    - Retries indefinitely on exceptions (connection errors, timeouts, etc.)
    - Uses a simple system prompt by default, but both model and system prompt
      are configurable.

    Parameters
    ----------
    prompt : str
        The user/content prompt to send.
    model_name : str, optional
        Name of the Ollama model to use (default: DEFAULT_MODEL_NAME).
    system_prompt : str, optional
        System message to steer the model (default: DEFAULT_SYSTEM_PROMPT).
    options : dict, optional
        Extra Ollama options (temperature, num_predict, etc.).
        If None, uses DEFAULT_OPTIONS.
    retry_delay_seconds : float, optional
        Seconds to wait before retrying after an error.

    Returns
    -------
    str
        The model's response text (message['content'].strip()).
    """
    if options is None:
        options = DEFAULT_OPTIONS

    while True:
        try:
            response = ollama.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                options=options,
            )
            return response["message"]["content"].strip()
        except Exception as e:
            err = str(e)
            print(f"[OLLAMA ERROR] {err} — retrying in {retry_delay_seconds} seconds...")
            time.sleep(retry_delay_seconds)
