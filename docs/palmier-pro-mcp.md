# Palmier Pro Mcp

Palmier Pro (/Applications/PalmierPro.app, bundle io.palmier.pro) runs a streamable-HTTP MCP server at http://127.0.0.1:19789/mcp while the app is open. The Claude Desktop extension is only a stdio shim for that URL and is not exposed to Code sessions, so talk to the port directly.

- Client: palmier_mcp.py. `python3 palmier_mcp.py` lists tools; `python3 palmier_mcp.py <tool> '<json args>'` calls one. Call get_timeline first.
- Projects are folders under ~/Documents/Palmier Pro/*.palmier containing project.json and media.json (readable when the app is closed).
- Key tools: get_timeline, get_transcript (granularity "words" or "segments"), inspect_media (wordTimestamps true), set_clip_properties (trimStartFrame/trimEndFrame/fades), split_clips, ripple_delete_ranges, remove_silence, apply_color, apply_effect, copy_clip_settings, export_project (only when the user asks to export), undo.
- The user's expected editing style is in [ugc-cut-style](ugc-cut-style.md).
