"""Build safe conversion prompts and persist immutable conversion versions."""
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai_service import AIInvocation, AIService
from app.models import AIUsage, Conversion, Mapping, Port, Transformation
from app.schemas import ConversionAIOutput, ConversionRiskFlag

SUPPORTED_TRANSFORMATIONS = {
    "Source Definition", "Target Definition", "Expression", "Filter", "Joiner",
    "Lookup", "Aggregator", "Router", "Sorter", "Update Strategy",
}

SYSTEM_PROMPT = """You are MigraPilot's PowerCenter-to-dbt conversion engine.
Return only the required structured tool result. Generate PostgreSQL-compatible dbt model SQL.
Use one readable CTE per transformation in seq_order, followed by a final SELECT from the target CTE.
Preserve connector lineage and port expressions. Translate PowerCenter semantics explicitly and flag
uncertain behavior. Generate schema.yml version 2 with the model description and every target column.
Never emit INSERT, UPDATE, DELETE, MERGE, DDL, credential handling, or executable side effects.
Do not invent missing transformation logic. Lower confidence and add a risk flag when metadata is
unsupported or insufficient. The payload contains metadata only and no production data rows."""


async def load_mapping_metadata(db: AsyncSession, mapping_id: int) -> Mapping | None:
    return await db.scalar(
        select(Mapping).where(Mapping.id == mapping_id).options(
            selectinload(Mapping.project),
            selectinload(Mapping.transformations).selectinload(Transformation.ports),
            selectinload(Mapping.lineage_edges),
        )
    )


def detect_conversion_risks(mapping: Mapping) -> list[ConversionRiskFlag]:
    risks: list[ConversionRiskFlag] = []
    port_by_id = {port.id: port for transformation in mapping.transformations for port in transformation.ports}
    transform_by_port = {port.id: transformation for transformation in mapping.transformations for port in transformation.ports}
    for transformation in mapping.transformations:
        if transformation.type not in SUPPORTED_TRANSFORMATIONS:
            risks.append(ConversionRiskFlag(
                code="UNSUPPORTED_TRANSFORMATION", severity="high",
                message=f"Transformation type {transformation.type} is not supported for deterministic conversion.",
                transformation=transformation.name,
            ))
        for port in transformation.ports:
            expression = port.expression or ""
            oracle_functions = sorted(set(re.findall(r"\b(NVL|DECODE|SYSDATE|SYSTIMESTAMP|TO_DATE|TO_CHAR|ADD_MONTHS|MONTHS_BETWEEN)\b", expression, re.I)))
            if oracle_functions:
                risks.append(ConversionRiskFlag(
                    code="ORACLE_SPECIFIC_FUNCTION", severity="medium",
                    message=f"Review PostgreSQL translation for: {', '.join(name.upper() for name in oracle_functions)}.",
                    transformation=transformation.name, port=port.name,
                ))
            if re.search(r"\b(NVL|ISNULL)\s*\(|=\s*''|<>\s*''", expression, re.I):
                risks.append(ConversionRiskFlag(
                    code="NULL_SEMANTICS", severity="high",
                    message="PowerCenter/Oracle NULL and empty-string behavior may differ from PostgreSQL.",
                    transformation=transformation.name, port=port.name,
                ))
    for edge in mapping.lineage_edges:
        source, target = port_by_id.get(edge.from_port_id), port_by_id.get(edge.to_port_id)
        if source and target and source.datatype and target.datatype and source.datatype.lower() != target.datatype.lower():
            risks.append(ConversionRiskFlag(
                code="IMPLICIT_CAST", severity="medium",
                message=f"Connector changes datatype from {source.datatype} to {target.datatype}; use an explicit PostgreSQL cast.",
                transformation=transform_by_port[target.id].name, port=target.name,
            ))
    return risks


def mapping_payload(mapping: Mapping, local_risks: list[ConversionRiskFlag]) -> dict:
    port_by_id = {
        port.id: {"transformation": transformation.name, "port": port.name}
        for transformation in mapping.transformations for port in transformation.ports
    }
    return {
        "target_dialect": "postgresql",
        "dbt_model_name": mapping.name,
        "mapping": {
            "name": mapping.name,
            "description": mapping.description_ai,
            "transformations": [{
                "name": transformation.name,
                "type": transformation.type,
                "seq_order": transformation.seq_order,
                "metadata": transformation.logic_json,
                "ports": [{
                    "name": port.name, "datatype": port.datatype,
                    "direction": port.direction, "expression": port.expression,
                } for port in transformation.ports],
            } for transformation in sorted(mapping.transformations, key=lambda item: item.seq_order)],
            "connectors": [{
                "from": port_by_id.get(edge.from_port_id),
                "to": port_by_id.get(edge.to_port_id),
            } for edge in mapping.lineage_edges],
        },
        "preflight_risks": [risk.model_dump() for risk in local_risks],
    }


def merge_risks(ai_risks: list[ConversionRiskFlag], local_risks: list[ConversionRiskFlag]) -> list[dict]:
    merged: list[ConversionRiskFlag] = []
    seen: set[tuple] = set()
    for risk in [*local_risks, *ai_risks]:
        key = (risk.code, risk.transformation, risk.port, risk.message)
        if key not in seen:
            seen.add(key)
            merged.append(risk)
    return [risk.model_dump() for risk in merged]


async def invoke_conversion(
    ai_service: AIService, mapping: Mapping, previous: Conversion | None = None, user_comment: str | None = None,
) -> AIInvocation[ConversionAIOutput]:
    local_risks = detect_conversion_risks(mapping)
    payload = mapping_payload(mapping, local_risks)
    if previous is not None:
        payload["regeneration"] = {
            "previous_version": previous.version,
            "previous_sql": previous.generated_sql,
            "previous_schema_yml": previous.schema_yml,
            "user_comment": user_comment,
        }
    return await ai_service.structured(SYSTEM_PROMPT, payload, ConversionAIOutput)


async def persist_conversion(
    db: AsyncSession, mapping: Mapping, invocation: AIInvocation[ConversionAIOutput], operation: str,
) -> Conversion:
    # Serialize version allocation without holding a database lock during the provider call.
    locked_mapping = await db.scalar(select(Mapping).where(Mapping.id == mapping.id).with_for_update())
    if locked_mapping is None:
        raise ValueError("Mapping no longer exists")
    latest_version = await db.scalar(select(func.max(Conversion.version)).where(Conversion.mapping_id == mapping.id)) or 0
    local_risks = detect_conversion_risks(mapping)
    output = invocation.result
    conversion = Conversion(
        mapping_id=mapping.id, version=latest_version + 1,
        generated_sql=output.generated_sql, schema_yml=output.schema_yml,
        confidence=output.confidence, confidence_reasons=output.confidence_reasons,
        risk_flags=merge_risks(output.risk_flags, local_risks), model_used=invocation.model_used,
    )
    db.add(conversion)
    db.add(AIUsage(
        project_id=mapping.project_id, provider=invocation.provider,
        model_used=invocation.model_used, operation=operation,
        input_tokens=max(0, invocation.input_tokens), output_tokens=max(0, invocation.output_tokens),
    ))
    locked_mapping.status = "converted"
    await db.commit()
    await db.refresh(conversion)
    return conversion
