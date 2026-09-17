# YouTube footage access

The downloader now enables the installed Node runtime and uses yt-dlp's official default dependencies, including yt-dlp-ejs. Search, metadata and clip downloads share the same settings.

The user approved a dedicated Firefox profile for YouTube footage. The profile lives under LocalAppData/VideoAI/YouTubeFirefox. youtube_access.json contains its path, not cookie values. Sign into YouTube in that profile if authentication expires. No Chrome encryption settings were changed. Do not print or export session cookies.

Verified on September 11, 2026: retrieved captions and a 1080p wide excerpt of the official September 3 Vance briefing, YouTube video rNXZbscEn6I (45:32–46:40). Existing licensing filters and attribution logic are unchanged.

September 16, 2026: on this PC every download returned HTTP 403 (format URLs resolved over IPv6 were refused by googlevideo). Forcing IPv4 (`yt-dlp -4 â€¦`) fixed it immediately, with or without the profile cookies. With cookies, use `--extractor-args "youtube:player_client=default,web_embedded"` (the default tv client answers "The page needs to be reloaded" for a cookie session). The dedicated profile folder did not exist on this machine; it was recreated at the same path and the user signed in there. Node 24 is the JS runtime (`--js-runtimes node`; yt-dlp-ejs installed).
