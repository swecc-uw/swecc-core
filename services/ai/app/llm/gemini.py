import os
from google import genai
from google.genai import types
import logging
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)


class Gemini:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Gemini, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.api_key = os.getenv("GEMINI_API_KEY")
            self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")

            if self.api_key is None:
                raise ValueError("GEMINI_API_KEY environment variable not set")

            self.client = genai.Client(api_key=self.api_key)
            self.initialized = True

    async def prompt_model(self, prompt: str, system_instruction: Optional[str] = None):
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=500,
            temperature=0.7,
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            return response.text
        except Exception as e:
            logger.error(f"Error in prompt_model: {e}")

    async def prompt_file(self, bytes: bytes, prompt: str, mime_type: str):
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[
                types.Part.from_bytes(
                    data=bytes,
                    mime_type=mime_type,
                ),
                prompt,
            ],
        )
        return response.text

    async def prompt_files(self, files: dict[(str, str), bytes], prompt: str):
        """
        files: dict[(str, str), bytes] where key is (filename, mime_type)
        prompt: str, the prompt to give to the model
        returns: Dictionary containing the filename and the corresponding response
        """
        results = await asyncio.gather(
            self.prompt_file(file_bytes, prompt, mime_type)
            for (_, mime_type), file_bytes in files.items()
        )
        return dict(zip(files.keys(), results))
