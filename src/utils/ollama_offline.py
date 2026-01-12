import time
from typing import Dict, Any, Optional

try:
    import ollama
except ImportError:
    print("[WARNING] ollama package not installed. Install with: pip install ollama")
    ollama = None


# Default model + options
DEFAULT_MODEL_NAME = "llama3.2:3b"
DEFAULT_SYSTEM_PROMPT = "You are a concise text classifier."
DEFAULT_OPTIONS: Dict[str, Any] = {
    "temperature": 0.2,
    "num_predict": 200,
}


def connect_ollama_offline(
    prompt: str,
    model_name: str = DEFAULT_MODEL_NAME,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    options: Optional[Dict[str, Any]] = None,
    max_tokens: Optional[int] = None,
    retry_delay_seconds: float = 3.0,
    max_retries: int = None,
) -> str:
    if ollama is None:
        raise RuntimeError(
            "[ERROR] ollama package is not installed. "
            "Install with: pip install ollama\n"
            "Or: pip install -r requirements.txt"
        )
    
    if options is None:
        options = dict(DEFAULT_OPTIONS)
    
    if max_tokens is not None:
        # Map max_tokens -> Ollama num_predict
        options["num_predict"] = int(max_tokens)
    
    retry_count = 0
    
    while True:
        try:
            print(f"[OLLAMA] Connecting to local Ollama instance...")
            print(f"[OLLAMA] Model: {model_name}")
            
            response = ollama.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                options=options,
            )
            
            result = response["message"]["content"].strip()
            print(f"[OLLAMA] Response received ({len(result)} chars)")
            return result
            
        except Exception as e:
            retry_count += 1
            err = str(e)
            
            # Check if we've exceeded max retries
            if max_retries is not None and retry_count > max_retries:
                raise ConnectionError(
                    f"[OLLAMA ERROR] Failed to connect after {max_retries} retries: {err}\n"
                    f"Make sure Ollama is running locally with: ollama serve"
                )
            
            # Print retry message
            if max_retries is not None:
                print(f"[OLLAMA ERROR] Attempt {retry_count}/{max_retries}: {err}")
            else:
                print(f"[OLLAMA ERROR] Attempt {retry_count}: {err}")
            
            print(f"[OLLAMA] Retrying in {retry_delay_seconds} seconds...")
            print(f"[OLLAMA] Ensure Ollama is running with: ollama serve")
            
            time.sleep(retry_delay_seconds)


def check_ollama_connection(model_name: str = DEFAULT_MODEL_NAME) -> bool:
    if ollama is None:
        print("[WARNING] ollama package not installed")
        return False
    
    try:
        print(f"[OLLAMA] Checking connection to local Ollama...")
        # Try a simple ping with a very short prompt
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": "ok"}],
            options={"num_predict": 10},
        )
        print(f"[OLLAMA] Connection successful! Model '{model_name}' is available.")
        return True
    except Exception as e:
        print(f"[OLLAMA] Connection check failed: {e}")
        print(f"[OLLAMA] Make sure Ollama is running with: ollama serve")
        return False


def list_available_models() -> list:
    if ollama is None:
        print("[WARNING] ollama package not installed")
        return []
    
    try:
        print("[OLLAMA] Fetching available models from local Ollama...")
        response = ollama.list()
        models = [model["name"] for model in response.get("models", [])]
        print(f"[OLLAMA] Found {len(models)} model(s): {models}")
        return models
    except Exception as e:
        print(f"[OLLAMA] Failed to list models: {e}")
        return []
