"""Provider-agnostic, schema-validated AI calls without prompt or credential logging."""
from dataclasses import dataclass
import logging
from time import monotonic
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from app.core.config import settings

ResultSchema = TypeVar("ResultSchema", bound=BaseModel)
logger = logging.getLogger(__name__)

# Gemini enforces only a subset of JSON Schema and can reject otherwise small
# schemas when validation constraints create too many serving states. MigraPilot
# still applies the complete Pydantic model after receiving the JSON response.
_GEMINI_SCHEMA_APP_ONLY_KEYS = {
    "default",
    "description",
    "examples",
    "format",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "pattern",
    "title",
    "uniqueItems",
}


def gemini_response_schema(output_type: type[BaseModel]) -> dict:
    """Return a low-complexity provider schema; Pydantic remains authoritative."""
    def simplify(value):
        if isinstance(value, dict):
            return {
                key: simplify(item)
                for key, item in value.items()
                if key not in _GEMINI_SCHEMA_APP_ONLY_KEYS
            }
        if isinstance(value, list):
            return [simplify(item) for item in value]
        return value

    return simplify(output_type.model_json_schema())


@dataclass(frozen=True)
class AIInvocation(Generic[ResultSchema]):
    result: ResultSchema
    provider: str
    model_used: str
    input_tokens: int = 0
    output_tokens: int = 0


class StructuredAIProvider(Protocol):
    async def generate(
        self, system_prompt: str, payload: dict, output_type: type[ResultSchema]
    ) -> AIInvocation[ResultSchema]: ...


class AIServiceNotConfigured(RuntimeError):
    pass


class AIProviderResponseError(RuntimeError):
    pass


class AIProviderAuthenticationError(RuntimeError):
    pass


class AIProviderQuotaError(RuntimeError):
    pass


class AIProviderRequestError(RuntimeError):
    pass


class AIProviderTimeoutError(AIProviderRequestError):
    pass


class GeminiProvider:
    def __init__(self, api_key: str, model: str, client=None):
        if client is None:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(
                        attempts=max(0, settings.ai_provider_max_retries),
                        initial_delay=0.5,
                        max_delay=2.0,
                        http_status_codes=[408, 500, 502, 503, 504],
                    ),
                ),
            )
        self.client = client
        self.model = model

    @staticmethod
    def _request_error(exc: Exception) -> RuntimeError:
        """Translate SDK failures without leaking provider payloads or credentials."""
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = None
        if code in {401, 403}:
            return AIProviderAuthenticationError("Gemini credentials were rejected")
        if code == 429:
            return AIProviderQuotaError("Gemini quota was exhausted")
        if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
            return AIProviderTimeoutError("Gemini request timed out")
        return AIProviderRequestError("Gemini request failed")

    @staticmethod
    def _diagnostic(exc: Exception) -> tuple[int | None, str | None]:
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        headers = getattr(exc, "headers", None)
        request_id = None
        if headers is not None:
            for key in ("x-request-id", "request-id", "x-goog-request-id"):
                request_id = headers.get(key)
                if request_id:
                    break
        try:
            status = int(status) if status is not None else None
        except (TypeError, ValueError):
            status = None
        return status, request_id

    @classmethod
    def _log_failure(cls, stage: str, started: float, exc: Exception) -> None:
        status, request_id = cls._diagnostic(exc)
        logger.warning(
            "ai_provider_failure provider=gemini stage=%s exception=%s status=%s "
            "elapsed_ms=%d request_id=%s",
            stage,
            type(exc).__name__,
            status,
            int((monotonic() - started) * 1000),
            request_id or "unavailable",
        )

    async def generate(
        self, system_prompt: str, payload: dict, output_type: type[ResultSchema]
    ) -> AIInvocation[ResultSchema]:
        """Send metadata-only JSON and require Gemini's structured JSON response."""
        import json

        started = monotonic()
        try:
            response = await self.client.aio.interactions.create(
                model=self.model,
                input=json.dumps(payload, separators=(",", ":")),
                system_instruction=system_prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": gemini_response_schema(output_type),
                },
                generation_config={"max_output_tokens": settings.ai_max_output_tokens},
                store=False,
                timeout=settings.ai_provider_timeout_seconds,
            )
        except Exception as exc:
            self._log_failure("request", started, exc)
            raise self._request_error(exc) from exc

        try:
            text = getattr(response, "output_text", None)
            if not text:
                raise ValueError("empty structured response")
            result = output_type.model_validate_json(text)
        except Exception as exc:
            self._log_failure("response_validation", started, exc)
            raise AIProviderResponseError("Gemini returned invalid structured JSON") from exc

        usage = getattr(response, "usage", None)
        return AIInvocation(
            result=result,
            provider="gemini",
            model_used=self.model,
            input_tokens=getattr(usage, "total_input_tokens", 0) or 0,
            output_tokens=getattr(usage, "total_output_tokens", 0) or 0,
        )

    async def aclose(self) -> None:
        await self.client.aio.aclose()


class AnthropicProvider:
    def __init__(self, api_key: str, model: str):
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(
        self, system_prompt: str, payload: dict, output_type: type[ResultSchema]
    ) -> AIInvocation[ResultSchema]:
        """Send mapping metadata only. Callers must never include rows or secrets."""
        import json

        message = await self.client.messages.create(
            model=self.model,
            max_tokens=settings.ai_max_output_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(payload, separators=(",", ":"))}],
            tools=[{
                "name": "return_structured_result",
                "description": "Return the validated MigraPilot conversion result.",
                "input_schema": output_type.model_json_schema(),
            }],
            tool_choice={"type": "tool", "name": "return_structured_result"},
        )
        for block in message.content:
            if block.type == "tool_use" and block.name == "return_structured_result":
                return AIInvocation(
                    result=output_type.model_validate(block.input),
                    provider="anthropic",
                    model_used=getattr(message, "model", self.model),
                    input_tokens=getattr(message.usage, "input_tokens", 0),
                    output_tokens=getattr(message.usage, "output_tokens", 0),
                )
        raise AIProviderResponseError("AI provider did not return the required structured tool output")

    async def aclose(self) -> None:
        await self.client.close()


class AIService:
    def __init__(self, provider: StructuredAIProvider | None = None):
        self.provider = provider

    @classmethod
    def from_settings(cls) -> "AIService":
        provider = settings.ai_provider.strip().lower()
        if provider == "gemini" and settings.gemini_api_key:
            return cls(GeminiProvider(settings.gemini_api_key, settings.gemini_model))
        if provider == "anthropic" and settings.anthropic_api_key:
            return cls(AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model))
        return cls()

    async def structured(
        self, system_prompt: str, payload: dict, output_type: type[ResultSchema]
    ) -> AIInvocation[ResultSchema]:
        if self.provider is None:
            provider = settings.ai_provider.strip().lower()
            if provider == "gemini":
                message = "AI conversion is not configured; set GEMINI_API_KEY on the API service"
            elif provider == "anthropic":
                message = "AI conversion is not configured; set ANTHROPIC_API_KEY on the API service"
            else:
                message = f"AI conversion is not configured; unsupported AI_PROVIDER '{provider}'"
            raise AIServiceNotConfigured(message)
        return await self.provider.generate(system_prompt, payload, output_type)

    async def aclose(self) -> None:
        close = getattr(self.provider, "aclose", None)
        if close is not None:
            await close()


def get_ai_service() -> AIService:
    return AIService.from_settings()
