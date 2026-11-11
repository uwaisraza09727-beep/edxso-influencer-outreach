
import os

from dotenv import load_dotenv
from google import genai


load_dotenv()


DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


class GeminiAPIError(Exception):
    """Raised when a Gemini API request fails."""


class GeminiClient:
    """Client for generating text using the Gemini API."""

    def __init__(self) -> None:
        self.api_key = os.getenv(
            "GEMINI_API_KEY",
            "",
        ).strip()

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is missing. Check your .env file."
            )

        self.model = os.getenv(
            "GEMINI_MODEL",
            DEFAULT_GEMINI_MODEL,
        ).strip()

        if not self.model:
            raise ValueError(
                "GEMINI_MODEL cannot be empty."
            )

        self.client = genai.Client(
            api_key=self.api_key,
        )

    def generate_text(
        self,
        prompt: str,
    ) -> str:
        """Generate text using the configured Gemini model."""

        if not prompt or not prompt.strip():
            raise ValueError(
                "Prompt cannot be empty."
            )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )

        except Exception as exc:
            raise GeminiAPIError(
                f"Gemini API request failed: {exc}"
            ) from exc

        generated_text = response.text

        if not generated_text or not generated_text.strip():
            raise GeminiAPIError(
                "Gemini returned an empty response."
            )

        return generated_text.strip()
