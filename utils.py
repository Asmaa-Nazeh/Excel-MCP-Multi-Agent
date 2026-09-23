"""
utils.py
--------
Small shared helpers used across agents. Kept separate from config.py /
prompts.py so each stays focused on a single responsibility.
"""

import json
import re


def strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers some LLMs add
    around structured output, so the remainder can be parsed as JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```$", "", text.strip())
    return text.strip()


def safe_json_loads(text: str):
    """Parse JSON from raw LLM text, tolerating code-fence wrapping."""
    cleaned = strip_code_fences(text)
    return json.loads(cleaned)
