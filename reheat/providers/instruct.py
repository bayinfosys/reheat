import logging
import os
from abc import ABC, abstractmethod

from reheat.errors import ConfigError, InstructError
from reheat.state.user import UserState

logger = logging.getLogger(__name__)


class InstructProvider(ABC):
    provider_name: str = ""
    model_name: str = ""

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 150) -> str:
        """Send a prompt and return the response text."""
        ...


class OpenAIProvider(InstructProvider):
    provider_name: str = "openai"

    def __init__(self, model: str) -> None:
        self.model_name = model

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise InstructError("openai package required: pip install reheat[openai]")

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise InstructError("OPENAI_API_KEY is not set")

        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                raise InstructError(
                    f"empty response from OpenAI (finish_reason="
                    f"{response.choices[0].finish_reason!r})"
                )
            return content
        except InstructError:
            raise
        except Exception as e:
            raise InstructError(f"OpenAI API call failed: {e}") from e


class MarigoldProvider(InstructProvider):
    provider_name: str = "marigold"

    def __init__(self, model: str) -> None:
        self.model_name = model

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise InstructError("openai package required: pip install reheat[openai]")

        api_key = os.environ.get("MARIGOLD_API_KEY")
        endpoint = os.environ.get("MARIGOLD_ENDPOINT")

        if not api_key:
            raise InstructError("MARIGOLD_API_KEY is not set")
        if not endpoint:
            raise InstructError("MARIGOLD_ENDPOINT is not set")

        try:
            client = OpenAI(api_key=api_key, base_url=endpoint.rstrip("/") + "/v1")
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                raise InstructError(
                    f"empty response from Marigold (finish_reason="
                    f"{response.choices[0].finish_reason!r})"
                )
            return content
        except InstructError:
            raise
        except Exception as e:
            raise InstructError(f"Marigold API call failed: {e}") from e


class AnthropicProvider(InstructProvider):
    """
    Instruct provider for the Anthropic Messages API.
    Reads ANTHROPIC_API_KEY from the environment at call time.
    Requires: pip install reheat[anthropic]
    """

    provider_name: str = "anthropic"

    def __init__(self, model: str) -> None:
        self.model_name = model

    def complete(self, prompt: str, max_tokens: int = 150) -> str:
        try:
            import anthropic
        except ImportError:
            raise InstructError(
                "anthropic package required: pip install reheat[anthropic]"
            )

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise InstructError("ANTHROPIC_API_KEY is not set")

        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as e:
            raise InstructError(f"Anthropic API call failed: {e}") from e


def get_instruct_provider(user: UserState) -> InstructProvider:
    """
    Select an InstructProvider based on available environment variables.
    Priority: OpenAI > Anthropic > Marigold.
    Raises ConfigError if no provider env vars are set.
    """
    if os.environ.get("OPENAI_API_KEY"):
        logger.info("using OpenAI instruct provider")
        return OpenAIProvider(model=user.instruct_model or "gpt-4o-mini")

    if os.environ.get("ANTHROPIC_API_KEY"):
        logger.info("using Anthropic instruct provider")
        return AnthropicProvider(
            model=user.instruct_model or "claude-haiku-4-5-20251001"
        )

    if os.environ.get("MARIGOLD_API_KEY") and os.environ.get("MARIGOLD_ENDPOINT"):
        logger.info("using Marigold instruct provider")
        return MarigoldProvider(model=user.instruct_model or "default")

    raise ConfigError(
        "no instruct provider configured. Set one of the following env vars\n"
        "(or add them to a .env file in your working directory):\n"
        "  OPENAI_API_KEY\n"
        "  ANTHROPIC_API_KEY\n"
        "  MARIGOLD_API_KEY + MARIGOLD_ENDPOINT"
    )
