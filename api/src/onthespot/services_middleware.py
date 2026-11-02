import json as _json
import os
import queue

import requests
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.metadata import EpisodeId, TrackId
from yt_dlp import YoutubeDL

from .accounts import get_account_token
from .api.apple_music import (
    apple_music_get_decryption_key,
    apple_music_get_webplayback_info,
)
from .api.crunchyroll import (
    crunchyroll_close_stream,
    crunchyroll_get_decryption_key,
    crunchyroll_get_mpd_info,
)
from .api.deezer import (
    calcbfkey,
    decryptfile,
    genurlkey,
    get_song_info_from_deezer_website,
)
from .api.qobuz import qobuz_get_file_url
from .api.spotify import reinit_spotify_session
from .api.tidal import tidal_get_mpd_data
from .basemodels import QueueItem
from .constants import ItemStatus
from .otsconfig import config
from .resources.exceptions import DownloadCancelled, TrackUnavailableError
from .runtimedata import get_logger, progress_hook, wait_for_download_resume, yt_dlp_progress_hook
from .utils import get_audio_duration, requeue_item, run_ffmpeg
from .youtube_auth import is_youtube_url, youtube_ydl_options

logger = get_logger("services_middleware")


def _download_http_with_resume(item: QueueItem, url, temp_path, headers=None):
    """Stream a URL into *temp_path*, continuing a partial file when possible."""
    headers = dict(headers or {})
    existing = os.path.getsize(temp_path) if os.path.isfile(temp_path) else 0
    if existing:
        headers["Range"] = f"bytes={existing}-"

    response = requests.get(url, headers=headers, stream=True, timeout=60)
    response.raise_for_status()
    can_append = existing > 0 and response.status_code == 206
    if not can_append:
        existing = 0
    total_size = int(response.headers.get("Content-Length", 0) or 0) + existing
    downloaded = existing

    with open(temp_path, "ab" if can_append else "wb") as audio_file:
        for chunk in response.iter_content(chunk_size=config.get("download_chunk_size", 65536)):
            if not chunk:
                continue
            if item.item_status == ItemStatus.CANCELLED:
                raise DownloadCancelled("Download cancelled by user.")
            # wait_for_download_resume(item)
            downloaded += len(chunk)
            audio_file.write(chunk)
            progress_hook(
                item,
                int((downloaded / total_size) * 100) if total_size else item.progress,
                ItemStatus.DOWNLOADING,
                downloaded_bytes=downloaded,
                total_bytes=total_size or None,
            )
    return downloaded


def download_spotify(item: QueueItem, item_id, item_type, token, temp_path):
    default_format = ".mp3"
    temp_path += default_format

    if item_type == "track":
        audio_key = TrackId.from_base62(item_id)
    else:
        audio_key = EpisodeId.from_base62(item_id)

    if item.download_format != "":
        quality = AudioQuality.HIGH
        bitrate = "160k"
    else:
        if token.get_user_attribute("type") == "premium" and item_type == "track":
            quality = AudioQuality.VERY_HIGH
            bitrate = "320k"

    try:
        stream = token.content_feeder().load(audio_key, VorbisOnlyAudioQuality(quality), False, None)
    except RuntimeError as exc:
        if "alternative track" in str(exc).lower():
            raise TrackUnavailableError(item_id) from exc
        reinit_spotify_session(token)
        raise RuntimeError(f"Spotify session connection lost: {exc}") from exc
    except (queue.Empty, OSError) as exc:
        if isinstance(exc, OSError) and exc.errno is None:
            # librespot raises a bare IOError(status) for CDN HTTP errors and
            # requests carries no errno either; neither says anything about
            # the session socket, so keep the session.
            raise
        # Only an OS-level socket error means the session itself is dead:
        # librespot's own reconnect failed and left the socket closed (#416).
        reinit_spotify_session(token)
        raise RuntimeError(f"Spotify session connection lost: {exc}") from exc

    total_size = stream.input_stream.size
    downloaded = 0

    with open(temp_path, "wb") as audio_file:
        while downloaded < total_size:
            if item.item_status == ItemStatus.CANCELLED:
                raise DownloadCancelled("Download cancelled by user.")
            chunk = stream.input_stream.stream().read(config.get("download_chunk_size"))
            downloaded += len(chunk)
            if chunk:
                audio_file.write(chunk)
                progress_hook(
                    item,
                    int((downloaded / total_size) * 100),
                    ItemStatus.DOWNLOADING,
                    downloaded_bytes=downloaded,
                    total_bytes=total_size,
                )
            if not chunk:
                break

    stream.input_stream.stream().close()
    del stream.input_stream

    return default_format, bitrate


def _select_deezer_quality(song, item: QueueItem):
    """
    Selects the best fitting format given the preferred profile and available ones.

    Cascades from best to worst in case of unavailability
    """
    if item.download_profile.bitrate > 1000 and int(song.get("FILESIZE_FLAC", 0)) > 0:
        return 9, "FLAC", "1411k", ".flac"

    if item.download_profile.bitrate > 256 and int(song.get("FILESIZE_MP3_320", 0)) > 0:
        return 5, "MP3_320", "320k", ".mp3"

    if item.download_profile.bitrate > 129 and int(song.get("FILESIZE_MP3_256", 0)) > 0:
        return 3, "MP3_256", "256k", ".mp3"

    return 1, "MP3_128", "128k", ".mp3"


def download_deezer(item: QueueItem, item_id, token, temp_path):
    song = get_song_info_from_deezer_website(token, item_id)

    if item.download_format in ["mp3", "flac"]:
        song_quality, song_format, bitrate, default_format = _select_deezer_quality(song, item)
    else:
        if int(song.get("FILESIZE_FLAC", 0)) > 0:
            song_quality, song_format, bitrate, default_format = 9, "FLAC", "1411k", ".flac"
        elif int(song.get("FILESIZE_MP3_320", 0)) > 0:
            song_quality, song_format, bitrate = 3, "MP3_320", "320k"
        elif int(song.get("FILESIZE_MP3_256", 0)) > 0:
            song_quality, song_format, bitrate = 5, "MP3_256", "256k"
        else:
            song_quality, song_format, bitrate, default_format = 1, "MP3_128", "128k", ".mp3"

    temp_path += default_format

    headers = {
        "Origin": "https://www.deezer.com",
        "Accept-Encoding": "utf-8",
        "Referer": "https://www.deezer.com/login",
    }
    track_data = (
        token["session"]
        .post(
            "https://media.deezer.com/v1/get_url",
            json={
                "license_token": token["license_token"],
                "media": [
                    {
                        "type": "FULL",
                        "formats": [{"cipher": "BF_CBC_STRIPE", "format": song_format}],
                    }
                ],
                "track_tokens": [song["TRACK_TOKEN"]],
            },
            headers=headers,
        )
        .json()
    )

    try:
        logger.debug(track_data)
        url = track_data["data"][0]["media"][0]["sources"][0]["url"]
    except KeyError as exc:
        logger.error(
            "Unable to select Deezer quality %s for track %s , defaulting to 128k MP3. Error: %s",
            song_quality,
            song["SNG_ID"],
            str(exc),
        )
        song_quality = 1
        song_format = "MP3_128"
        bitrate = "128k"
        default_format = ".mp3"
        url_key = genurlkey(song["SNG_ID"], song["MD5_ORIGIN"], song["MEDIA_VERSION"], song_quality)
        url = f"https://e-cdns-proxy-{song['MD5_ORIGIN'][0]}.dzcdn.net/mobile/1/{url_key.decode()}"

    response = requests.get(url, stream=True, timeout=60)
    if response.status_code != 200:
        logger.info("Deezer download failed %s", response.status_code)
        item.item_status = ItemStatus.FAILED
        requeue_item(item)
        return default_format, bitrate

    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0
    data_chunks = b""

    for chunk in response.iter_content(chunk_size=config.get("download_chunk_size")):
        downloaded += len(chunk)
        data_chunks += chunk
        if downloaded != total_size:
            if item.item_status == ItemStatus.CANCELLED:
                raise DownloadCancelled("Download cancelled by user.")
            progress_hook(
                item,
                int((downloaded / total_size) * 100),
                ItemStatus.DOWNLOADING,
                downloaded_bytes=downloaded,
                total_bytes=total_size,
            )

    bf_key = calcbfkey(song["SNG_ID"])
    progress_hook(item, 99, ItemStatus.DECRYPTING)
    with open(temp_path, "wb") as out_file:
        decryptfile(data_chunks, bf_key, out_file)

    return default_format, bitrate


def download_via_ytdlp_audio(item: QueueItem, item_metadata, service, item_id, token, temp_path, item_type):
    """Download audio via yt-dlp (SoundCloud, Tidal, YouTube Music)."""
    item_url = item_metadata["item_url"]
    default_format = ""
    bitrate = ""
    ydl_opts = {}

    mpd_file_path = temp_path + ".mpd"

    if service == "soundcloud":
        if token["oauth_token"]:
            ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio"
            ydl_opts["username"] = "oauth"
            ydl_opts["password"] = token["oauth_token"]
        else:
            default_format = ".mp3"
            bitrate = "128k"
            ydl_opts["format"] = "bestaudio[ext=mp3]"

    elif service == "tidal":
        default_format = ".flac"
        bitrate = "1411k"

        # Get MPD manifest with error handling
        mpd_data = tidal_get_mpd_data(token, item_id)
        if not mpd_data:
            raise RuntimeError(f"Tidal: Failed to get MPD manifest for track {item_id}")

        # Check if manifest is JSON with direct URLs (common for AAC/MP4 tracks)

        try:
            manifest_json = _json.loads(mpd_data)
            if manifest_json.get("urls"):
                direct_url = manifest_json["urls"][0]
                logger.info("Tidal: Direct URL detected", extra={"url": direct_url[:80]})
                headers = {"Authorization": f"Bearer {token['access_token']}"}
                resp = requests.get(direct_url, headers=headers, stream=True, timeout=60)
                resp.raise_for_status()
                with open(temp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                mime = manifest_json.get("codecs", "audio/mp4")
                default_format = ".flac" if "flac" in mime else ".m4a"
                bitrate = "1411k"
                return default_format, bitrate
        except (_json.JSONDecodeError, KeyError):
            pass

        # Fallback: Write MPD to temp file for yt-dlp
        with open(mpd_file_path, "wb") as mpd_file:
            mpd_file.write(mpd_data.encode("utf-8"))

        prefix = "file:///" if os.name == "nt" else "file://"
        item_url = f"{prefix}{mpd_file_path}"

        ydl_opts["allowed_extractors"] = ["generic"]
        ydl_opts["fixup"] = "never"
        ydl_opts["enable_file_urls"] = True
        ydl_opts["allow_unplayable_formats"] = True

        ydl_opts["http_headers"] = {
            "Authorization": f"Bearer {token['access_token']}",
            "X-Tidal-Token": token["access_token"],
        }

        ydl_opts["quiet"] = False
        ydl_opts["nowarnings"] = False

    elif service == "youtube_music":
        default_format = ".m4a"
        bitrate = "128k"
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts.update(youtube_ydl_options())

    ydl_opts.update(
        {
            "verbose": config.get("debug_mode", False),
            "quiet": False,
            "no_warnings": True,
            "noprogress": True,
            "extract_audio": True,
            "outtmpl": temp_path,
            "continuedl": True,
            "overwrites": False,
            "retries": 3,
            "fragment_retries": 3,
        }
    )
    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]

    if is_youtube_url(item_id) or is_youtube_url(item_url):
        ydl_opts.update(youtube_ydl_options())

    with YoutubeDL(ydl_opts) as downloader:
        if service == "soundcloud" and token["oauth_token"]:
            info = downloader.extract_info(item_url)
            bitrate = f"{info.get('abr')}k"
            default_format = f".{info.get('audio_ext')}"
        downloader.download(item_url)

    if os.path.exists(mpd_file_path):
        os.remove(mpd_file_path)

    return default_format, bitrate


def resolve_youtube_title_and_artist(video_id: str) -> tuple[str, str]:
    """Retrieve title and artist from YouTube oEmbed/noembed endpoints for unavailable or deleted videos."""
    import json
    import re
    import urllib.request

    title = ""
    artist = ""

    urls = [
        f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
        f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={video_id}",
    ]

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                t = data.get("title") or ""
                a = data.get("author_name") or ""
                if t:
                    title = t
                if a:
                    artist = a
                if title:
                    break
        except Exception as e:
            logger.debug("Failed to resolve oEmbed info for %s from %s: %s", video_id, url, e)

    if title:
        # Strip leading track numbers like "02- ", "02. ", "02 "
        title = re.sub(r"^\d+[\s.-]+", "", title).strip()
    if artist:
        # Strip " - Topic"
        artist = re.sub(r"\s*-\s*Topic$", "", artist, flags=re.IGNORECASE).strip()

    return title, artist


def search_best_youtube_candidates(
    artist: str,
    title: str,
    target_duration_s: int = 0,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    """Search YouTube for high quality versions matching artist and title.

    Prioritizes official label releases (Topic channels, official studio audio) with matching duration,
    disqualifying previews, shorts, and unrelated tracks.
    """
    exclude_ids = exclude_ids or set()
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    base_opts.update(youtube_ydl_options())

    clean_artist = (artist or "").strip()
    clean_title = (title or "").strip()

    queries = []
    if clean_artist and clean_title:
        queries.append(f"{clean_artist} - {clean_title} Official Audio")
        queries.append(f"{clean_artist} - {clean_title}")
        queries.append(f"{clean_title} {clean_artist}")
    elif clean_title:
        queries.append(f"{clean_title} Official Audio")
        queries.append(clean_title)
    else:
        return []

    candidates = []
    seen_ids = set(exclude_ids)

    with YoutubeDL(base_opts) as ytdl:
        for q in queries:
            try:
                res = ytdl.extract_info(f"ytsearch10:{q}", download=False)
                for entry in (res or {}).get("entries") or []:
                    eid = entry.get("id")
                    if eid and eid not in seen_ids:
                        seen_ids.add(eid)
                        candidates.append(entry)
            except Exception as e:
                logger.debug("ytsearch query '%s' failed: %s", q, e)
            if len(candidates) >= 15:
                break

    if not candidates:
        return []

    clean_t = clean_title.lower()
    clean_a = clean_artist.lower()
    title_words = [w for w in clean_t.replace("-", " ").replace("(", " ").replace(")", " ").split() if len(w) > 2]

    # Check if a short track is legitimately expected (e.g. interlude, skit, intro)
    is_short_expected = (0 < target_duration_s <= 45) or any(
        w in clean_t for w in ("intro", "outro", "skit", "interlude", "short")
    )

    def _score(e: dict) -> int:
        ch = str(e.get("channel") or e.get("uploader") or "").lower()
        t = str(e.get("title") or "").lower()
        dur = int(e.get("duration") or 0)

        # 0. Title relevance check (MANDATORY)
        matching_title_words = [w for w in title_words if w in t]
        if title_words and not matching_title_words:
            return -999

        # 1. Duration check - eliminate shorts, snippets, ringtones
        if not is_short_expected:
            if 0 < dur < 45:
                return -999
        if target_duration_s > 45 and dur > 0:
            if dur < target_duration_s * 0.70 or dur > target_duration_s * 1.50:
                return -999

        score = 0
        if clean_t in t:
            score += 150
        elif title_words and len(matching_title_words) == len(title_words):
            score += 120
        elif title_words:
            score += int((len(matching_title_words) / len(title_words)) * 100)

        # Topic channel: Master quality direct from record label
        if " - topic" in ch:
            score += 100
        if "official audio" in t:
            score += 50
        elif "audio" in t:
            score += 20

        # Artist match in channel or title
        artist_words = [w for w in clean_a.split() if len(w) > 2]
        if clean_a in ch or clean_a in t:
            score += 40
        elif any(w in ch or w in t for w in artist_words):
            score += 20

        # Duration match bonus
        if target_duration_s > 0 and dur > 0:
            diff = abs(dur - target_duration_s)
            if diff <= 4:
                score += 80
            elif diff <= 10:
                score += 50
            elif diff <= 20:
                score += 25
            elif diff > 35:
                score -= 80
            elif diff > 75:
                score -= 200

        # Penalize live, cover, karaoke unless original requested it
        if "live" in t and "live" not in clean_t:
            score -= 100
        if "cover" in t and "cover" not in clean_t:
            score -= 120
        if "karaoke" in t or "instrumental" in t:
            score -= 150
        if "cumbia" in t and "cumbia" not in clean_t:
            score -= 80

        return score

    valid_candidates = [c for c in candidates if _score(c) > 0]
    valid_candidates.sort(key=_score, reverse=True)
    return valid_candidates


def search_best_youtube_audio(
    artist: str,
    title: str,
    target_duration_s: int = 0,
    exclude_ids: set[str] | None = None,
) -> tuple[str | None, dict | None]:
    """Search YouTube for the highest audio quality version matching artist and title."""
    candidates = search_best_youtube_candidates(artist, title, target_duration_s, exclude_ids)
    if candidates:
        return candidates[0].get("id"), candidates[0]
    return None, None


def download_fallback_youtube(
    item: QueueItem,
    artist: str,
    title: str,
    temp_path: str,
    target_duration_s: int = 0,
    exclude_ids: set[str] | None = None,
) -> tuple[str, str]:
    """Search and download the highest quality audio stream from YouTube for a track."""
    candidates = search_best_youtube_candidates(
        artist=artist,
        title=title,
        target_duration_s=target_duration_s,
        exclude_ids=exclude_ids,
    )
    if not candidates:
        raise TrackUnavailableError(f"No alternative found on YouTube for '{artist} - {title}'")

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "verbose": config.get("debug_mode", False),
        "quiet": False,
        "no_warnings": True,
        "noprogress": True,
        "extract_audio": True,
        "outtmpl": temp_path,
        "continuedl": True,
        "overwrites": True,
        "retries": 3,
        "fragment_retries": 3,
    }
    ydl_opts.update(youtube_ydl_options())
    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]

    title_lower = (title or "").lower()
    is_short_expected = (0 < target_duration_s <= 45) or any(
        w in title_lower for w in ("intro", "outro", "skit", "interlude", "short")
    )

    for candidate in candidates:
        alt_id = candidate.get("id")
        alt_title = candidate.get("title") or alt_id
        alt_url = f"https://music.youtube.com/watch?v={alt_id}"
        logger.info(
            "Trying fallback track with best audio quality: '%s' (ID: %s)",
            alt_title,
            alt_id,
        )

        try:
            with YoutubeDL(ydl_opts) as downloader:
                downloader.download(alt_url)

            # Determine extension and find actual file
            default_format = ".m4a"
            bitrate = "128k"
            actual_file = temp_path
            if not os.path.isfile(temp_path):
                for ext in (".m4a", ".webm", ".opus", ".mp3", ".ogg"):
                    if os.path.isfile(temp_path + ext):
                        default_format = ext
                        actual_file = temp_path + ext
                        break

            # Verify downloaded file duration
            actual_dur = get_audio_duration(actual_file)
            if not is_short_expected:
                if (target_duration_s > 45 and actual_dur > 0 and actual_dur < target_duration_s * 0.6) or (0 < actual_dur < 30):
                    logger.warning(
                        "Fallback file is too short (%.1fs vs target %ss). Removing and trying next candidate...",
                        actual_dur,
                        target_duration_s,
                    )
                    if os.path.exists(actual_file):
                        os.remove(actual_file)
                    continue

            return default_format, bitrate
        except Exception as e:
            logger.warning("Download failed for candidate '%s': %s", alt_id, e)
            continue

    raise TrackUnavailableError(f"All fallback candidates failed or were too short for '{artist} - {title}'")


def download_http_stream(item: QueueItem, item_metadata, service, item_id, token, temp_path):
    """Download a direct HTTP stream (Bandcamp, Qobuz)."""
    if service == "qobuz":
        default_format = ".flac"
        bitrate = "1411k"
        file_url = qobuz_get_file_url(token, item_id)
    else:  # bandcamp
        default_format = ".mp3"
        bitrate = "128k"
        file_url = item_metadata["file_url"]

    response = requests.get(file_url, stream=True, timeout=60)
    total_size = int(response.headers.get("Content-Length", 0))
    downloaded = 0

    with open(temp_path, "wb") as audio_file:
        for chunk in response.iter_content(chunk_size=config.get("download_chunk_size", 1024)):
            if not chunk:
                continue
            downloaded += len(chunk)
            audio_file.write(chunk)
            if total_size > 0 and downloaded != total_size:
                if item.item_status == ItemStatus.CANCELLED:
                    raise DownloadCancelled("Download cancelled by user.")
                progress_hook(item, int((downloaded / total_size) * 100))

    return default_format, bitrate


def download_apple_music(item: QueueItem, item_id, token, temp_path):
    default_format = ".m4a"
    bitrate = "256k"

    webplayback_info = apple_music_get_webplayback_info(token, item_id)
    stream_url = next(
        (asset["URL"] for asset in webplayback_info["assets"] if asset["flavor"] == "28:ctrp256"),
        None,
    )
    if not stream_url:
        logger.error(
            "Apple Music playback info invalid",
            extra={"webplayback_info": webplayback_info},
        )
        raise RuntimeError("No valid Apple Music stream URL found.")

    decryption_key = apple_music_get_decryption_key(token, stream_url, item_id)

    ydl_opts = {
        "quiet": False,
        "no_warnings": True,
        "outtmpl": temp_path,
        "allow_unplayable_formats": True,
        "fixup": "never",
        "allowed_extractors": ["generic"],
        "noprogress": True,
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
    }
    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]
    if is_youtube_url(item_id):
        ydl_opts.update(youtube_ydl_options())

    with YoutubeDL(ydl_opts) as downloader:
        downloader.download(stream_url)

    decrypted_path = temp_path + ".m4a"
    ffmpeg_cmd = [
        config.get("_ffmpeg_bin_path"),
        "-loglevel",
        "error",
        "-y",
        "-decryption_key",
        decryption_key,
        "-i",
        temp_path,
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        decrypted_path,
    ]
    run_ffmpeg(ffmpeg_cmd)
    progress_hook(item, 99, ItemStatus.DECRYPTING)

    if os.path.exists(temp_path):
        os.remove(temp_path)
    os.rename(decrypted_path, temp_path)

    return default_format, bitrate


def download_crunchyroll(item: QueueItem, item_metadata, item_id, token, temp_path):
    """Download encrypted Crunchyroll video/audio streams and subtitles."""
    skip_url = "https://static.crunchyroll.com/skip-events/production/"
    ydl_base_opts = {
        "quiet": False,
        "no_warnings": True,
        "allow_unplayable_formats": True,
        "fixup": "never",
        "allowed_extractors": ["generic"],
        "noprogress": True,
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
    }
    ydl_base_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]

    encrypted_files = []
    video_files = []
    subtitle_formats = []
    preferred_langs = config.get("preferred_audio_language").replace(" ", "").split(",")

    for version in item_metadata["versions"]:
        lang = version["audio_locale"]
        if lang not in preferred_langs and not config.get("download_all_available_audio"):
            continue

        try:
            (
                mpd_url,
                stream_token,
                _audio_locale,
                headers,
                _versions,
                extra_subtitles,
            ) = crunchyroll_get_mpd_info(token, version["guid"])
            subtitle_formats += extra_subtitles
            decryption_key = crunchyroll_get_decryption_key(token, version["guid"], mpd_url, stream_token)
        except Exception as exc:
            logger.error(str(exc), exc_info=exc)
            continue

        token = get_account_token(item_metadata.get("item_service", "crunchyroll"))
        headers["Authorization"] = f"Bearer {token}"

        # Video
        ydl_video_opts = dict(ydl_base_opts)
        ydl_video_opts["http_headers"] = headers
        ydl_video_opts["outtmpl"] = temp_path + f" - {lang}.%(ext)s.%(ext)s"
        ydl_video_opts["format"] = (
            f"(bestvideo[height<={config.get('preferred_video_resolution')}][ext=mp4]+bestaudio[ext=m4a])/"
            f"(bestvideo[height<={config.get('preferred_video_resolution')}]+bestaudio)/"
            f"best"
        )
        with YoutubeDL(ydl_video_opts) as downloader:
            video_info = downloader.extract_info(mpd_url, download=False)
            encrypted_files.append(
                {
                    "path": downloader.prepare_filename(video_info),
                    "type": "video",
                    "decryption_key": decryption_key,
                    "language": lang,
                }
            )
            downloader.download(mpd_url)

        # Audio
        token = get_account_token(item_metadata.get("item_service", "crunchyroll"))
        headers["Authorization"] = f"Bearer {token}"
        ydl_audio_opts = dict(ydl_base_opts)
        ydl_audio_opts["http_headers"] = headers
        ydl_audio_opts["outtmpl"] = temp_path + f" - {lang}.%(ext)s.%(ext)s"
        ydl_audio_opts["format"] = "(bestaudio[ext=m4a]/bestaudio)"
        with YoutubeDL(ydl_audio_opts) as downloader:
            audio_info = downloader.extract_info(mpd_url, download=False)
            encrypted_files.append(
                {
                    "path": downloader.prepare_filename(audio_info),
                    "type": "audio",
                    "decryption_key": decryption_key,
                    "language": lang,
                }
            )
            downloader.download(mpd_url)

        crunchyroll_close_stream(token, item_id, stream_token)

        # Chapters
        if not config.get("raw_media_download") and config.get("download_chapters"):
            chapter_file = temp_path + f" - {lang}.txt"
            if not os.path.exists(chapter_file):
                resp = requests.get(f"{skip_url}{version['guid']}.json", timeout=20)
                if resp.status_code == 200:
                    chapter_data = resp.json()
                    with open(chapter_file, "w", encoding="utf-8") as cf:
                        cf.write(";FFMETADATA1\n")
                        for entry in ("intro", "credits"):
                            if chapter_data.get(entry):
                                cf.write(
                                    f"[CHAPTER]\nTIMEBASE=1/1\n"
                                    f"START={chapter_data[entry].get('start')}\n"
                                    f"END={chapter_data[entry].get('end')}\n"
                                    f"title={entry.title()}\nlanguage={lang}\n"
                                )
                    video_files.append(
                        {
                            "path": chapter_file,
                            "type": "chapter",
                            "format": "txt",
                            "language": lang,
                        }
                    )

    for enc_file in encrypted_files:
        decrypted_path = os.path.splitext(enc_file["path"])[0]
        video_files.append(
            {
                "path": decrypted_path,
                "format": os.path.splitext(enc_file["path"])[1],
                "type": enc_file["type"],
                "language": enc_file.get("language"),
            }
        )
        ffmpeg_cmd = [
            config.get("_ffmpeg_bin_path"),
            "-loglevel",
            "error",
            "-y",
            "-decryption_key",
            enc_file["decryption_key"],
            "-i",
            enc_file["path"],
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            decrypted_path,
        ]
        run_ffmpeg(ffmpeg_cmd)
        if os.path.exists(enc_file["path"]):
            os.remove(enc_file["path"])

    # Subtitles
    if config.get("download_subtitles"):
        item.item_status = ItemStatus.DOWNLOADING_SUBTITLES
        preferred_sub_langs = config.get("preferred_subtitle_language").split(",")
        seen_langs = []
        for sub in subtitle_formats:
            lang = sub["language"]
            if lang in seen_langs:
                continue
            seen_langs.append(lang)
            if lang not in preferred_sub_langs and not config.get("download_all_available_subtitles"):
                continue
            sub_file = temp_path + f" - {lang}.{sub['extension']}"
            if not os.path.exists(sub_file):
                sub_data = requests.get(sub["url"], timeout=20).text
                with open(sub_file, "w", encoding="utf-8") as sf:
                    sf.write(sub_data)
            video_files.append(
                {
                    "path": sub_file,
                    "type": "subtitle",
                    "format": sub["extension"],
                    "language": lang,
                }
            )

    return video_files


def download_generic(item: QueueItem, item_id, temp_path):
    """Download using yt-dlp's generic extractor (any URL)."""

    ydl_opts = {
        "format": (
            f"(bestvideo[height<={config.get('preferred_video_resolution')}][ext=mp4]+bestaudio[ext=m4a])/"
            f"(bestvideo[height<={config.get('preferred_video_resolution')}]+bestaudio)/"
            f"best"
        ),
        "quiet": False,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": config.get("video_download_path") + os.sep + "%(title)s.%(ext)s",
        "ffmpeg_location": config.get("_ffmpeg_bin_path"),
        "postprocessors": [{"key": "FFmpegMetadata"}],
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
    }

    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]
    if is_youtube_url(item_id):
        ydl_opts.update(youtube_ydl_options())

    with YoutubeDL(ydl_opts) as downloader:
        info = downloader.extract_info(item_id, download=False)
        item.file_path = downloader.prepare_filename(info)
        downloader.download(item_id)


def download_generic_v2a(item: QueueItem, item_id, temp_path):
    """Download using yt-dlp's generic extractor (any URL) but extracts only audio"""

    ydl_opts = {
        "format": (
            f"(bestvideo[height<={config.get('preferred_video_resolution')}][ext=mp4]+bestaudio[ext=m4a])/"
            f"(bestvideo[height<={config.get('preferred_video_resolution')}]+bestaudio)/"
            f"best"
        ),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": config.get("video_download_path") + os.sep + "%(title)s.%(ext)s",
        "ffmpeg_location": config.get("_ffmpeg_bin_path"),
        "postprocessors": [
            {"key": "FFmpegMetadata"},
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": config.get("v2a_preferred_codec"),
                "preferredquality": config.get("v2a_preferred_bitrate"),
            },
        ],
        "continuedl": True,
        "overwrites": False,
        "retries": 3,
        "fragment_retries": 3,
    }

    ydl_opts["progress_hooks"] = [lambda d: yt_dlp_progress_hook(item, d)]
    if is_youtube_url(item_id):
        ydl_opts.update(youtube_ydl_options())

    with YoutubeDL(ydl_opts) as downloader:
        info = downloader.extract_info(item_id, download=False)
        item.file_path = downloader.prepare_filename(info)
        downloader.download(item_id)

    return config.get("v2a_preferred_codec"), config.get("v2a_preferred_bitrate")
