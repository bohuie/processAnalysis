import os
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from src.utils.connect_groq import connect_groq              # LLM client (Groq)
from src.utils.ollama_offline import connect_ollama_offline  # LLM client (Offline Ollama)

load_dotenv()

# === LLM ALIAS (Check AI_MODE toggle) ================================
AI_MODE = os.getenv("AI_MODE", "online").lower()
if AI_MODE == "offline":
    ask_llm = connect_ollama_offline
else:
    ask_llm = connect_groq


def classify_constructiveness(
    main_comment: str,
    inline_bodies: list[str] | None = None,
    other_review_bodies: list[str] | None = None,
) -> str:
    """
    Classify overall review behaviour (for a single reviewer on a PR) as
    'constructive' or 'non_constructive', given:

      - main_comment: the primary review message to classify
      - inline_bodies: inline comments by the same reviewer on the same PR
      - other_review_bodies: other (non-APPROVED, context) review bodies
    """
    inline_bodies = [str(b).strip() for b in (inline_bodies or []) if str(b).strip()]
    other_review_bodies = [str(b).strip() for b in (other_review_bodies or []) if str(b).strip()]

    context_sections = ""
    if inline_bodies:
        joined_inline = "\n\n--- inline comment ---\n\n".join(inline_bodies)
        context_sections += (
            "\n\nINLINE COMMENTS BY THE SAME REVIEWER ON THIS PR:\n"
            f"{joined_inline}"
        )
    if other_review_bodies:
        joined_reviews = "\n\n--- other review ---\n\n".join(other_review_bodies)
        context_sections += (
            "\n\nOTHER REVIEW MESSAGES BY THE SAME REVIEWER ON THIS PR "
            "(for context only):\n"
            f"{joined_reviews}"
        )

    prompt = f"""
You are analyzing a GitHub pull request review.

You receive:
- One PRIMARY review message (the one to classify).
- Optional INLINE comments by the same reviewer on the same PR.
- Optional OTHER REVIEW messages by the same reviewer on the same PR.

Inline comments that give specific, actionable feedback on code
(e.g. pointing to issues, suggesting alternatives) are strong evidence
that the overall review behaviour is CONSTRUCTIVE.

Use these criteria:

CONSTRUCTIVE IF the overall review behaviour:
- Addresses functional defects or potential bugs
- Points out validation issues or alternative use cases
- Suggests changes to APIs, resources, or conventions
- Mentions style/naming/indentation/typos in a helpful way
- Requests refactoring or simplification
- OR when the primary review is short but is clearly accompanied by
  substantial inline comments giving concrete suggestions

NON-CONSTRUCTIVE IF:
- It mostly states opinions as fact (e.g., "This should be stateless")
  without explanation
- Is sarcastic/judgmental ("Did you even test this?")
- Only says things like "Looks good" with no substantive inline feedback
- Piggybacks on a previous comment without adding insight

PRIMARY REVIEW:
\"\"\"{main_comment}\"\"\"
{context_sections}

Classify the overall review behaviour as 'constructive'
or 'non_constructive' and briefly explain your reasoning.
Respond format: label | reasoning
""".strip()

    return ask_llm(prompt, max_tokens=200)


def label_pr_descriptions(prs_df):
    desc_col = "pr_description" if "pr_description" in prs_df.columns else "body"
    labels = []
    for _, pr in prs_df.iterrows():
        description = str(pr.get(desc_col, "")).strip()
        word_count = len(description.split())
        if word_count >= 10:
            event = "pr_description_clear"
        else:
            event = "pr_description_unclear"
        labels.append({
            "pr_id": pr.get("pr_id", np.nan),
            "pr_author": pr.get("pr_author", "unknown"),
            "created_at": pr.get("created_at", pd.NaT),
            "event": event,
        })
    return pd.DataFrame(labels)