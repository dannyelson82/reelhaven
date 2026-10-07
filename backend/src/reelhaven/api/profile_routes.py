"""Compression profiles, and which profile each library uses."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from reelhaven import audit
from reelhaven.api.deps import (
    AnyPrincipalDep,
    DbDep,
    InteractiveDep,
    csrf_protect,
    require_setup_done,
)
from reelhaven.api.schemas import StrictModel
from reelhaven.db import Library, Profile
from reelhaven.profiles import ProfileSettings

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class MimicSaved(StrictModel):
    """Where a mimicked profile came from, shown next to it (ARCHITECTURE.md §7.2)."""

    file: str = Field(min_length=1, max_length=4096)
    sources: dict[str, Literal["read", "estimated", "default"]] = Field(max_length=20)
    notes: list[Annotated[str, Field(max_length=500)]] = Field(max_length=20)


class ProfileOut(BaseModel):
    id: int
    name: str
    builtin: bool
    settings: ProfileSettings
    source: str
    mimic: MimicSaved | None = None
    used_by: list[str]
    updated_at: datetime


class ProfileIn(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    settings: ProfileSettings
    mimic: MimicSaved | None = None  # set when the profile was made with mimic


class LibraryProfile(StrictModel):
    profile_id: int | None


def _out(profile: Profile, used_by: list[str]) -> ProfileOut:
    return ProfileOut(
        id=profile.id, name=profile.name, builtin=profile.builtin,
        settings=ProfileSettings.model_validate(profile.settings), source=profile.source,
        mimic=MimicSaved.model_validate(profile.mimic) if profile.mimic else None,
        used_by=used_by, updated_at=profile.updated_at,
    )  # fmt: skip


def _users(session: object) -> dict[int, list[str]]:
    rows = session.execute(  # type: ignore[attr-defined]
        select(Library.profile_id, Library.name).where(Library.profile_id.is_not(None))
    ).all()
    users: dict[int, list[str]] = {}
    for profile_id, name in rows:
        users.setdefault(profile_id, []).append(name)
    return users


@router.get("/profiles")
def list_profiles(db: DbDep, _principal: AnyPrincipalDep) -> list[ProfileOut]:
    with db.read() as session:
        users = _users(session)
        profiles = session.scalars(
            select(Profile).order_by(Profile.builtin.desc(), func.lower(Profile.name))
        )
        return [_out(p, users.get(p.id, [])) for p in profiles]


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
def create_profile(body: ProfileIn, db: DbDep, principal: InteractiveDep) -> ProfileOut:
    with db.write() as session:
        profile = Profile(
            name=body.name.strip(),
            settings=body.settings.model_dump(),
            source="mimic" if body.mimic else "manual",
            mimic=body.mimic.model_dump() if body.mimic else None,
        )
        session.add(profile)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "name_taken") from exc
        audit.record(
            session, principal.actor, "profile.created", profile.name, body.settings.model_dump()
        )
        return _out(profile, [])


def _editable(session: object, profile_id: int) -> Profile:
    profile: Profile | None = session.get(Profile, profile_id)  # type: ignore[attr-defined]
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile_not_found")
    if profile.builtin:
        raise HTTPException(status.HTTP_409_CONFLICT, "builtin_profile")
    return profile


@router.put("/profiles/{profile_id}")
def update_profile(
    profile_id: int, body: ProfileIn, db: DbDep, principal: InteractiveDep
) -> ProfileOut:
    with db.write() as session:
        profile = _editable(session, profile_id)
        profile.name = body.name.strip()
        profile.settings = body.settings.model_dump()
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "name_taken") from exc
        audit.record(
            session, principal.actor, "profile.updated", profile.name, body.settings.model_dump()
        )
        return _out(profile, _users(session).get(profile.id, []))


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: int, db: DbDep, principal: InteractiveDep) -> None:
    with db.write() as session:
        profile = _editable(session, profile_id)
        if _users(session).get(profile.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "profile_in_use")
        session.delete(profile)
        audit.record(session, principal.actor, "profile.deleted", profile.name)


@router.put("/libraries/{library_id}/profile")
def set_library_profile(
    library_id: int, body: LibraryProfile, db: DbDep, principal: InteractiveDep
) -> LibraryProfile:
    with db.write() as session:
        library = session.get(Library, library_id)
        if library is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
        if body.profile_id is not None and session.get(Profile, body.profile_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "profile_not_found")
        library.profile_id = body.profile_id
        audit.record(
            session,
            principal.actor,
            "library.profile_set",
            library.name,
            {"profile_id": body.profile_id},
        )
    return body


@router.get("/libraries/{library_id}/profile")
def get_library_profile(library_id: int, db: DbDep, _principal: AnyPrincipalDep) -> LibraryProfile:
    with db.read() as session:
        library = session.get(Library, library_id)
        if library is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "library_not_found")
        return LibraryProfile(profile_id=library.profile_id)
