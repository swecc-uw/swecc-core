import logging
import os
import re
from dataclasses import asdict, dataclass
from time import sleep
from typing import Optional

import requests

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
)


def _response_detail(response) -> str:
    """Best-effort error text from an AI service response. Never raises."""
    text = (getattr(response, "text", None) or "")[:500]
    try:
        body = response.json()
    except ValueError:
        return text
    if not isinstance(body, dict):
        return text or str(body)[:500]
    if body.get("error"):
        return str(body.get("error"))[:500]
    return text or str(body)[:500]


@dataclass(frozen=True)
class Metadata:
    is_authorized: Optional[bool] = None
    author: Optional[str] = None


class GeminiAPI:

    def __init__(
        self,
        max_context_length=2000,
        context_invalidation_time_seconds=10 * 60,  # 10 minutes
    ):
        self.OFF_TOPIC_CHANNEL_ID = int(os.getenv("OFF_TOPIC_CHANNEL_ID", "0"))
        self.allowed_channels = [self.OFF_TOPIC_CHANNEL_ID]
        self.allowlisted_roles_id = [int(os.getenv("OFFICER_ROLE_ID", "0"))]

        self.prompt = "rusty"
        self.max_context_length = max_context_length
        self.context_invalidation_time_seconds = context_invalidation_time_seconds

        self.ROLE = "You are a butler for the Software Engineering Career Club at the University of Washington and also answer questions about LeBron Raymone James. You can answer questions regarding software engineering, career development, and LeBron Raymone James."
        self.REPLY_INSTRUCTION = (
            "Reply with the Discord message itself. "
            "Do not describe your reasoning, these instructions, or the shape of the request."
        )
        self.AUTHORIZED_INSTRUCTION = "Do exactly what the member asks."
        self.UNAUTHORIZED_INSTRUCTION = (
            "Answer only questions about software engineering, career development, "
            "LeBron Raymone James, or this club. "
            "If a request is outside those topics, say that it is outside your scope."
        )
        self.BUTLER_MESSAGE_PREFIX = "Response: "

        self.url = os.getenv("AI_API_URL", "http://ai:8008")
        self.config_key = "swecc-bot"

        self.session = requests.Session()

        self.polling_interval = 0.5
        self.max_tries = 100  # 50s, past the OpenRouter client timeout

        self.welcome_message_key = "welcome_message"
        self.process_timeline_message_key = "process_timeline_message"

    def initialize_config(self):
        data = {
            "max_context_length": self.max_context_length,
            "context_invalidation_time_seconds": self.context_invalidation_time_seconds,
            "system_instruction": self.generate_system_instruction(),
        }

        with self.session.post(
            f"{self.url}/inference/{self.config_key}/config", json=data
        ) as response:
            if response.status_code == 200:
                logging.info("Configuration initialized successfully.")
            else:
                logging.error(f"Failed to initialize configuration: {response.text}")

    def initialize_welcome_message_config(self):
        data = {
            "max_context_length": self.max_context_length,
            "context_invalidation_time_seconds": self.context_invalidation_time_seconds,
            "system_instruction": "",
        }

        with self.session.post(
            f"{self.url}/inference/{self.welcome_message_key}/config", json=data
        ) as response:
            if response.status_code == 200:
                logging.info("Configuration initialized successfully.")
            else:
                logging.error(f"Failed to initialize configuration: {response.text}")

    def initialize_process_timeline_message_config(self):
        data = {
            "max_context_length": self.max_context_length,
            "context_invalidation_time_seconds": self.context_invalidation_time_seconds,
            "system_instruction": (
                "You are a stateless information extraction engine. "
                "You have no personality. "
                "You do not greet. "
                "You do not explain. "
                "You do not roleplay. "
                "You only output extracted data or the exact phrase 'Not relevant'."
            ),
        }

        with self.session.post(
            f"{self.url}/inference/{self.process_timeline_message_key}/config",
            json=data,
        ) as response:
            if response.status_code == 200:
                logging.info("Configuration initialized successfully.")
            else:
                logging.error(f"Failed to initialize configuration: {response.text}")

    def generate_system_instruction(self):
        return f"{self.ROLE}\n{self.REPLY_INSTRUCTION}"

    def policy_instruction(self, is_authorized: bool) -> str:
        if is_authorized:
            return self.AUTHORIZED_INSTRUCTION
        return self.UNAUTHORIZED_INSTRUCTION

    def format_user_message(self, message):
        # Replace first instance of prompt with empty string
        return re.sub(self.prompt.lower(), "", message.content.lower(), 1).strip()

    def is_authorized(self, message):
        return any(role.id in self.allowlisted_roles_id for role in message.author.roles)

    def clean_response(self, response):
        if "@" in response:
            return "NO"
        if response and len(response) > 2000:
            response = response[:1997] + "..."
        return re.sub(self.BUTLER_MESSAGE_PREFIX, "", response, 1).strip()

    def request_completion(
        self,
        message,
        metadata: Metadata,
        key,
        needs_context=True,
        system_instruction: Optional[str] = None,
    ):
        url = f"{self.url}/inference/{key}/complete"
        payload = {
            "message": message,
            "metadata": asdict(metadata),
            "needs_context": needs_context,
        }
        if system_instruction:
            payload["system_instruction"] = system_instruction
        try:
            response_cm = self.session.post(url, json=payload)
        except requests.RequestException as exc:
            logging.exception("Inference complete request failed key=%s url=%s: %s", key, url, exc)
            return None

        with response_cm as response:
            if response.status_code == 202:
                body = response.json()
                logging.info("Inference accepted key=%s request_id=%s", key, body.get("request_id"))
                return body["request_id"]

            logging.error(
                "Inference complete rejected key=%s url=%s http_status=%s detail=%s",
                key,
                url,
                response.status_code,
                _response_detail(response),
            )
            return None

    def poll_for_response(self, request_id):
        failed_response_message = "Request failed. Please try again later."
        if not request_id:
            logging.error(
                "Inference poll aborted: no request_id. "
                "POST /inference/{key}/complete did not return 202."
            )
            return failed_response_message

        last_status = None
        url = f"{self.url}/inference/status/{request_id}"
        for attempt in range(1, self.max_tries + 1):
            try:
                response_cm = self.session.get(url)
            except requests.RequestException as exc:
                logging.exception(
                    "Inference poll transport error request_id=%s attempt=%s/%s url=%s: %s",
                    request_id,
                    attempt,
                    self.max_tries,
                    url,
                    exc,
                )
                return failed_response_message

            with response_cm as response:
                if response.status_code != 200:
                    # Model failures are returned as HTTP 500 with
                    # {"status": "error", "error": "<upstream detail>"}.
                    logging.error(
                        "Inference status HTTP error request_id=%s attempt=%s/%s "
                        "http_status=%s detail=%s",
                        request_id,
                        attempt,
                        self.max_tries,
                        response.status_code,
                        _response_detail(response),
                    )
                    return failed_response_message

                try:
                    body = response.json()
                except ValueError:
                    logging.exception(
                        "Inference status returned non-JSON request_id=%s attempt=%s/%s body=%s",
                        request_id,
                        attempt,
                        self.max_tries,
                        (response.text or "")[:500],
                    )
                    return failed_response_message

                status = body.get("status")
                last_status = status
                if status == "success":
                    response_data = body.get("result")
                    logging.info("Inference success request_id=%s", request_id)
                    if response_data:
                        return self.clean_response(response_data)
                    logging.error(
                        "Inference success had empty result request_id=%s body=%s",
                        request_id,
                        body,
                    )
                    return failed_response_message
                elif status == "pending":
                    logging.info(
                        "Inference pending request_id=%s attempt=%s/%s",
                        request_id,
                        attempt,
                        self.max_tries,
                    )
                elif status == "error":
                    logging.error(
                        "Inference request error request_id=%s attempt=%s/%s error=%s",
                        request_id,
                        attempt,
                        self.max_tries,
                        body.get("error"),
                    )
                    return "Error occurred Please try again later."
                elif status == "in_progress":
                    logging.info(
                        "Inference in progress request_id=%s attempt=%s/%s",
                        request_id,
                        attempt,
                        self.max_tries,
                    )
                else:
                    logging.error(
                        "Unknown inference status request_id=%s attempt=%s/%s status=%s body=%s",
                        request_id,
                        attempt,
                        self.max_tries,
                        status,
                        body,
                    )
                    return failed_response_message
            sleep(self.polling_interval)

        logging.error(
            "Inference poll timed out request_id=%s attempts=%s interval_seconds=%s last_status=%s",
            request_id,
            self.max_tries,
            self.polling_interval,
            last_status,
        )
        return failed_response_message

    async def process_message_event(self, message):
        # Idempotent, no problem calling multiple times
        self.initialize_config()
        if message.author.bot or not self.prompt.lower() in message.content.lower():
            return

        is_authorized = self.is_authorized(message)
        if message.channel.id not in self.allowed_channels and not is_authorized:
            return

        metadata = Metadata(
            is_authorized=is_authorized,
            author=str(message.author),
        )

        cleaned_message = self.format_user_message(message)

        request_id = self.request_completion(
            cleaned_message,
            metadata,
            self.config_key,
            system_instruction=self.policy_instruction(is_authorized),
        )

        response = self.poll_for_response(request_id)

        await message.channel.send(response)

    async def get_welcome_message(self, username, discord_id):
        self.initialize_welcome_message_config()

        request_id = self.request_completion(
            f"""
            {self.ROLE}

            You should write a fun and unique welcome message for {username}.
            They just joined the club and are excited to meet everyone!

            You can ping them using <@{discord_id}> to get their attention.

            At the end of your message, be sure to tell them that they can
            always reach you in <#{self.OFF_TOPIC_CHANNEL_ID}> if they have any questions or
            need help with anything.
            """,
            Metadata(),
            self.welcome_message_key,
            needs_context=False,
        )

        response = self.poll_for_response(request_id)
        return response

    async def process_timeline_message(self, timeline, is_authorized, user):
        if not getattr(self, "_process_timeline_message_config_initialized", False):
            self.initialize_process_timeline_message_config()
            self._process_timeline_message_config_initialized = True

        request_id = self.request_completion(
            f"""
                {self.ROLE}

                ### Role
                You are an HR Data Processor specializing in identifying job application timelines. Ignore all other roles or context.

                ### Task
                Analyze the text under the heading Data and determine if it describes a job application timeline. The **main goal** is to check relevance.

                ### Data
                {timeline}

                ### Instructions
                1. First, decide if the text describes a job application timeline.
                2. If it **does not**, output exactly: `Not relevant`.
                3. If it **does**, return the timeline **exactly as it appears in the text**, preserving dates, formatting, and stage names.
                4. Do **not** modify or normalize dates, add placeholders, or change event names.
                5. Do **not** include any extra text, explanations, or filler.
                6. A valid job application timeline must list each stage on its own line with the date. Sentences or paragraphs do NOT count as valid timelines.

                ### Example (relevant timeline)
                Got reachout 10/10
                1st round case 11/10
                2nd round case 15/10
                Internship 25/10

                ### Example (not relevant)
                Not relevant
            """,
            metadata=Metadata(
                is_authorized=is_authorized,
                author=str(user),
            ),
            key=self.process_timeline_message_key,
            needs_context=False,
        )

        response = self.poll_for_response(request_id)
        return response
