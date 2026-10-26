# Fanout UGC pipeline

Scripts and notes for producing short UGC-style talking-head ads for [Fanout](https://fanout.sh):
split a script into clips, generate each clip with **Google Veo 3.1 Fast** (via OpenRouter) from one
first-frame image, unify the voice with **ElevenLabs speech-to-speech**, then assemble and trim the
clips in **Palmier Pro** through its local MCP server.

## Layout

| path | what |
|---|---|
| `pipeline/ugc_pipeline.py` | main pipeline: split → prompts → Veo clips → (optional gate) → ElevenLabs voice swap → mux |
| `pipeline/regen_feedback.py` | example of regenerating specific clips with per-clip prompt tweaks |
| `palmier/palmier_mcp.py` | minimal MCP streamable-HTTP client for Palmier Pro (`127.0.0.1:19789/mcp`) |
| `palmier/palmier_assemble.py` | builds a 720x1280 @ 24 fps timeline in Palmier: speech-edge trims, hard cuts, fixed grade |
| `experiments/veo_first_frame/` | the one-off Veo scripts the pipeline grew out of (v1–v8) |
| `scripts/` | the ad scripts used so far |
| `docs/` | the working rules: workflow, cut style, hook rule, delivery reference, pipeline settings |
| `voice_id.txt` | the pinned ElevenLabs voice ID (premade "Sarah") |

Generated media (clips, first frames, Palmier projects) is not in the repo; see `.gitignore`.

## Requirements

- Python 3.9+, `pip install -r requirements.txt`
- `ffmpeg` / `ffprobe` on PATH
- Environment variables: `OPENROUTER_API_KEY`, `ELEVENLABS_API_KEY`
- Palmier Pro running with a project open (for the assemble step)

## Workflow (short)

1. **Trial**: `python3 pipeline/ugc_pipeline.py --first-frame frame.png --script-file script.txt --outdir out --room "<room>" --no-gate --same-first-frame --only-clip 1`
2. Apply feedback, then generate the rest: same command with `--start-at 2`.
3. Review the full set.
4. **Assemble**: `python3 palmier/palmier_assemble.py --project "<script name>" --deliver-dir "<folder>" --name "<cut>" --files out/clip_0*_final.mp4`

Details, and the reasoning behind each rule, are in `docs/`.

## Key pipeline rules

- One first frame for every clip (no chaining).
- Clip length by word count: ≤9 words 4 s, 10–14 words 6 s, 15+ words 8 s (Veo only offers 4/6/8).
- URLs written phonetically for the voice model ("Fanout dot ess aitch").
- Hook (clip 1) is lively but natural; body clips are expressive with continuous hand gestures.
- Same seed across clips; vary the seed on re-rolls (same seed = identical video).
- No post speed-up; pace is controlled through prompt wording and clip length.
