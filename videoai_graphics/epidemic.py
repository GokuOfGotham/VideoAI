"""Fetch mandatory music and sound effects through Epidemic's official MCP.

Only Python's standard library is used. Every call searches and downloads live;
there is no local-file, cache, alternate-provider, or silent-audio fallback.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
from urllib import error, parse, request
import uuid


MCP_URL = "https://www.epidemicsound.com/a/mcp-service/mcp"
PROTOCOL = "2024-11-05"
_REQUIRED_TOOLS = {"SearchRecordings", "SearchSoundEffects", "DownloadRecording", "DownloadSoundEffect"}
_QUERIES = {
    "political": ("documentary instrumental", "subtle whoosh"),
    "space": ("ambient cinematic", "sci fi transition"),
    "gaming": ("energetic electronic", "game interface whoosh"),
    "reaction": ("playful instrumental", "short pop"),
}
_RPC_LIMIT = 4 * 1024 * 1024


class EpidemicError(RuntimeError):
    """A sanitized, actionable failure that must abort the render."""


def _fail_http(action, exception):
    status = getattr(exception, "code", None)
    if status in (401, 403):
        message = "authentication or access was rejected; check EPIDEMIC_SOUND_API_KEY and its download permissions"
    elif status == 429:
        message = "the service rate limit was reached; wait before retrying"
    elif status and status >= 500:
        message = "the service is temporarily unavailable; retry later"
    elif status:
        message = "the service rejected the request; check API access and search settings"
    else:
        message = "the secure network request failed; check connectivity and retry"
    suffix = f" (HTTP {status})" if isinstance(status, int) else ""
    return EpidemicError(f"Epidemic {action}: {message}{suffix}.")


def _https_url(url):
    if not isinstance(url, str) or len(url) > 16384 or any(ord(char) < 32 for char in url):
        raise EpidemicError("Epidemic returned an invalid download address; retry the request.")
    try:
        parsed = parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError
    except (ValueError, TypeError):
        raise EpidemicError("Epidemic returned an unsafe download address; HTTPS public media hosting is required.") from None
    return url


class _SecureRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _https_url(newurl)
        if req.has_header("Authorization"):
            raise EpidemicError("Epidemic API redirected an authenticated request; verify the official API endpoint.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    return request.build_opener(_SecureRedirect())


def _read_bounded(response, limit, seconds=120):
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise EpidemicError("Epidemic response exceeded the permitted download size.")
        except ValueError:
            raise EpidemicError("Epidemic returned an invalid response size.") from None
    deadline = time.monotonic() + seconds
    chunks = []
    size = 0
    while True:
        if time.monotonic() > deadline:
            raise EpidemicError("Epidemic download timed out; check connectivity and retry.")
        chunk = response.read(min(1024 * 1024, limit + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise EpidemicError("Epidemic response exceeded the permitted download size.")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_rpc(body, response_id):
    try:
        raw = body.decode("utf-8-sig")
    except (AttributeError, UnicodeDecodeError):
        raise EpidemicError("Epidemic returned an unreadable API response; retry the request.") from None
    messages = []
    try:
        parsed = json.loads(raw)
        messages = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        data_lines = []
        for line in raw.replace("\r\n", "\n").split("\n") + [""]:
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip(" "))
            elif not line and data_lines:
                data = "\n".join(data_lines)
                event_lines = data_lines
                data_lines = []
                if not data.strip() or data == "[DONE]":
                    continue
                try:
                    messages.append(json.loads(data))
                except json.JSONDecodeError:
                    # Some transports batch complete JSON data lines without
                    # blank separators. Accept these as independent messages.
                    try:
                        messages.extend(json.loads(item) for item in event_lines if item.strip())
                    except json.JSONDecodeError:
                        raise EpidemicError("Epidemic returned malformed streaming JSON; retry the request.") from None
    for message in messages:
        if isinstance(message, dict) and message.get("id") == response_id:
            if "error" in message:
                raise EpidemicError("Epidemic rejected an API operation; check the account's API permissions and request settings.")
            if "result" not in message:
                raise EpidemicError("Epidemic returned an incomplete API response; retry the request.")
            return message["result"]
    raise EpidemicError("Epidemic did not return the matching API response; retry the request.")


def _reject_api_errors(value):
    """Reject partial GraphQL successes without revealing server error text."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if item.get("errors") or item.get("error") or item.get("isError"):
                raise EpidemicError("Epidemic reported an API operation error; check access and search settings. Rendering stopped.")
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _unwrap(value):
    for _ in range(10):
        _reject_api_errors(value)
        if not isinstance(value, dict):
            return value
        if isinstance(value.get("structuredContent"), (dict, list)):
            value = value["structuredContent"]
            continue
        content = value.get("content")
        if isinstance(content, list):
            decoded = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    try:
                        decoded.append(json.loads(item["text"]))
                    except json.JSONDecodeError:
                        continue
            if len(decoded) == 1:
                value = decoded[0]
                continue
            if not decoded:
                raise EpidemicError("Epidemic returned no usable structured result; retry the request.")
            _reject_api_errors(decoded)
            return decoded
        if len(value) == 1 and next(iter(value)) in ("result", "data", "payload"):
            value = next(iter(value.values()))
            continue
        return value
    raise EpidemicError("Epidemic returned an unsupported nested response.")


class _MCPClient:
    def __init__(self, key):
        self._key = key
        self._session = None
        self._protocol = PROTOCOL
        self._next_id = 0
        self._transport = _opener()

    def rpc(self, method, params=None, *, notification=False):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        response_id = None
        if not notification:
            self._next_id += 1
            response_id = self._next_id
            payload["id"] = response_id
        headers = {
            "Authorization": "Bearer " + self._key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self._protocol,
        }
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        req = request.Request(MCP_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with self._transport.open(req, timeout=45) as response:
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    if len(session) > 1024 or any(ord(char) < 32 for char in session):
                        raise EpidemicError("Epidemic returned an invalid API session.")
                    self._session = session
                body = _read_bounded(response, _RPC_LIMIT, 90)
        except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
            raise _fail_http("API request", exc) from None
        if notification:
            return None
        return _parse_rpc(body, response_id)

    def initialize(self):
        result = self.rpc("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "videoai-graphics", "version": "1.0"},
        })
        if not isinstance(result, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(result.get("protocolVersion", ""))):
            raise EpidemicError("Epidemic API initialization failed; verify official MCP access.")
        self._protocol = result["protocolVersion"]
        self.rpc("notifications/initialized", notification=True)
        names = set()
        cursors = set()
        cursor = None
        for _ in range(20):
            result = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                raise EpidemicError("Epidemic did not provide its API capabilities; check MCP account access.")
            names.update(tool["name"] for tool in result["tools"] if isinstance(tool, dict) and isinstance(tool.get("name"), str))
            cursor = result.get("nextCursor")
            if not cursor:
                break
            if not isinstance(cursor, str) or cursor in cursors:
                raise EpidemicError("Epidemic returned invalid API capability pagination.")
            cursors.add(cursor)
        else:
            raise EpidemicError("Epidemic API capability pagination exceeded its limit.")
        missing = _REQUIRED_TOOLS - names
        if missing:
            raise EpidemicError("Epidemic music and SFX search/download capabilities are required; missing: " + ", ".join(sorted(missing)) + ".")

    def call(self, name, arguments):
        return _unwrap(self.rpc("tools/call", {"name": name, "arguments": arguments}))


def _load_key():
    key = os.environ.get("EPIDEMIC_SOUND_API_KEY", "").strip()
    if not key:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        try:
            with env_path.open("r", encoding="utf-8-sig") as handle:
                for line in handle:
                    match = re.match(r"^\s*(?:export\s+)?EPIDEMIC_SOUND_API_KEY\s*=\s*(.*?)\s*$", line)
                    if match:
                        candidate = match.group(1)
                        if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "\"'":
                            candidate = candidate[1:-1]
                        else:
                            candidate = re.split(r"\s+#", candidate, maxsplit=1)[0].strip()
                        if candidate:
                            key = candidate
                            break
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            raise EpidemicError("Cannot read the project's .env; set EPIDEMIC_SOUND_API_KEY in the environment.") from None
    if not key:
        raise EpidemicError("Epidemic music and SFX are required. Set EPIDEMIC_SOUND_API_KEY in the environment or the VideoAI root .env before rendering.")
    if len(key) > 8192 or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise EpidemicError("EPIDEMIC_SOUND_API_KEY has invalid formatting; replace it with the account's API key.")
    return key


def _number(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EpidemicError(f"{label} must be a finite number.")
    try:
        value = float(value)
    except OverflowError:
        raise EpidemicError(f"{label} must be a finite number.") from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise EpidemicError(f"{label} must be between {minimum:g} and {maximum:g}.")
    return value


def _object(value, label, keys):
    if not isinstance(value, dict):
        raise EpidemicError(f"{label} must be an object; music and SFX cannot be disabled.")
    if set(value) - set(keys):
        raise EpidemicError(f"{label} contains unsupported settings; music and SFX cannot be disabled or replaced by local files.")


def _query(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 240 or any(ord(char) < 32 for char in value):
        raise EpidemicError(f"{label} must be a nonempty search phrase of at most 240 characters.")
    return value.strip()


def _settings(config, duration):
    if not isinstance(config, dict):
        raise EpidemicError("Graphics configuration must be an object.")
    audio = config.get("audio", {})
    _object(audio, "audio", {"provider", "music", "sfx"})
    if audio.get("provider", "epidemic") != "epidemic":
        raise EpidemicError("Every graphics render requires Epidemic music and SFX; alternate or disabled providers are unsupported.")
    preset = config.get("preset", "gaming")
    if not isinstance(preset, str) or preset not in _QUERIES:
        raise EpidemicError("Audio preset must be political, space, gaming, or reaction.")
    music_query, sfx_query = _QUERIES[preset]
    music = audio.get("music", {})
    _object(music, "audio.music", {"query", "gain_db"})
    music = {"query": _query(music.get("query", music_query), "audio.music.query"),
             "gain_db": _number(music.get("gain_db", -24), "audio.music.gain_db", -36, -6)}
    default_start = min(0.2, duration * 0.1)
    overlays = config.get("overlays")
    if isinstance(overlays, list) and overlays and isinstance(overlays[0], dict) and "start" in overlays[0]:
        default_start = _number(overlays[0]["start"], "first overlay start", 0, duration)
        if default_start >= duration:
            raise EpidemicError("The first overlay must start before the video ends to place its required sound effect.")
    sfx = audio.get("sfx", [{"start": default_start, "duration": min(1, duration - default_start)}])
    if not isinstance(sfx, list) or not sfx or len(sfx) > 64:
        raise EpidemicError("audio.sfx must contain between 1 and 64 sound effects; empty or disabled SFX are unsupported.")
    effects = []
    for index, item in enumerate(sfx):
        label = f"audio.sfx[{index}]"
        _object(item, label, {"query", "start", "duration", "gain_db"})
        start = _number(item.get("start", default_start), label + ".start", 0, duration)
        if start >= duration:
            raise EpidemicError(f"{label}.start must be before the video ends.")
        effect_duration = _number(item.get("duration", min(1, duration - start)), label + ".duration", 0.02, duration - start)
        effects.append({"query": _query(item.get("query", sfx_query), label + ".query"),
                        "start": start, "duration": effect_duration,
                        "gain_db": _number(item.get("gain_db", -14), label + ".gain_db", -30, 0)})
    return music, effects


def _find(value, key):
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for item in value.values():
            found = _find(item, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find(item, key)
            if found is not None:
                return found
    return None


def _select(client, query, *, music):
    search_tool = "SearchRecordings" if music else "SearchSoundEffects"
    arguments = {"query": {"term": query}, "first": 5}
    if music:
        arguments["filter"] = {"vocals": False}
    result = client.call(search_tool, arguments)
    nodes = _find(result, "nodes")
    if not isinstance(nodes, list):
        raise EpidemicError("Epidemic search returned an unsupported response; no audio was substituted.")
    field = "recording" if music else "soundEffect"
    for node in nodes:
        asset = node.get(field) if isinstance(node, dict) else None
        if not isinstance(asset, dict):
            continue
        try:
            asset_id = str(uuid.UUID(str(asset.get("id", ""))))
        except ValueError:
            continue
        title = asset.get("title")
        if isinstance(title, str) and title.strip():
            title = " ".join(title.split())[:300]
            return {"id": asset_id, "title": title}
    kind = "music" if music else "sound effects"
    raise EpidemicError(f"Epidemic found no usable {kind}; revise the search query and retry. Rendering stopped.")


def _probe_audio(path, ffprobe):
    try:
        result = subprocess.run([
            str(ffprobe), "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration",
            "-of", "json", str(path),
        ], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise EpidemicError("Cannot validate downloaded Epidemic audio; install or configure a working ffprobe executable.") from None
    if result.returncode != 0:
        raise EpidemicError("Downloaded Epidemic media failed audio validation; retry the download.")
    try:
        metadata = json.loads(result.stdout)
        streams = [stream for stream in metadata.get("streams", []) if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
        lengths = [metadata.get("format", {}).get("duration")] + [stream.get("duration") for stream in streams]
        lengths = [float(value) for value in lengths if value is not None]
        length = max((value for value in lengths if math.isfinite(value) and value > 0), default=0)
        if not streams or length <= 0:
            raise ValueError
        return length
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise EpidemicError("Downloaded Epidemic media contains no valid audio stream or duration; retry the download.") from None


def _download(client, asset, workspace, ffprobe, *, music):
    options = {"fileType": "MP3"}
    if music:
        options["stemType"] = "FULL"
    result = client.call("DownloadRecording" if music else "DownloadSoundEffect", {"id": asset["id"], "options": options})
    url = _https_url(_find(result, "assetUrl"))
    filename = ("epidemic_music_" if music else "epidemic_sfx_") + uuid.uuid4().hex + ".mp3"
    path = workspace / filename
    req = request.Request(url, headers={"Accept": "audio/mpeg, application/octet-stream"}, method="GET")
    try:
        with _opener().open(req, timeout=45) as response:
            if hasattr(response, "geturl"):
                _https_url(response.geturl())
            payload = _read_bounded(response, (256 if music else 32) * 1024 * 1024)
        if not payload:
            raise EpidemicError("Epidemic returned an empty audio download; retry the request.")
        with path.open("xb") as handle:
            handle.write(payload)
    except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
        raise _fail_http("audio download", exc) from None
    try:
        length = _probe_audio(path, ffprobe)
    except EpidemicError:
        path.unlink(missing_ok=True)
        raise
    return path, length, hashlib.sha256(payload).hexdigest()


def prepare_audio(config: dict, duration: float, workspace: Path, *, ffprobe="ffprobe") -> dict:
    """Fetch live Epidemic music and at least one SFX, or raise EpidemicError.

    The returned manifest contains IDs, titles, queries, timestamps, cue timing,
    gains, and SHA-256 hashes. It contains no credentials, media URLs, or paths.
    """
    duration = _number(duration, "video duration", 0, 86400)
    if duration <= 0:
        raise EpidemicError("Video duration must be greater than zero.")
    music_settings, effects_settings = _settings(config, duration)
    key = _load_key()
    workspace = Path(workspace).resolve()
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise EpidemicError("Cannot create the temporary Epidemic audio workspace; check write permissions.") from None
    client = _MCPClient(key)
    client.initialize()
    created = []
    try:
        music_asset = _select(client, music_settings["query"], music=True)
        path, _, digest = _download(client, music_asset, workspace, ffprobe, music=True)
        created.append(path)
        music_metadata = {**music_asset, **music_settings, "sha256": digest, "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        music = {**music_metadata, "path": str(path)}
        effects = []
        effect_metadata = []
        for settings in effects_settings:
            asset = _select(client, settings["query"], music=False)
            path, asset_duration, digest = _download(client, asset, workspace, ffprobe, music=False)
            created.append(path)
            if min(settings["duration"], asset_duration) < 0.02:
                raise EpidemicError("Epidemic returned a sound effect shorter than 0.02 seconds; revise the SFX query and retry.")
            metadata = {**asset, **settings, "duration": min(settings["duration"], asset_duration), "sha256": digest,
                        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
            effects.append({**metadata, "path": str(path)})
            effect_metadata.append(metadata)
        manifest = {"provider": "epidemic", "api": "official_mcp", "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "music": music_metadata, "sfx": effect_metadata}
        return {"music": music, "sfx": effects, "manifest": manifest}
    except Exception:
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
