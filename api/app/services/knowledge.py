"""Deterministic, project-scoped verified failure knowledge lifecycle."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Autopsy, Conversion, KnowledgeCandidate, KnowledgeEvent, Mapping, ShadowRun,
)
from app.schemas import AutopsyAIOutput
from app.services.autopsy import execution_error_category
from app.services.conversion import load_mapping_metadata


class KnowledgeValidationError(ValueError):
    pass


MISMATCH_FIELDS = (
    "missing_rows", "unexpected_rows", "duplicate_key_mismatches", "column_mismatches",
    "null_mismatches", "numeric_precision_differences",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_sql(sql: str) -> str:
    without_comments = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"\s+", " ", without_comments).strip().lower().rstrip(";")


def _expression_shape(value: str) -> str:
    """Remove literals and identifiers while retaining reusable operator/function structure."""
    value = re.sub(r"'(?:''|[^'])*'", " <str> ", value)
    value = re.sub(r'"(?:""|[^"])*"', " <id> ", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\b", " <num> ", value)
    functions = {name.upper() for name in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", value)}
    operators = set(re.findall(r"<>|!=|>=|<=|\|\||[-+*/%=<>]", value))
    keywords = {token.upper() for token in re.findall(r"\b(?:CASE|WHEN|THEN|ELSE|END|AND|OR|NOT|IS|NULL|IN|LIKE)\b", value, re.I)}
    return " ".join(sorted(functions | operators | keywords))


def build_signature(mapping: Mapping, diagnosis: AutopsyAIOutput, run: ShadowRun) -> dict:
    affected = {name.casefold() for name in diagnosis.affected_transformations}
    transformations = [item for item in mapping.transformations if not affected or item.name.casefold() in affected]
    expression_shapes = sorted({
        shape for item in transformations for port in item.ports
        if port.expression and (shape := _expression_shape(port.expression))
    })
    symptoms = [name for name in MISMATCH_FIELDS if (getattr(run, name) or 0) > 0]
    if run.status == "failed" and execution_error_category(run.error):
        symptoms.append(f"execution:{execution_error_category(run.error)}")
    return {
        "diagnosis_category": diagnosis.diagnosis_category,
        "transformation_types": sorted({item.type for item in transformations}),
        "expression_shapes": expression_shapes[:50],
        "affected_column_shapes": sorted({value.casefold() for value in diagnosis.affected_columns})[:100],
        "failure_symptoms": sorted(symptoms),
    }


async def create_candidate(db: AsyncSession, autopsy: Autopsy, owner_id: int) -> KnowledgeCandidate:
    if autopsy.status != "completed" or not autopsy.diagnosis_json:
        raise KnowledgeValidationError("Only a completed AI Autopsy with a structured diagnosis can create a candidate")
    diagnosis = AutopsyAIOutput.model_validate(autopsy.diagnosis_json)
    if diagnosis.diagnosis_category in {"UNKNOWN", "NEEDS_MORE_EVIDENCE"}:
        raise KnowledgeValidationError("The Autopsy diagnosis is not specific enough for reusable knowledge")
    if not diagnosis.suspected_root_cause.strip() or not diagnosis.suggested_corrective_actions:
        raise KnowledgeValidationError("The Autopsy does not contain a meaningful root cause and correction")
    run = await db.get(ShadowRun, autopsy.shadow_run_id)
    mapping = await load_mapping_metadata(db, autopsy.mapping_id)
    if run is None or mapping is None or run.project_id != autopsy.project_id:
        raise KnowledgeValidationError("The original failure provenance is incomplete")
    eligible_failure = (
        run.status == "completed" and run.comparison_result == "FAIL"
    ) or (run.status == "failed" and execution_error_category(run.error) is not None)
    if not eligible_failure:
        raise KnowledgeValidationError("The source Shadow Run is not an eligible failure")
    candidate = KnowledgeCandidate(
        project_id=autopsy.project_id, mapping_id=autopsy.mapping_id, owner_id=owner_id,
        source_autopsy_id=autopsy.id, original_shadow_run_id=run.id,
        original_conversion_id=autopsy.conversion_id,
        diagnosis_category=diagnosis.diagnosis_category,
        transformation_identifiers=diagnosis.affected_transformations,
        affected_columns=diagnosis.affected_columns,
        signature_metadata=build_signature(mapping, diagnosis, run),
        root_cause_summary=diagnosis.suspected_root_cause,
        suggested_corrective_actions=diagnosis.suggested_corrective_actions,
        fixture_id=run.fixture_id, status="draft",
    )
    db.add(candidate)
    await db.flush()
    db.add(KnowledgeEvent(
        candidate_id=candidate.id, actor_id=owner_id, event_type="created",
        from_status=None, to_status="draft", notes="Created from completed AI Autopsy.",
        evidence_snapshot={"source_autopsy_id": autopsy.id, "original_shadow_run_id": run.id, "original_conversion_id": autopsy.conversion_id},
    ))
    await db.commit()
    return await load_candidate(db, candidate.id)


async def verify_candidate(db: AsyncSession, candidate: KnowledgeCandidate, passing_run: ShadowRun, actor_id: int) -> KnowledgeCandidate:
    if candidate.status != "draft":
        raise KnowledgeValidationError("Only a draft candidate can be verified")
    if passing_run.project_id != candidate.project_id or passing_run.owner_id != candidate.owner_id:
        raise KnowledgeValidationError("Passing Shadow Run must belong to the same project and owner")
    if passing_run.mapping_id != candidate.mapping_id:
        raise KnowledgeValidationError("Passing Shadow Run must validate the same mapping")
    if passing_run.fixture_id != candidate.fixture_id:
        raise KnowledgeValidationError("Passing Shadow Run must use the same test fixture as the original failure")
    if passing_run.status != "completed" or passing_run.comparison_result != "PASS" or passing_run.completed_at is None:
        raise KnowledgeValidationError("Passing Shadow Run must be completed with comparison_result=PASS")
    if any((getattr(passing_run, name) or 0) != 0 for name in MISMATCH_FIELDS):
        raise KnowledgeValidationError("Passing Shadow Run contains unresolved comparison mismatches")
    if passing_run.reference_row_count is None or passing_run.migrated_row_count is None or passing_run.matched_rows is None:
        raise KnowledgeValidationError("Passing Shadow Run has insufficient row-count provenance")
    if not (passing_run.reference_row_count == passing_run.migrated_row_count == passing_run.matched_rows):
        raise KnowledgeValidationError("Passing Shadow Run row counts do not establish a complete match")
    if passing_run.conversion_id == candidate.original_conversion_id:
        raise KnowledgeValidationError("Verification requires a different immutable conversion")
    original = await db.get(Conversion, candidate.original_conversion_id)
    corrected = await db.get(Conversion, passing_run.conversion_id)
    if original is None or corrected is None or corrected.mapping_id != candidate.mapping_id or original.mapping_id != candidate.mapping_id:
        raise KnowledgeValidationError("Corrected conversion provenance does not match the candidate mapping")
    if _canonical_sql(original.generated_sql) == _canonical_sql(corrected.generated_sql):
        raise KnowledgeValidationError("Corrected conversion SQL is identical to the original failed conversion")
    evidence = {
        "passing_shadow_run_id": passing_run.id,
        "corrected_conversion_id": corrected.id,
        "corrected_conversion_version": corrected.version,
        "fixture_id": passing_run.fixture_id,
        "comparison_result": passing_run.comparison_result,
        "reference_row_count": passing_run.reference_row_count,
        "migrated_row_count": passing_run.migrated_row_count,
        "matched_rows": passing_run.matched_rows,
        "mismatch_counts": {name: getattr(passing_run, name) or 0 for name in MISMATCH_FIELDS},
        "completed_at": passing_run.completed_at.isoformat(),
    }
    before = candidate.status
    candidate.corrected_conversion_id = corrected.id
    candidate.corrected_conversion_version = corrected.version
    candidate.passing_shadow_run_id = passing_run.id
    candidate.verified_remediation_summary = f"Immutable conversion v{corrected.version} passed fixture {passing_run.fixture_id} with all compared rows matching."
    candidate.verification_outcome = "PASS"
    candidate.verification_scope = f"Verified on fixture {passing_run.fixture_id}"
    candidate.verification_evidence = evidence
    candidate.status = "verified"
    candidate.verified_at = _now()
    db.add(KnowledgeEvent(
        candidate_id=candidate.id, actor_id=actor_id, event_type="verified",
        from_status=before, to_status="verified", notes=candidate.verification_scope,
        evidence_snapshot=evidence,
    ))
    await db.commit()
    return await load_candidate(db, candidate.id)


async def review_candidate(db: AsyncSession, candidate: KnowledgeCandidate, decision: str, notes: str, actor_id: int) -> KnowledgeCandidate:
    before = candidate.status
    now = _now()
    if decision == "approve":
        if candidate.status != "verified" or not candidate.verification_evidence or not candidate.passing_shadow_run_id:
            raise KnowledgeValidationError("Only a fully verified candidate can be approved and published")
        candidate.status = "published"
        candidate.approved_at = now
        candidate.published_at = now
    elif decision == "reject":
        if candidate.status not in {"draft", "verified"}:
            raise KnowledgeValidationError("Only draft or verified candidates can be rejected")
        candidate.status = "rejected"
    elif decision == "archive":
        if candidate.status != "published":
            raise KnowledgeValidationError("Only published knowledge can be archived")
        candidate.status = "archived"
        candidate.archived_at = now
    else:
        raise KnowledgeValidationError("Unsupported review decision")
    candidate.reviewer_id = actor_id
    candidate.review_notes = notes
    db.add(KnowledgeEvent(
        candidate_id=candidate.id, actor_id=actor_id, event_type=decision,
        from_status=before, to_status=candidate.status, notes=notes,
        evidence_snapshot=candidate.verification_evidence,
    ))
    await db.commit()
    return await load_candidate(db, candidate.id)


async def load_candidate(db: AsyncSession, candidate_id: int) -> KnowledgeCandidate | None:
    return await db.scalar(select(KnowledgeCandidate).where(KnowledgeCandidate.id == candidate_id).options(
        selectinload(KnowledgeCandidate.events),
    ).execution_options(populate_existing=True))


def score_candidate(candidate: KnowledgeCandidate, mapping: Mapping, conversion: Conversion | None) -> tuple[int, list[str]]:
    signature = candidate.signature_metadata or {}
    target_types = {item.type for item in mapping.transformations}
    known_types = set(signature.get("transformation_types") or [])
    shared_types = sorted(target_types & known_types)
    target_columns = {port.name.casefold() for item in mapping.transformations for port in item.ports}
    known_columns = set(signature.get("affected_column_shapes") or [])
    shared_columns = sorted(target_columns & known_columns)
    target_shapes = {_expression_shape(port.expression) for item in mapping.transformations for port in item.ports if port.expression}
    shared_shapes = sorted((target_shapes - {""}) & set(signature.get("expression_shapes") or []))
    risk_codes = {
        str(flag.get("code", "")).upper() for flag in (conversion.risk_flags or [])
        if isinstance(flag, dict)
    } if conversion else set()
    score, reasons = 0, []
    if shared_types:
        score += min(3, len(shared_types) + 1)
        reasons.append(f"Shared transformation types: {', '.join(shared_types[:5])}")
    if shared_columns:
        score += 2
        reasons.append(f"Affected field structure overlaps: {', '.join(shared_columns[:5])}")
    if shared_shapes:
        score += 3
        reasons.append("PowerCenter expression operator/function structure overlaps")
    category_token = candidate.diagnosis_category.replace("_MISMATCH", "")
    matching_risks = sorted(code for code in risk_codes if category_token in code or code in candidate.diagnosis_category)
    if matching_risks:
        score += 2
        reasons.append(f"Conversion risk signals align: {', '.join(matching_risks[:5])}")
    return score, reasons
