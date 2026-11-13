from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.ai_service import (
    AIProviderAuthenticationError,
    AIProviderQuotaError,
    AIProviderRequestError,
    AIProviderResponseError,
    GeminiProvider,
    gemini_response_schema,
)
from app.schemas import AutopsyAIOutput, ConversionAIOutput


VALID_OUTPUT = {
    "generated_sql": "with source_data as (select 1 as id) select id from source_data",
    "schema_yml": "version: 2\nmodels:\n  - name: converted_model\n    description: Converted model\n",
    "confidence": 90,
    "confidence_reasons": ["All supported metadata was available."],
    "risk_flags": [],
}


class FakeInteractions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class SchemaComplexityRejectingInteractions(FakeInteractions):
    async def create(self, **kwargs):
        self.calls.append(kwargs)
        serialized = str(kwargs["response_format"]["schema"])
        forbidden = ("maxLength", "minLength", "maxItems", "minItems", "maximum", "minimum", "pattern")
        if any(key in serialized for key in forbidden):
            error = RuntimeError("schema has too many serving states")
            error.status_code = 400
            raise error
        return self.response


def client_for(interactions):
    return SimpleNamespace(aio=SimpleNamespace(interactions=interactions))


@pytest.mark.asyncio
async def test_gemini_uses_pydantic_structured_output_and_tracks_tokens():
    response = SimpleNamespace(
        output_text=ConversionAIOutput.model_validate(VALID_OUTPUT).model_dump_json(),
        usage=SimpleNamespace(total_input_tokens=321, total_output_tokens=123),
    )
    interactions = FakeInteractions(response=response)
    provider = GeminiProvider("not-a-real-key", "gemini-3.8-flash", client_for(interactions))

    invocation = await provider.generate("System instruction", {"mapping": {"name": "m_orders"}}, ConversionAIOutput)

    assert invocation.result == ConversionAIOutput.model_validate(VALID_OUTPUT)
    assert (invocation.provider, invocation.model_used) == ("gemini", "gemini-3.8-flash")
    assert (invocation.input_tokens, invocation.output_tokens) == (321, 123)
    call = interactions.calls[0]
    assert call["model"] == "gemini-3.8-flash"
    assert call["response_format"]["type"] == "text"
    assert call["response_format"]["mime_type"] == "application/json"
    assert call["response_format"]["schema"] == gemini_response_schema(ConversionAIOutput)
    assert call["timeout"] > 0
    assert call["store"] is False
    assert call["system_instruction"] == "System instruction"
    assert "m_orders" in call["input"]
    assert "not-a-real-key" not in call["input"]


@pytest.mark.asyncio
async def test_gemini_rejects_malformed_structured_response():
    interactions = FakeInteractions(response=SimpleNamespace(output_text="not json", usage=None))
    provider = GeminiProvider("key", "gemini-3.8-flash", client_for(interactions))
    with pytest.raises(AIProviderResponseError):
        await provider.generate("prompt", {"mapping": {}}, ConversionAIOutput)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected"),
    [(401, AIProviderAuthenticationError), (403, AIProviderAuthenticationError),
     (429, AIProviderQuotaError), (500, AIProviderRequestError)],
)
async def test_gemini_translates_api_failures(code, expected):
    error = RuntimeError("provider detail must not escape")
    error.code = code
    provider = GeminiProvider("key", "gemini-3.8-flash", client_for(FakeInteractions(error=error)))
    with pytest.raises(expected) as raised:
        await provider.generate("prompt", {"mapping": {}}, ConversionAIOutput)
    assert "provider detail" not in str(raised.value)


def test_gemini_provider_schema_removes_serving_state_constraints_but_pydantic_keeps_them():
    provider_schema = gemini_response_schema(ConversionAIOutput)
    serialized = str(provider_schema)
    for unsupported in ("maxLength", "minLength", "maxItems", "minItems", "maximum", "minimum", "pattern"):
        assert unsupported not in serialized

    with pytest.raises(ValidationError):
        ConversionAIOutput.model_validate({**VALID_OUTPUT, "confidence": 101})


@pytest.mark.asyncio
async def test_gemini_conversion_avoids_provider_schema_complexity_rejection():
    response = SimpleNamespace(
        output_text=ConversionAIOutput.model_validate(VALID_OUTPUT).model_dump_json(),
        usage=SimpleNamespace(total_input_tokens=10, total_output_tokens=20),
    )
    interactions = SchemaComplexityRejectingInteractions(response=response)
    provider = GeminiProvider("key", "gemini-3.6-flash", client_for(interactions))

    invocation = await provider.generate("prompt", {"mapping": {}}, ConversionAIOutput)

    assert invocation.result.confidence == 90
    assert len(interactions.calls) == 1


@pytest.mark.asyncio
async def test_gemini_diagnostics_are_safe_and_include_request_id(caplog):
    error = RuntimeError("secret provider response")
    error.status_code = 400
    error.headers = {"x-request-id": "request-safe-123"}
    provider = GeminiProvider("key", "gemini-3.6-flash", client_for(FakeInteractions(error=error)))

    with caplog.at_level("WARNING"), pytest.raises(AIProviderRequestError):
        await provider.generate("raw prompt must stay private", {"password": "private"}, ConversionAIOutput)

    log = caplog.text
    assert "stage=request" in log
    assert "exception=RuntimeError" in log
    assert "status=400" in log
    assert "request_id=request-safe-123" in log
    assert "elapsed_ms=" in log
    assert "secret provider response" not in log
    assert "raw prompt" not in log
    assert "private" not in log


@pytest.mark.asyncio
async def test_gemini_autopsy_uses_reduced_schema_and_validates_locally():
    output = AutopsyAIOutput.model_validate({
        "summary": "A deterministic output mismatch affects NET_AMOUNT.",
        "diagnosis_category": "EXPRESSION_MISMATCH",
        "suspected_root_cause": "The SQL multiplier differs from the mapped expression.",
        "observed_facts": ["Column mismatches were reported."],
        "hypotheses": ["The discount multiplier was translated incorrectly."],
        "affected_transformations": ["EXP_NET"],
        "affected_columns": ["NET_AMOUNT"],
        "supporting_evidence": [{"reference": "metrics.column_mismatches", "observation": "The metric is nonzero."}],
        "confidence": 85,
        "confidence_reasons": ["Mapping and aggregate evidence agree."],
        "suggested_corrective_actions": ["Review the immutable conversion and create a corrected version."],
        "suggested_sql": None,
        "risks_and_limitations": ["No proposed correction has been executed."],
        "recommended_verification_steps": ["Run another isolated shadow comparison."],
        "more_evidence_required": False,
    })
    response = SimpleNamespace(
        output_text=output.model_dump_json(),
        usage=SimpleNamespace(total_input_tokens=40, total_output_tokens=50),
    )
    interactions = SchemaComplexityRejectingInteractions(response=response)
    provider = GeminiProvider("key", "gemini-test", client_for(interactions))
    invocation = await provider.generate("prompt", {"shadow_run": {"id": 1}}, AutopsyAIOutput)
    assert invocation.result == output
    assert invocation.input_tokens == 40 and invocation.output_tokens == 50
    assert interactions.calls[0]["store"] is False


@pytest.mark.asyncio
async def test_gemini_timeout_is_bounded_and_not_retried_at_application_layer():
    interactions = FakeInteractions(error=TimeoutError("private timeout detail"))
    provider = GeminiProvider("key", "gemini-test", client_for(interactions))
    with pytest.raises(AIProviderRequestError):
        await provider.generate("prompt", {"mapping": {}}, ConversionAIOutput)
    assert len(interactions.calls) == 1
    assert interactions.calls[0]["timeout"] > 0
