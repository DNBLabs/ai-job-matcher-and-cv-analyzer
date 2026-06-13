"""Operator-only admin routes for searching users and toggling unlimited quota."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.validation import NOT_FOUND_DETAIL, parse_uuid_path_param
from app.db.models import UserAccount
from app.db.repositories.audit_log_repository import AuditLogRepository
from app.db.repositories.user_repository import UserRepository
from app.db.session import get_db_session

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_UNLIMITED_TOGGLED_EVENT = "admin.user.unlimited_toggled"


class AdminUserResponse(BaseModel):
    """User Account fields surfaced to the operator console."""

    id: UUID
    email: str
    is_admin: bool
    is_unlimited: bool
    created_at: datetime


class UpdateUnlimitedRequest(BaseModel):
    """Strict payload for toggling a user's unlimited quota flag."""

    model_config = {"extra": "forbid"}

    is_unlimited: bool


def _user_to_response(user: UserAccount) -> AdminUserResponse:
    """Map a User Account ORM row to the admin API response shape.

    Args:
        user: Persisted User Account row.

    Returns:
        AdminUserResponse: API-safe operator view of the account.
    """
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        is_unlimited=user.is_unlimited,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def search_users(
    email: Annotated[str, Query(max_length=320)] = "",
    _admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> list[AdminUserResponse]:
    """Search User Accounts by email fragment for the operator console.

    Args:
        email: Case-insensitive email fragment; a blank query returns no rows.
        _admin: Authenticated admin account (enforces 404 for non-admins).
        db: Request-scoped database session.

    Returns:
        list[AdminUserResponse]: Matching accounts, capped to a bounded result size.
    """
    users = UserRepository(db).search_by_email(email)
    return [_user_to_response(user) for user in users]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user_unlimited(
    payload: UpdateUnlimitedRequest,
    user_id: Annotated[str, Path()],
    admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminUserResponse:
    """Toggle a user's unlimited-quota flag and record an audit entry.

    Args:
        payload: New ``is_unlimited`` state.
        user_id: Target User Account identifier from the route path.
        admin: Authenticated admin performing the action.
        db: Request-scoped database session.

    Returns:
        AdminUserResponse: Updated account view.

    Raises:
        HTTPException: With 404 when the target account does not exist.
    """
    parsed_user_id = parse_uuid_path_param(user_id, field_name="user_id")
    repository = UserRepository(db)
    updated = repository.set_unlimited(parsed_user_id, is_unlimited=payload.is_unlimited)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)

    AuditLogRepository(db).append_event(
        event_type=ADMIN_UNLIMITED_TOGGLED_EVENT,
        actor_user_id=admin.id,
        subject_user_id=updated.id,
        metadata={"is_unlimited": payload.is_unlimited},
    )
    return _user_to_response(updated)
