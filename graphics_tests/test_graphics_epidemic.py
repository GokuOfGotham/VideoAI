import io
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from videoai_graphics import epidemic


_KEY = "test-secret-key-never-display"
_MUSIC_ID = "f1f06306-d788-4020-a06b-b5a4f901388c"
_SFX_ID = "2ab20b01-bd68-4fa3-b33d-3941e612f174"
_MEDIA_URL = "https://media.example.org/audio.mp3?private-signature=never-display"


class Response:
    def __init__(self, body, headers=None, url=epidemic.MCP_URL):
        self.body = io.BytesIO(body)
        self.headers = headers or {}
        self.url = url

    def read(self, size=-1):
        return self.body.read(size)

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Transport:
    def __init__(self, *, streaming=False, missing=None, empty=None, failure=None,
                 download_url=_MEDIA_URL, payload=b"synthetic-mocked-audio", structured=False):
        self.requests = []
        self.streaming = streaming
        self.missing = missing or set()
        self.empty = empty
        self.failure = failure
        self.download_url = download_url
        self.payload = payload
        self.structured = structured

    def open(self, req, timeout):
        self.requests.append(req)
        if req.get_method() == "GET":
            return Response(self.payload, {"Content-Length": str(len(self.payload))}, self.download_url)
        if self.failure == "authentication":
            raise HTTPError(epidemic.MCP_URL + "?" + _KEY, 401, _KEY, {}, None)
        message = json.loads(req.data)
        method = message["method"]
        if method == "notifications/initialized":
            return Response(b"")
        if method == "initialize":
            result = {"protocolVersion": epidemic.PROTOCOL, "capabilities": {"tools": {}}}
        elif method == "tools/list":
            cursor = message.get("params", {}).get("cursor")
            names = ["SearchRecordings", "DownloadRecording"] if not cursor else ["SearchSoundEffects", "DownloadSoundEffect"]
            result = {"tools": [{"name": name} for name in names if name not in self.missing]}
            if not cursor:
                result["nextCursor"] = "second-page"
        else:
            name = message["params"]["name"]
            if self.failure == name:
                result = {"isError": True, "content": [{"type": "text", "text": _KEY + _MEDIA_URL}]}
            elif name.startswith("Search"):
                music = name == "SearchRecordings"
                field = "recording" if music else "soundEffect"
                asset = {"id": _MUSIC_ID if music else _SFX_ID, "title": "Test music" if music else "Test effect", "audioFile": {"durationInMilliseconds": 3000}}
                nodes = [] if self.empty == name else [{field: asset}]
                data = {"data": {"recordings" if music else "soundEffects": {"nodes": nodes}}}
                if self.failure == "graphql_partial":
                    data["errors"] = [{"message": _KEY + _MEDIA_URL}]
                result = {"structuredContent": data} if self.structured else {"content": [{"type": "text", "text": json.dumps(data)}], "isError": False}
            else:
                data = {"data": {"downloadRecording" if name == "DownloadRecording" else "downloadSoundEffect": {"assetUrl": self.download_url}}}
                result = {"content": [{"type": "text", "text": json.dumps(data)}]}
        reply = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        if self.failure == "jsonrpc":
            reply = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32000, "message": _KEY + _MEDIA_URL}}
        raw = json.dumps(reply)
        if self.streaming:
            # Pretty JSON spans multiple SSE data lines. An unrelated message
            # precedes the response to test matching by JSON-RPC ID.
            raw = 'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
            raw += "event: message\n" + "\n".join("data: " + line for line in json.dumps(reply, indent=2).splitlines()) + "\n\n"
        return Response(raw.encode(), {"Mcp-Session-Id": "safe-test-session"})

    def tool_names(self):
        messages = [json.loads(req.data) for req in self.requests if req.data]
        return [message["params"]["name"] for message in messages if message["method"] == "tools/call"]


def probe_result(*args, **kwargs):
    return SimpleNamespace(returncode=0, stdout=json.dumps({"format": {"duration": "2.5"}, "streams": [{"codec_type": "audio"}]}), stderr="")


class EpidemicTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name)
        self.env = patch.dict(os.environ, {"EPIDEMIC_SOUND_API_KEY": _KEY})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def prepare(self, transport, config=None, duration=5):
        with patch.object(epidemic, "_opener", return_value=transport), patch.object(epidemic.subprocess, "run", side_effect=probe_result):
            return epidemic.prepare_audio(config or {}, duration, self.workspace)

    def test_live_protocol_and_music_sfx_contract_without_secret_leakage(self):
        transport = Transport()
        result = self.prepare(transport, {"preset": "space", "overlays": [{"start": 0.7}]})
        self.assertEqual(transport.tool_names(), ["SearchRecordings", "DownloadRecording", "SearchSoundEffects", "DownloadSoundEffect"])
        self.assertEqual(result["music"]["gain_db"], -24)
        self.assertEqual(result["sfx"][0]["gain_db"], -14)
        self.assertEqual(result["sfx"][0]["start"], 0.7)
        self.assertEqual(result["music"]["query"], "ambient cinematic")
        self.assertTrue(Path(result["music"]["path"]).is_file())
        self.assertTrue(Path(result["sfx"][0]["path"]).is_file())
        for req in transport.requests:
            if req.get_method() == "GET":
                self.assertIsNone(req.get_header("Authorization"))
            else:
                self.assertEqual(req.get_header("Authorization"), "Bearer " + _KEY)
                self.assertEqual(req.get_header("Mcp-protocol-version"), epidemic.PROTOCOL)
        self.assertEqual(transport.requests[1].get_header("Mcp-session-id"), "safe-test-session")
        manifest = result["manifest"]
        self.assertEqual(manifest["provider"], "epidemic")
        self.assertEqual(manifest["api"], "official_mcp")
        self.assertEqual(len(manifest["music"]["sha256"]), 64)
        self.assertTrue(manifest["fetched_at"].endswith("Z"))
        serialized = json.dumps(manifest)
        for sensitive in (_KEY, _MEDIA_URL, "private-signature", str(self.workspace), '"path"'):
            self.assertNotIn(sensitive, serialized)

    def test_multiline_sse_and_structured_content_work(self):
        for streaming, structured in ((True, False), (False, True)):
            with self.subTest(streaming=streaming, structured=structured):
                result = self.prepare(Transport(streaming=streaming, structured=structured))
                self.assertEqual(result["music"]["id"], _MUSIC_ID)
                self.assertEqual(result["sfx"][0]["id"], _SFX_ID)

    def test_every_render_fetches_fresh_assets_and_never_uses_cached_files(self):
        transport = Transport()
        first = self.prepare(transport)
        second = self.prepare(transport)
        self.assertNotEqual(first["music"]["path"], second["music"]["path"])
        self.assertEqual(transport.tool_names().count("DownloadRecording"), 2)
        self.assertEqual(transport.tool_names().count("DownloadSoundEffect"), 2)
        transport.empty = "SearchRecordings"
        with self.assertRaises(epidemic.EpidemicError):
            self.prepare(transport)

    def test_missing_key_aborts_before_network_or_existing_audio(self):
        (self.workspace / "music.mp3").write_bytes(b"existing")
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "open", side_effect=FileNotFoundError), patch.object(epidemic, "_opener") as opener:
            with self.assertRaisesRegex(epidemic.EpidemicError, "EPIDEMIC_SOUND_API_KEY"):
                epidemic.prepare_audio({}, 5, self.workspace)
            opener.assert_not_called()

    def test_only_named_env_key_is_loaded_from_root_dotenv(self):
        content = "OTHER_API_KEY=ignore-me\nEPIDEMIC_SOUND_API_KEY='correct-key'\n"
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "open", return_value=io.StringIO(content)):
            self.assertEqual(epidemic._load_key(), "correct-key")

    def test_disabled_missing_or_alternate_audio_is_rejected(self):
        bad_audio = [False, None, {"provider": "local"}, {"enabled": False}, {"music": False}, {"music": None}, {"music": {"path": "music.mp3"}}, {"sfx": []}, {"sfx": False}, {"sfx": None}, {"sfx": [{"enabled": False}]}]
        for audio in bad_audio:
            with self.subTest(audio=audio), patch.object(epidemic, "_opener") as opener:
                with self.assertRaises(epidemic.EpidemicError):
                    epidemic.prepare_audio({"audio": audio}, 5, self.workspace)
                opener.assert_not_called()

    def test_invalid_queries_gains_timing_and_unknown_keys_rejected(self):
        bad_audio = [
            {"music": {"query": ""}}, {"music": {"query": "x\n"}},
            {"music": {"gain_db": -99}}, {"music": {"gain_db": 0}},
            {"music": {"gain_db": math.nan}}, {"music": {"gain_db": True}},
            {"sfx": [{"gain_db": -99}]}, {"sfx": [{"gain_db": 1}]},
            {"sfx": [{"duration": 0}]}, {"sfx": [{"start": 5}]},
            {"sfx": [{"duration": 1e-9}]}, {"sfx": [{"start": 4.99}]},
            {"sfx": [{"start": -1}]}, {"sfx": [{"start": 4, "duration": 2}]},
            {"unknown": True},
        ]
        for audio in bad_audio:
            with self.subTest(audio=audio), self.assertRaises(epidemic.EpidemicError):
                self.prepare(Transport(), {"audio": audio})

    def test_auth_jsonrpc_and_tool_errors_are_sanitized_and_abort(self):
        for failure in ("authentication", "jsonrpc", "SearchRecordings", "DownloadRecording", "SearchSoundEffects", "DownloadSoundEffect"):
            with self.subTest(failure=failure):
                transport = Transport(failure=failure)
                with self.assertRaises(epidemic.EpidemicError) as caught:
                    self.prepare(transport)
                self.assertNotIn(_KEY, str(caught.exception))
                self.assertNotIn(_MEDIA_URL, str(caught.exception))
                self.assertEqual(list(self.workspace.glob("epidemic_*.mp3")), [])

    def test_missing_music_or_sfx_capabilities_stop_before_search(self):
        for missing in ({"DownloadRecording"}, {"SearchSoundEffects"}, {"DownloadSoundEffect"}):
            with self.subTest(missing=missing):
                transport = Transport(missing=missing)
                with self.assertRaisesRegex(epidemic.EpidemicError, "capabilities are required"):
                    self.prepare(transport)
                self.assertEqual(transport.tool_names(), [])

    def test_partial_graphql_search_errors_abort_before_download(self):
        for structured in (False, True):
            with self.subTest(structured=structured):
                transport = Transport(failure="graphql_partial", structured=structured)
                with self.assertRaises(epidemic.EpidemicError) as caught:
                    self.prepare(transport)
                self.assertNotIn(_KEY, str(caught.exception))
                self.assertNotIn(_MEDIA_URL, str(caught.exception))
                self.assertEqual(transport.tool_names(), ["SearchRecordings"])
                self.assertEqual(list(self.workspace.glob("epidemic_*.mp3")), [])

    def test_nested_graphql_error_wrappers_are_rejected_without_leaking_details(self):
        valid_data = {"data": {"recordings": {"nodes": [{"recording": {"id": _MUSIC_ID, "title": "Usable partial result"}}]}}}
        for field in ("error", "errors"):
            partial = {**valid_data, field: [{"message": _KEY + _MEDIA_URL}]}
            for wrapped in (
                {"structuredContent": {"payload": partial}, "isError": False},
                {"content": [{"type": "text", "text": json.dumps({"payload": partial})}], "isError": False},
                {"payload": {"result": partial}},
            ):
                with self.subTest(field=field, wrapped=wrapped), self.assertRaises(epidemic.EpidemicError) as caught:
                    epidemic._unwrap(wrapped)
                self.assertNotIn(_KEY, str(caught.exception))
                self.assertNotIn(_MEDIA_URL, str(caught.exception))
        self.assertEqual(epidemic._unwrap({**valid_data, "errors": [], "error": None}), {**valid_data, "errors": [], "error": None})

    def test_empty_music_or_sfx_results_have_no_fallback_and_clean_partial_downloads(self):
        for empty in ("SearchRecordings", "SearchSoundEffects"):
            with self.subTest(empty=empty):
                with self.assertRaisesRegex(epidemic.EpidemicError, "no usable"):
                    self.prepare(Transport(empty=empty))
                self.assertEqual(list(self.workspace.glob("epidemic_*.mp3")), [])

    def test_invalid_download_addresses_and_empty_media_abort(self):
        for address in (None, "http://media.example.org/a.mp3", "file:///a.mp3", "https://localhost/a", "https://127.0.0.1/a", "https://user:password@media.example.org/a"):
            with self.subTest(address=address), self.assertRaises(epidemic.EpidemicError):
                self.prepare(Transport(download_url=address))
        with self.assertRaisesRegex(epidemic.EpidemicError, "empty audio"):
            self.prepare(Transport(payload=b""))

    def test_downloaded_media_must_have_audio_stream_and_positive_duration(self):
        invalid = [
            SimpleNamespace(returncode=1, stdout="", stderr=_KEY),
            SimpleNamespace(returncode=0, stdout=json.dumps({"format": {"duration": "3"}, "streams": [{"codec_type": "video"}]})),
            SimpleNamespace(returncode=0, stdout=json.dumps({"format": {"duration": "0"}, "streams": [{"codec_type": "audio"}]})),
        ]
        for result in invalid:
            with self.subTest(result=result), patch.object(epidemic, "_opener", return_value=Transport()), patch.object(epidemic.subprocess, "run", return_value=result):
                with self.assertRaises(epidemic.EpidemicError):
                    epidemic.prepare_audio({}, 5, self.workspace)
                self.assertEqual(list(self.workspace.glob("epidemic_*.mp3")), [])

    def test_parse_response_matches_id_and_rejects_malformed_content(self):
        body = b'data: {"id":10,"result":{"wrong":true}}\n\ndata: {"id":11,"result":{"correct":true}}\n\n'
        self.assertEqual(epidemic._parse_rpc(body, 11), {"correct": True})
        for body in (b"not-json", b"data: broken-json\n\n", b'{"id":12,"result":{}}'):
            with self.subTest(body=body), self.assertRaises(epidemic.EpidemicError):
                epidemic._parse_rpc(body, 11)

    def test_empty_sse_heartbeat_and_batched_data_lines(self):
        body = b'data: \nid: 0\nretry: 3000\n\ndata: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n\n'
        self.assertEqual(epidemic._parse_rpc(body, 1), {"protocolVersion": "2024-11-05"})
        body = b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\ndata: {"jsonrpc":"2.0","id":1,"result":{"ready":true}}\n\n'
        self.assertEqual(epidemic._parse_rpc(body, 1), {"ready": True})

    def test_sound_effect_asset_cannot_trim_to_effectively_zero(self):
        tiny = SimpleNamespace(returncode=0, stdout=json.dumps({"format": {"duration": "0.001"}, "streams": [{"codec_type": "audio"}]}), stderr="")
        with patch.object(epidemic, "_opener", return_value=Transport()), patch.object(epidemic.subprocess, "run", side_effect=[probe_result(), tiny]):
            with self.assertRaisesRegex(epidemic.EpidemicError, "shorter than 0.02"):
                epidemic.prepare_audio({}, 5, self.workspace)
        self.assertEqual(list(self.workspace.glob("epidemic_*.mp3")), [])

    def test_oversized_download_is_rejected_before_read(self):
        response = Response(b"small", {"Content-Length": "10000"})
        with self.assertRaisesRegex(epidemic.EpidemicError, "size"):
            epidemic._read_bounded(response, 100)


if __name__ == "__main__":
    unittest.main()
