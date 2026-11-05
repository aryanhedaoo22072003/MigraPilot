from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_service import (
    AIProviderAuthenticationError,
    AIProviderQuotaError,
    AIProviderRequestError,
    AIProviderResponseError,
    AIService,
    AIServiceNotConfigured,
    get_ai_service,
)
from app.core.config import settings
from app.core.rate_limit import RateLimitExceeded, ai_conversion_limiter
from app.database import get_db
from app.deps import current_user, require_write
from app.models import Conversion, User
from app.schemas import ConversionResponse, RegenerateConversionRequest
from app.services.conversion import invoke_conversion, load_mapping_metadata, persist_conversion

router = APIRouter(tags=["AI Conversion"])


def _check_rate_limit(user: User) -> None:
    try:
        ai_conversion_limiter.check(
            f"conversion:user:{user.id}", settings.ai_conversion_rate_limit_per_minute,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429, detail="AI conversion rate limit exceeded; retry later",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


async def _call_provider(ai_service: AIService, mapping, previous=None, user_comment=None):
    try:
        return await invoke_conversion(ai_service, mapping, previous, user_comment)
    except AIServiceNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIProviderAuthenticationError as exc:
        raise HTTPException(status_code=502, detail="AI provider credentials were rejected") from exc
    except AIProviderQuotaError as exc:
        raise HTTPException(
            status_code=429, detail="AI provider quota exhausted; retry later", headers={"Retry-After": "60"},
        ) from exc
    except AIProviderRequestError as exc:
        raise HTTPException(status_code=502, detail="AI provider request failed") from exc
    except (AIProviderResponseError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail="AI provider returned an invalid structured conversion") from exc
    except Exception as exc:
        # Do not expose provider errors, prompts, credentials, or payload content.
        raise HTTPException(status_code=502, detail="AI provider request failed") from exc


@router.post("/mappings/{mapping_id}/convert", response_model=ConversionResponse, status_code=status.HTTP_201_CREATED)
async def convert_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    ai_service: AIService = Depends(get_ai_service),
):
    require_write(user)
    mapping = await load_mapping_metadata(db, mapping_id)
    if mapping is None or mapping.project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mapping not found")
    _check_rate_limit(user)
    invocation = await _call_provider(ai_service, mapping)
    return await persist_conversion(db, mapping, invocation, "conversion")


@router.post("/conversions/{conversion_id}/regenerate", response_model=ConversionResponse, status_code=status.HTTP_201_CREATED)
async def regenerate_conversion(
    conversion_id: int,
    body: RegenerateConversionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    ai_service: AIService = Depends(get_ai_service),
):
    require_write(user)
    previous = await db.get(Conversion, conversion_id)
    mapping = await load_mapping_metadata(db, previous.mapping_id) if previous else None
    if previous is None or mapping is None or mapping.project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Conversion not found")
    _check_rate_limit(user)
    invocation = await _call_provider(ai_service, mapping, previous, body.user_comment)
    return await persist_conversion(db, mapping, invocation, "regeneration")
