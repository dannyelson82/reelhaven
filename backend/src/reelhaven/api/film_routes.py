"""Test films (ADR-0031): the catalogue, downloads on request, and deleting them."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from reelhaven import films as catalogue
from reelhaven.api.deps import AnyPrincipalDep, InteractiveDep, csrf_protect, require_setup_done
from reelhaven.films import Film, FilmError, FilmLibrary, film

router = APIRouter(dependencies=[Depends(require_setup_done), Depends(csrf_protect)])


class FilmOut(BaseModel):
    id: str
    title: str
    year: int
    about: str
    width: int
    height: int
    hdr: bool
    minutes: int
    download_bytes: int
    credit: str
    licence: str
    licence_url: str
    source_url: str
    state: Literal["available", "downloading", "verifying", "ready", "failed"]
    downloaded_bytes: int
    error: str | None


def _out(films: FilmLibrary, item: Film) -> FilmOut:
    state, done, error = films.state(item)
    return FilmOut(
        id=item.id,
        title=item.title,
        year=item.year,
        about=item.about,
        width=item.width,
        height=item.height,
        hdr=item.hdr,
        minutes=item.minutes,
        download_bytes=item.download_bytes,
        credit=item.credit,
        licence=item.licence,
        licence_url=item.licence_url,
        source_url=item.source_url,
        state=state,
        downloaded_bytes=done,
        error=error,
    )


def _film(film_id: str) -> Film:
    try:
        return film(film_id)
    except FilmError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/films")
def list_films(request: Request, _principal: AnyPrincipalDep) -> list[FilmOut]:
    return [_out(request.app.state.films, item) for item in catalogue.CATALOGUE]


@router.post("/films/{film_id}/download", status_code=status.HTTP_202_ACCEPTED)
def download_film(film_id: str, request: Request, _principal: InteractiveDep) -> FilmOut:
    item = _film(film_id)
    films: FilmLibrary = request.app.state.films
    try:
        films.download(item)
    except FilmError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _out(films, item)


@router.delete("/films/{film_id}")
def delete_film(film_id: str, request: Request, _principal: InteractiveDep) -> FilmOut:
    """Stop a download, or remove a downloaded film."""
    item = _film(film_id)
    films: FilmLibrary = request.app.state.films
    films.delete(item)
    return _out(films, item)
