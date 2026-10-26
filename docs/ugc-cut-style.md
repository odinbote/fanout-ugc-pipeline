# Ugc Cut Style

The user's Palmier Pro cut of the Fanout UGC clips (Oct 24 2026, project "Untitled Project", timeline 720x1280 @ 24 fps) is the reference style for all talking-head UGC edits.

**Cut rules (learned from the timeline):**
- In-point sits exactly on the first word's onset: zero handle, no air before speech. Any breath, lip noise or stray sound before the first word is cut (clip 2 in at 0.42 s skipped a pre-breath).
- Out-point sits at the perceived end of the last word, 0 to 0.1 s of air at most. Trailing breath, laugh, sibilant tail or hold-and-smile after the line is cut (clip 4 dropped a laugh at 3.1 s; clip 5 trimmed the "sh" tail; clip 1 cut on the post-word breath). Whisper word-end timestamps are padded; cut to the audible word end, not the transcript end.
- Clips sit back-to-back in script order on V1 with linked audio on A1. Hard cuts only: no audio fades, no crossfades, no transitions, no markers.
- Each generated clip's unused hold time after the line is removed in the edit, so generated clips can carry a little tail; it will be trimmed.

**Grade stack applied identically to every clip:** contrast 0.956, highlights -0.331, shadows 0, vibrance +0.106, grain amount 0.189 size 1.5 (sharpen present at 0). Copy this stack to any new clip added to the timeline.

**Why:** The user said this cut and edit is perfect and asked me to learn it, after I had flagged the tight in/out points and the lack of fades as issues. Those are deliberate choices, not mistakes.

**How to apply:** When trimming or assembling UGC clips (in Palmier via [palmier-pro-mcp](palmier-pro-mcp.md) or with ffmpeg), cut to speech edges with zero handles, strip pre/post breaths and tails, no fades, apply the grade stack above, and do not suggest fades or looser handles. Pair with [ugc-pipeline-fanout](ugc-pipeline-fanout.md) for how the clips are generated.
