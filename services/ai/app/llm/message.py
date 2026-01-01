from dataclasses import dataclass
from datetime import datetime


# Represents a message in any chat history
@dataclass
class Message:
    message: str
    response: str
    timestamp: datetime

    # Any additional metadata the client might want to store
    # In the discord bot, this would be `is_authorized` and `author`
    metadata: dict

    def format_prompt(self):
        prompt = "\n"
        for key, value in self.metadata.items():
            prompt += f"{key}: {value}\n"
        prompt += f"Message: {self.message}\n"
        return prompt

    def __str__(self):
        return f"Prompt: {self.format_prompt()}\nResponse: {self.response}"

    def __repr__(self):
        return f"Prompt: {self.format_prompt()}\nResponse: {self.response}"

    def __len__(self):
        return len(str(self))
