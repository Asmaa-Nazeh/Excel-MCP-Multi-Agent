import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "cohere/north-mini-code:free"
)

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "uploads"
)

os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_llm_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. "
            "Add your OpenRouter API key to the .env file."
        )

    return OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL
    )


def get_model_name() -> str:
    return OPENROUTER_MODEL