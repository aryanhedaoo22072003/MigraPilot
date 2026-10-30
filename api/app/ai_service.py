"""Provider-agnostic, validated structured AI calls.

Integration points are ready; conversion, autopsy, PII masking and usage
persistence are deliberately NOT presented as working in Phase 1.
"""
from typing import Protocol, TypeVar
from pydantic import BaseModel
from app.core.config import settings

ResultSchema = TypeVar("ResultSchema", bound=BaseModel)


class StructuredAIProvider(Protocol):
    async def generate(self, system_prompt: str, payload: dict, output_type: type[ResultSchema]) -> ResultSchema: ...


class AIServiceNotConfigured(RuntimeError):
    pass


class AnthropicProvider:
    def __init__(self, api_key: str, model: str):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(self, system_prompt: str, payload: dict, output_type: type[ResultSchema]) -> ResultSchema:
        """For schema-only metadata and masked diff aggregates; no raw rows."""
        import json
        message = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(payload)}],
            tools=[{
                "name": "return_structured_result",
                "description": "Return the validated result for the MigraPilot application.",
                "input_schema": output_type.model_json_schema(),
            }],
            tool_choice={"type": "tool", "name": "return_structured_result"},
        )
        for block in message.content:
            if block.type == "tool_use" and block.name == "return_structured_result":
                # TODO(phase 4): log message.usage to ai_usage and mask PII before invoking.
                return output_type.model_validate(block.input)
        raise ValueError("AI did not return the required structured tool output")


class AIService:
    def __init__(self, provider: StructuredAIProvider | None = None):
        self.provider = provider

    @classmethod
    def from_settings(cls) -> "AIService":
        if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
            return cls(AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model))
        return cls()

    async def structured(self, system_prompt: str, payload: dict, output_type: type[ResultSchema]) -> ResultSchema:
        if self.provider is None:
            raise AIServiceNotConfigured("Set ANTHROPIC_API_KEY before running AI conversion and autopsy")
        return await self.provider.generate(system_prompt, payload, output_type)
