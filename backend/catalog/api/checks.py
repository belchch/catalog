from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from catalog.api.deps import get_provider, get_settings, get_workspace_db
from catalog.api.schemas import (
    CustomCheckCreate,
    CustomCheckOut,
    CustomCheckPreviewOut,
    CustomCheckPreviewRequest,
    VerifyChecksCatalogOut,
)
from catalog.config import Settings
from catalog.llm.base import LLMProvider
from catalog.skills.verify import builtin_check_labels, registered_checks, run_custom_judge
from catalog.storage.db import Database
from catalog.storage.repo_custom_check import (
    create_custom_check,
    hide_custom_check,
    list_custom_checks,
)

router = APIRouter()


def _check_out(row) -> CustomCheckOut:
    return CustomCheckOut(
        id=row.id,
        name=row.name,
        prompt=row.prompt,
        hidden=row.hidden,
        created_at=row.created_at,
    )


@router.get("/verify-checks", response_model=VerifyChecksCatalogOut)
async def list_verify_checks_endpoint() -> VerifyChecksCatalogOut:
    ids = registered_checks()
    labels = builtin_check_labels()
    return VerifyChecksCatalogOut(
        builtin=ids,
        labels={check_id: labels.get(check_id, check_id) for check_id in ids},
    )


@router.get("/custom-checks", response_model=list[CustomCheckOut])
async def list_custom_checks_endpoint(
    db: Database = Depends(get_workspace_db),
) -> list[CustomCheckOut]:
    return [_check_out(row) for row in list_custom_checks(db)]


@router.post("/custom-checks", response_model=CustomCheckOut)
async def create_custom_check_endpoint(
    body: CustomCheckCreate,
    db: Database = Depends(get_workspace_db),
) -> CustomCheckOut:
    row = create_custom_check(db, name=body.name, prompt=body.prompt)
    return _check_out(row)


@router.post("/custom-checks/preview", response_model=CustomCheckPreviewOut)
async def preview_custom_check_endpoint(
    body: CustomCheckPreviewRequest,
    provider: LLMProvider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
) -> CustomCheckPreviewOut:
    reason = await run_custom_judge(
        body.sample,
        body.prompt,
        provider=provider,
        model=settings.default_model,
        label="preview",
    )
    if reason is None:
        return CustomCheckPreviewOut(passed=True, failures=[])
    return CustomCheckPreviewOut(passed=False, failures=[reason])


@router.post("/custom-checks/{check_id}/hide", status_code=204)
async def hide_custom_check_endpoint(
    check_id: str,
    db: Database = Depends(get_workspace_db),
) -> None:
    if not hide_custom_check(db, check_id):
        raise HTTPException(status_code=404, detail="custom check not found")
