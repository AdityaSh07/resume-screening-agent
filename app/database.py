from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import POSTGRE_DB_URL


class Base(DeclarativeBase):
    pass


class ShortlistedCandidate(Base):
    __tablename__ = "shortlisted_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rank: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320), index=True)
    overall_score: Mapped[float] = mapped_column(Float)
    resume_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    github_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    resume_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    qualification_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    meeting_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    interview_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interview_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interview_timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    interview_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class RecruiterIntegration(Base):
    __tablename__ = "recruiter_integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), unique=True)
    token_data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


def _session_factory() -> async_sessionmaker[AsyncSession]:
    if not POSTGRE_DB_URL:
        raise RuntimeError("POSTGRE_DB_URL is not configured.")
    engine = create_async_engine(POSTGRE_DB_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _ensure_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        for statement in (
            "ALTER TABLE shortlisted_candidates DROP CONSTRAINT IF EXISTS uq_shortlisted_job_email",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS candidate_id VARCHAR(255)",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS qualification_status VARCHAR(64)",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS final_score DOUBLE PRECISION",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS meeting_id VARCHAR(255)",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS meeting_url TEXT",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS interview_start TIMESTAMPTZ",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS interview_end TIMESTAMPTZ",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS interview_timezone VARCHAR(100)",
            "ALTER TABLE shortlisted_candidates ADD COLUMN IF NOT EXISTS interview_status VARCHAR(64)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_shortlisted_job_candidate ON shortlisted_candidates (job_id, candidate_id) WHERE candidate_id IS NOT NULL",
        ):
            await connection.execute(text(statement))


async def save_shortlisted_candidates(
    job_id: str,
    candidates: list[dict],
) -> list[dict]:
    session_factory = _session_factory()
    engine = session_factory.kw["bind"]
    try:
        await _ensure_schema(engine)
        async with session_factory() as session:
            stored: list[dict] = []
            seen_candidates: set[str] = set()
            for rank, result in enumerate(candidates, start=1):
                identity = result["identity"]
                email = identity.email.strip().lower()
                if not email:
                    continue
                candidate_id = identity.candidate_id or None
                dedupe_key = candidate_id or email
                if dedupe_key in seen_candidates:
                    continue
                seen_candidates.add(dedupe_key)

                lookup = [ShortlistedCandidate.job_id == job_id]
                if candidate_id:
                    lookup.append(ShortlistedCandidate.candidate_id == candidate_id)
                else:
                    lookup.append(ShortlistedCandidate.email == email)
                existing = await session.scalar(select(ShortlistedCandidate).where(*lookup))
                if existing is not None:
                    existing.rank = rank
                    existing.candidate_id = candidate_id or existing.candidate_id
                    existing.name = identity.name
                    existing.overall_score = float(result.get("overall_score") or 0)
                    existing.resume_score = result.get("resume_score")
                    existing.github_score = result.get("github_score")
                    existing.resume_reasoning = result.get("resume_reasoning")
                    existing.github_reasoning = result.get("github_reasoning")
                    stored.append(
                        {
                            "rank": rank,
                            "name": existing.name,
                            "email": existing.email,
                            "overall_score": existing.overall_score,
                        }
                    )
                    continue

                row = ShortlistedCandidate(
                    job_id=job_id,
                    candidate_id=candidate_id,
                    rank=rank,
                    name=identity.name,
                    email=email,
                    overall_score=float(result.get("overall_score") or 0),
                    resume_score=result.get("resume_score"),
                    github_score=result.get("github_score"),
                    resume_reasoning=result.get("resume_reasoning"),
                    github_reasoning=result.get("github_reasoning"),
                    test_results=None,
                )
                session.add(row)
                stored.append(
                    {
                        "rank": rank,
                        "name": identity.name,
                        "email": email,
                        "overall_score": row.overall_score,
                    }
                )
            await session.commit()
            return stored
    finally:
        await engine.dispose()


async def update_test_results(
    job_id: str,
    email: str,
    test_results: dict[str, Any],
    candidate_id: str = "",
    candidate_name: str = "",
    final_score: float | None = None,
    qualification_status: str | None = None,
) -> bool:
    """Attach a validated test-result payload to a shortlisted candidate."""
    session_factory = _session_factory()
    engine = session_factory.kw["bind"]
    try:
        await _ensure_schema(engine)
        async with session_factory() as session:
            conditions = [ShortlistedCandidate.job_id == job_id]
            normalized_email = email.strip().lower()
            if candidate_id:
                conditions.append(ShortlistedCandidate.candidate_id == candidate_id)
            elif normalized_email:
                conditions.append(ShortlistedCandidate.email == normalized_email)
            elif candidate_name:
                conditions.append(ShortlistedCandidate.name.ilike(candidate_name.strip()))
            else:
                return False
            result = await session.execute(
                update(ShortlistedCandidate)
                .where(*conditions)
                .values(
                    test_results=test_results,
                    final_score=final_score,
                    qualification_status=qualification_status,
                )
            )
            await session.commit()
            return result.rowcount == 1
    finally:
        await engine.dispose()


async def get_shortlisted_candidates(job_id: str) -> list[dict]:
    session_factory = _session_factory()
    engine = session_factory.kw["bind"]
    try:
        await _ensure_schema(engine)
        async with session_factory() as session:
            rows = (await session.scalars(
                select(ShortlistedCandidate)
                .where(ShortlistedCandidate.job_id == job_id)
                .order_by(ShortlistedCandidate.rank)
            )).all()
            return [
                {
                    "id": row.id,
                    "candidate_id": row.candidate_id,
                    "name": row.name,
                    "email": row.email,
                    "rank": row.rank,
                    "overall_score": row.overall_score,
                    "test_results": row.test_results,
                    "final_score": row.final_score,
                    "qualification_status": row.qualification_status,
                    "meeting_id": row.meeting_id,
                    "meeting_url": row.meeting_url,
                    "interview_start": row.interview_start.isoformat() if row.interview_start else None,
                    "interview_end": row.interview_end.isoformat() if row.interview_end else None,
                    "interview_timezone": row.interview_timezone,
                    "interview_status": row.interview_status,
                }
                for row in rows
            ]
    finally:
        await engine.dispose()


async def get_interview_candidate(job_id: str, candidate_id: int) -> ShortlistedCandidate | None:
    session_factory = _session_factory()
    engine = session_factory.kw["bind"]
    try:
        await _ensure_schema(engine)
        async with session_factory() as session:
            return await session.scalar(
                select(ShortlistedCandidate).where(
                    ShortlistedCandidate.job_id == job_id,
                    ShortlistedCandidate.id == candidate_id,
                )
            )
    finally:
        await engine.dispose()


async def save_interview_details(
    candidate_id: int,
    *,
    meeting_id: str,
    meeting_url: str,
    start: datetime,
    end: datetime,
    timezone: str,
    status: str,
) -> None:
    session_factory = _session_factory()
    engine = session_factory.kw["bind"]
    try:
        await _ensure_schema(engine)
        async with session_factory() as session:
            row = await session.get(ShortlistedCandidate, candidate_id)
            if row is not None:
                row.meeting_id = meeting_id
                row.meeting_url = meeting_url
                row.interview_start = start
                row.interview_end = end
                row.interview_timezone = timezone
                row.interview_status = status
                await session.commit()
    finally:
        await engine.dispose()


async def save_google_token(token_data: dict[str, Any]) -> None:
    session_factory = _session_factory()
    engine = session_factory.kw["bind"]
    try:
        await _ensure_schema(engine)
        async with session_factory() as session:
            row = await session.scalar(
                select(RecruiterIntegration).where(RecruiterIntegration.provider == "google")
            )
            if row is None:
                session.add(RecruiterIntegration(provider="google", token_data=token_data))
            else:
                row.token_data = token_data
                row.updated_at = datetime.utcnow()
            await session.commit()
    finally:
        await engine.dispose()


async def load_google_token() -> dict[str, Any] | None:
    session_factory = _session_factory()
    engine = session_factory.kw["bind"]
    try:
        await _ensure_schema(engine)
        async with session_factory() as session:
            row = await session.scalar(
                select(RecruiterIntegration).where(RecruiterIntegration.provider == "google")
            )
            return row.token_data if row else None
    finally:
        await engine.dispose()