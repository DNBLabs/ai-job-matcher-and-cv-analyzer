"""Integration tests for POST /cvs PDF upload and validation."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.local.memory_blob_store import MemoryBlobStore
from app.auth.middleware import SESSION_COOKIE_NAME
from app.auth.session import SessionService
from app.db.models import Cv, UserAccount
from tests.auth.conftest import create_test_user

VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
EXE_RENAMED_AS_PDF_BYTES = b"MZ\x90\x00fake executable content"


def _authenticate_client(
    client: AsyncClient,
    db_session: Session,
    user: UserAccount,
) -> None:
    """Attach a valid session cookie for the given user to the test client."""
    session_record = SessionService(db_session).create_session(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)


@pytest.mark.asyncio
async def test_upload_valid_pdf_creates_blob_and_db_row(
    cv_client: AsyncClient,
    db_session: Session,
    memory_blob_store: MemoryBlobStore,
) -> None:
    """Authenticated upload stores the PDF in BlobStore and persists CV metadata."""
    user = create_test_user(db_session)
    _authenticate_client(cv_client, db_session, user)

    response = await cv_client.post(
        "/cvs",
        data={"name": "Engineer CV"},
        files={"file": ("resume.pdf", VALID_PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Engineer CV"
    assert "id" in body
    assert "uploaded_at" in body

    cv_id = uuid.UUID(body["id"])
    cv_row = db_session.scalar(select(Cv).where(Cv.id == cv_id))
    assert cv_row is not None
    assert cv_row.user_id == user.id
    assert cv_row.name == "Engineer CV"
    assert cv_row.blob_key == f"cvs/{user.id}/{cv_id}.pdf"

    stored_pdf = memory_blob_store.get(f"{user.id}/{cv_id}.pdf")
    assert stored_pdf == VALID_PDF_BYTES


@pytest.mark.asyncio
async def test_upload_without_session_returns_401(cv_client: AsyncClient) -> None:
    """Unauthenticated upload requests are rejected."""
    response = await cv_client.post(
        "/cvs",
        data={"name": "Engineer CV"},
        files={"file": ("resume.pdf", VALID_PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


@pytest.mark.asyncio
async def test_upload_exe_renamed_as_pdf_is_rejected(
    cv_client: AsyncClient,
    db_session: Session,
) -> None:
    """Executable content disguised as PDF is rejected and nothing is stored."""
    user = create_test_user(db_session, email="reject@example.com")
    _authenticate_client(cv_client, db_session, user)

    response = await cv_client.post(
        "/cvs",
        data={"name": "Bad CV"},
        files={"file": ("resume.pdf", EXE_RENAMED_AS_PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid PDF file"}

    assert db_session.scalars(select(Cv).where(Cv.user_id == user.id)).all() == []
