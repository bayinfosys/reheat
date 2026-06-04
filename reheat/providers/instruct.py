import json
import logging
import requests
from abc import ABC, abstractmethod
from reheat.state.user import UserState

logger = logging.getLogger(__name__)


class InstructError(Exception):
    """Raised when an instruct provider call fails."""


class InstructProvider(ABC):

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 150) -> str:
        """Send a prompt and return the response text."""
        ...


class OpenAICompatibleProvider(InstructProvider):
    """
    Covers Marigold, OpenAI, and any other OpenAI-compatible endpoint.
    """

    def __init__(self, api_key: str, endpoint: str, model: str) -> None:
        self._api_key = api_key
        self._endpoint = endpoint.rstrip("/")
        self._model = model

    def complete(self, prompt: str, max_tokens: int = 150) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        try:
            response = requests.post(
                f"{self._endpoint}/v1/chat/completions",
                headers=headers,
                json=body,
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise InstructError(f"instruct API request failed: {e}") from e

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise InstructError(f"unexpected API response shape: {e}") from e


class ConfigError(Exception):
    """Raised when instruct provider configuration is invalid."""


def get_instruct_provider(user: UserState) -> InstructProvider:
    """
    Construct the configured InstructProvider from UserState.
    Prefers Marigold endpoint if set, falls back to OpenAI.
    Raises ConfigError if neither is configured.
    """
    if user.marigold_api_key and user.marigold_endpoint:
        logger.debug("using Marigold instruct provider")
        return OpenAICompatibleProvider(
            api_key=user.marigold_api_key,
            endpoint=user.marigold_endpoint,
            model=user.summary_model or "default",
        )

    if user.openai_api_key:
        logger.debug("using OpenAI instruct provider")
        return OpenAICompatibleProvider(
            api_key=user.openai_api_key,
            endpoint="https://api.openai.com",
            model=user.summary_model or "gpt-4o-mini",
        )

    raise ConfigError(
        "no instruct provider configured. Set either:\n"
        "  reheat config set --key marigold_api_key --value <key>\n"
        "  reheat config set --key marigold_endpoint --value <url>\n"
        "or:\n"
        "  reheat config set --key openai_api_key --value <key>"
    )
