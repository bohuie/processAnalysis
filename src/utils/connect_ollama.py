def ask_ollama(prompt: str) -> str:
    """Send a text classification prompt to Ollama running locally."""
    while True:
        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a concise text classifier."},
                    {"role": "user", "content": prompt}
                ],
                options={
                    "temperature": 0.2,
                    "num_predict": 200,
                }
            )
            return response['message']['content'].strip()
        except Exception as e:
            err = str(e)
            print(f"Ollama error: {err} — retrying in 3 seconds...")
            time.sleep(3)