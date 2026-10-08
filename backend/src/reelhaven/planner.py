"""The planner (ARCHITECTURE.md §6.4, §8): what should happen to one file.

Pure function, no I/O: ``plan(info, original_language, policy) -> Plan``.
Phase 0.3 decides track removals and default flags (a ``remux``); video
encoding decisions are added in phase 0.4.
"""

from typing import Literal

from pydantic import BaseModel

from reelhaven.audio_rules import AudioCodec, conversion, saved_bytes
from reelhaven.encode_planner import VideoPlan, format_size, plan_video
from reelhaven.media.info import MediaInfo, Stream
from reelhaven.media.languages import display_name
from reelhaven.policy import LanguagePolicy
from reelhaven.profiles import ProfileSettings

Action = Literal["skip", "remux", "encode"]
Flag = Literal[
    "wrong_language", "no_wanted_audio", "dolby_vision", "hdr10plus", "probe_failed", "no_audio"
]


class TrackPlan(BaseModel):
    index: int
    kind: Literal["audio", "subtitle"]
    language: str | None
    title: str | None
    keep: bool
    default_before: bool
    default_after: bool
    reason: str
    # Audio conversion (ADR-0023); None = the track is copied.
    convert_codec: AudioCodec | None = None
    convert_kbps: int | None = None
    convert_channels: int | None = None  # 2 when downmixing (ADR-0024)


class Plan(BaseModel):
    action: Action
    tracks: list[TrackPlan]
    flags: list[Flag]
    summary: str
    details: list[str]
    removed_bytes: int | None  # estimate; None when stream sizes are unknown
    video: VideoPlan | None = None  # set when the library has a compression profile
    audio_saved_bytes: int | None = None  # estimate for converted audio tracks

    @property
    def changes(self) -> bool:
        return self.action != "skip"

    @property
    def remux_saved_bytes(self) -> int | None:
        """Estimated saving of a track-change job: removed tracks plus converted audio."""
        if self.removed_bytes is None:
            return None
        return self.removed_bytes + (self.audio_saved_bytes or 0)


def _effective_language(stream: Stream, policy: LanguagePolicy) -> str | None:
    if stream.language is None and policy.untagged != "keep":
        return policy.untagged
    return stream.language


def _subtitle_kind(stream: Stream) -> str:
    if stream.forced:
        return "forced"
    if stream.hearing_impaired:
        return "SDH"
    return "full"


def _name(language: str | None) -> str:
    return display_name(language)


def _describe(stream: Stream) -> str:
    label = _name(stream.language)
    if stream.kind == "subtitle":
        label += f" ({_subtitle_kind(stream)})"
    if stream.commentary:
        label += " commentary"
    return label


def plan(info: MediaInfo, original_language: str | None, policy: LanguagePolicy) -> Plan:
    wanted = list(policy.keep_languages)
    if policy.keep_original and original_language and original_language not in wanted:
        wanted.append(original_language)
    viewer = policy.viewer_language

    audio = info.of_kind("audio")
    subtitles = info.of_kind("subtitle")
    flags: list[Flag] = []
    details: list[str] = []

    if info.video is not None and info.video.hdr == "dolby_vision":
        flags.append("dolby_vision")
    if not audio:
        flags.append("no_audio")

    # --- audio ------------------------------------------------------------------
    keep_audio: dict[int, str] = {}  # index -> reason kept
    drop_audio: dict[int, str] = {}
    untagged_kept = policy.untagged == "keep"
    for stream in audio:
        language = _effective_language(stream, policy)
        if language is None:
            if untagged_kept:
                keep_audio[stream.index] = "untagged: kept to be safe"
            else:  # untagged treated as a language that may or may not be wanted
                drop_audio[stream.index] = "untagged"
        elif language in wanted:
            if stream.commentary and not policy.keep_commentary:
                drop_audio[stream.index] = "commentary"
            else:
                keep_audio[stream.index] = (
                    "original language" if language == original_language else "wanted language"
                )
        else:
            drop_audio[stream.index] = "not a wanted language"

    main_kept = [s for s in audio if s.index in keep_audio and not s.commentary]
    if audio and not main_kept:
        # Never remove the last audio track (§8.2): keep everything and flag.
        has_untagged = any(s.language is None for s in audio)
        if original_language and not has_untagged:
            flags.append("wrong_language")
            details.append(
                f"No audio in a wanted language (original: {_name(original_language)}); "
                "all audio kept and the file is flagged for review."
            )
        else:
            flags.append("no_wanted_audio")
            details.append("No audio in a wanted language; all audio kept for safety.")
        for stream in audio:
            keep_audio[stream.index] = "kept: no wanted audio track"
            drop_audio.pop(stream.index, None)

    # --- subtitles ----------------------------------------------------------------
    keep_subs: dict[int, str] = {}
    drop_subs: dict[int, str] = {}
    type_allowed = {
        "full": policy.keep_subtitles_full,
        "forced": policy.keep_subtitles_forced,
        "SDH": policy.keep_subtitles_sdh,
    }
    for stream in subtitles:
        language = _effective_language(stream, policy)
        kind = _subtitle_kind(stream)
        if language is None:
            if untagged_kept:
                keep_subs[stream.index] = "untagged: kept to be safe"
            else:
                drop_subs[stream.index] = "untagged"
        elif language not in wanted:
            drop_subs[stream.index] = "not a wanted language"
        elif stream.commentary and not policy.keep_commentary:
            drop_subs[stream.index] = "commentary"
        elif not type_allowed[kind]:
            drop_subs[stream.index] = f"{kind} subtitles not wanted"
        else:
            keep_subs[stream.index] = "wanted language"

    # --- default flags (§8.3) -----------------------------------------------------------
    defaults: dict[int, bool] = {s.index: s.default for s in [*audio, *subtitles]}
    if policy.set_defaults:
        kept_main = [s for s in audio if s.index in keep_audio and not s.commentary]
        chosen = _pick_default_audio(kept_main, original_language, viewer)
        if chosen is not None:
            for stream in audio:
                defaults[stream.index] = stream.index == chosen.index
            default_language = _effective_language(chosen, policy)
            kept_sub_streams = [s for s in subtitles if s.index in keep_subs]
            if default_language is not None:
                sub_choice = _pick_default_subtitle(kept_sub_streams, default_language, viewer)
                for stream in subtitles:
                    defaults[stream.index] = (
                        sub_choice is not None and stream.index == sub_choice.index
                    )
            # Untagged default audio: subtitle defaults are left as they are.

    # MP4/MOV can't store "no default track": the muxer then enables the first
    # one of that type. Plan for what the file will really contain, otherwise
    # every remux would plan the same change again.
    if any(name in info.container for name in ("mp4", "mov")):
        for group, kept_ids in ((audio, keep_audio), (subtitles, keep_subs)):
            kept_streams = [s for s in group if s.index in kept_ids]
            if kept_streams and not any(defaults[s.index] for s in kept_streams):
                defaults[kept_streams[0].index] = True

    # --- assemble ---------------------------------------------------------------------
    tracks: list[TrackPlan] = []
    for stream in [*audio, *subtitles]:
        keep = stream.index in keep_audio or stream.index in keep_subs
        reason = (
            keep_audio.get(stream.index)
            or keep_subs.get(stream.index)
            or (drop_audio.get(stream.index) or drop_subs.get(stream.index) or "")
        )
        tracks.append(
            TrackPlan(
                index=stream.index,
                kind=stream.kind,  # type: ignore[arg-type]
                language=stream.language,
                title=stream.title,
                keep=keep,
                default_before=stream.default,
                default_after=defaults[stream.index] if keep else False,
                reason=reason,
            )
        )

    removed = [t for t in tracks if not t.keep]
    default_changes = [t for t in tracks if t.keep and t.default_before != t.default_after]
    if removed:
        for kind in ("audio", "subtitle"):
            names = [_describe(_stream(info, t.index)) for t in removed if t.kind == kind]
            if names:
                details.append(f"Remove {kind}: {', '.join(names)}.")
    for track in default_changes:
        stream = _stream(info, track.index)
        verb = "Make default" if track.default_after else "Clear default"
        details.append(f"{verb}: {track.kind} {_describe(stream)}.")

    if "wrong_language" in flags or "no_wanted_audio" in flags:
        # The file needs a human decision: change nothing at all.
        for track in tracks:
            track.keep = True
            track.default_after = track.default_before
        removed, default_changes = [], []
        details = [d for d in details if not d.startswith(("Remove", "Make", "Clear"))]
    action: Action = "remux" if removed or default_changes else "skip"
    summary = _summary(action, original_language, removed, default_changes)
    return Plan(
        action=action,
        tracks=tracks,
        flags=flags,
        summary=summary,
        details=details,
        removed_bytes=_removed_bytes(info, removed),
    )


def _pick_default_audio(
    candidates: list[Stream], original: str | None, viewer: str
) -> Stream | None:
    """Original language if kept, otherwise the viewer's, otherwise keep the current default."""
    for language in (original, viewer):
        if language is None:
            continue
        matches = [s for s in candidates if s.language == language]
        if matches:
            current = [s for s in matches if s.default]
            return current[0] if current else matches[0]
    current = [s for s in candidates if s.default]
    if current:
        return current[0]
    return candidates[0] if candidates else None


def _pick_default_subtitle(
    candidates: list[Stream], audio_language: str, viewer: str
) -> Stream | None:
    viewer_subs = [s for s in candidates if s.language == viewer and not s.commentary]
    if audio_language == viewer:
        # Viewer understands the audio: only forced subtitles (signs, foreign lines).
        forced = [s for s in viewer_subs if s.forced]
        return forced[0] if forced else None
    # Foreign audio: full subtitles in the viewer's language, SDH as a fallback.
    full = [s for s in viewer_subs if not s.forced and not s.hearing_impaired]
    sdh = [s for s in viewer_subs if s.hearing_impaired and not s.forced]
    if full:
        return full[0]
    return sdh[0] if sdh else None


def _stream(info: MediaInfo, index: int) -> Stream:
    return next(s for s in info.streams if s.index == index)


def _removed_bytes(info: MediaInfo, removed: list[TrackPlan]) -> int | None:
    if not removed:
        return 0
    if not info.duration_s:
        return None
    total = 0
    for track in removed:
        bit_rate = _stream(info, track.index).bit_rate
        if bit_rate is None:
            if track.kind == "subtitle":
                continue  # text subtitles are tiny; image subtitles unknown
            return None
        total += int(bit_rate * info.duration_s / 8)
    return total


def _summary(
    action: Action,
    original: str | None,
    removed: list[TrackPlan],
    default_changes: list[TrackPlan],
) -> str:
    origin = f"Original language: {_name(original)}." if original else "Original language unknown."
    if action == "skip":
        return f"{origin} Nothing to change."
    parts: list[str] = []
    audio = sum(1 for t in removed if t.kind == "audio")
    subs = sum(1 for t in removed if t.kind == "subtitle")
    if audio:
        parts.append(f"remove {audio} audio track{'s' if audio != 1 else ''}")
    if subs:
        parts.append(f"remove {subs} subtitle track{'s' if subs != 1 else ''}")
    if default_changes:
        parts.append("fix default tracks")
    return f"{origin} Will {', '.join(parts)}."


_CODEC_NAMES = {"eac3": "E-AC-3", "aac": "AAC", "opus": "Opus"}


def _plan_audio(info: MediaInfo, result: Plan, profile: ProfileSettings) -> int:
    """Mark kept audio tracks the profile converts; returns the estimated bytes saved."""
    saved = 0
    for track in result.tracks:
        if track.kind != "audio" or not track.keep:
            continue
        stream = _stream(info, track.index)
        change = conversion(
            stream,
            profile.audio,
            profile.audio_codec,
            profile.audio_kbps_per_channel,
            profile.downmix_stereo,
        )
        if change is None:
            continue
        track.convert_codec, track.convert_kbps = profile.audio_codec, change.kbps
        track.convert_channels = change.channels
        saved += saved_bytes(stream, change.kbps, info.duration_s or 0.0)
    return saved


def _conversion_details(info: MediaInfo, result: Plan) -> list[str]:
    return [
        f"Convert audio: {_describe(_stream(info, t.index))} "
        f"({(_stream(info, t.index).codec or '?').upper()}) → "
        f"{_CODEC_NAMES.get(t.convert_codec or '', t.convert_codec)}"
        f"{' stereo' if t.convert_channels == 2 else ''} {t.convert_kbps} kbit/s."
        for t in result.tracks
        if t.convert_codec
    ]


def plan_file(
    info: MediaInfo,
    original_language: str | None,
    policy: LanguagePolicy,
    profile: ProfileSettings | None,
    no_gain_profile: str | None = None,
) -> Plan:
    """Language changes (§8) plus the video decision (§7.4), done in one pass."""
    result = plan(info, original_language, policy)
    if profile is None:
        return result
    video = plan_video(info, profile, no_gain_profile)
    result.video = video
    if info.video is not None and info.video.hdr == "hdr10plus":
        result.flags.append("hdr10plus")
    if "wrong_language" in result.flags or "no_wanted_audio" in result.flags:
        video.decision = "keep"
        video.reason = "The file needs review first."
        return result
    audio_saved = _plan_audio(info, result, profile)
    converted = any(t.convert_codec for t in result.tracks)
    if converted and video.decision == "encode":
        # Converted in the same pass: count the audio in the saving estimate.
        result.audio_saved_bytes = audio_saved
        if video.bytes_after_estimate is not None and info.size_bytes:
            video.bytes_after_estimate = max(video.bytes_after_estimate - audio_saved, 0)
            video.savings_percent = round(
                100 * (1 - video.bytes_after_estimate / info.size_bytes), 1
            )
            saved = info.size_bytes - video.bytes_after_estimate
            video.reason = f"Saves about {format_size(saved)} ({video.savings_percent:.0f} %)."
        result.details.extend(_conversion_details(info, result))
    elif converted:
        # ADR-0023 audio-only: the video is copied. Worth it when there are track
        # changes anyway, or when the audio alone reaches the profile's minimum.
        minimum = (info.size_bytes or 0) * profile.min_savings_percent / 100
        if result.action == "remux" or (info.size_bytes and audio_saved >= minimum):
            result.action = "remux"
            result.audio_saved_bytes = audio_saved
            result.details.extend(_conversion_details(info, result))
            n = sum(1 for t in result.tracks if t.convert_codec)
            what = f"convert {n} audio track{'s' if n != 1 else ''}"
            if result.summary.endswith("Nothing to change."):
                result.summary = result.summary.replace("Nothing to change.", f"Will {what}.")
            else:
                result.summary = result.summary[:-1] + f", {what}."
        else:
            for track in result.tracks:
                track.convert_codec = track.convert_kbps = None
    if video.decision == "encode":
        result.action = "encode"
        height = (
            f" {video.height_before}p → {video.height_after}p"
            if video.height_after != video.height_before
            else ""
        )
        result.details.insert(
            0,
            f"Re-encode video to {(video.codec or '').upper()}"
            f"{' 10-bit' if video.ten_bit else ''}{height}: "
            f"{video.reason[0].lower()}{video.reason[1:]}",
        )
        origin = result.summary.split(".")[0] + "."
        result.summary = f"{origin} Will re-encode the video" + (
            " and apply the track changes." if any(not t.keep for t in result.tracks) else "."
        )
    return result
