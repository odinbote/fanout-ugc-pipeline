# Ugc Workflow

Agreed Oct 24 2026. When the user gives a SCRIPT and a FIRST FRAME:

1. **Trial clip first**: generate ONLY clip 1 with ugc_pipeline.py --only-clip 1 (same first frame, no gate, duration by word count, ElevenLabs voice swap). Send it and ask for feedback. Wait.
2. **Apply the trial feedback** (prompt wording, beat, pace, duration, voice) to the pipeline, then **generate the rest** with --start-at 2 (clip 1 is kept and not re-swapped). If the feedback changes clip 1 itself, regenerate it too. Rules in [ugc-pipeline-fanout](ugc-pipeline-fanout.md).
3. **Deliver the full set for review once**: send all clips and ask the user to review. Do not review them myself, do not touch Palmier yet. **Wait for "go ahead"** (or targeted feedback: regenerate only the clips they name, deliver again, wait).
4. **On "go ahead", edit in Palmier Pro** with palmier_assemble.py --project "<script name>" --deliver-dir "~/Documents/fanout/AI ugc/<script name>" --name "<cut name>" --files <clips in script order>: creates a NEW Palmier project per script (720p 9:16 24 fps), imports the clips, builds the timeline, places clips back-to-back, in-point on first-word onset, out-point just after the audible end of the last word, internal pauses over 0.6 s tightened to ~0.2 s, hard cuts, no fades, and the Timeline 1 grade stack on every clip. Style details in [ugc-cut-style](ugc-cut-style.md), app access in [palmier-pro-mcp](palmier-pro-mcp.md).
5. The script then closes the project (which saves it) and moves the .palmier package into the script's folder under ~/Documents/fanout/AI ugc, then reopens it from there. Report the timeline (clip table, duration) and the project path, and stop. No export unless asked; the user does grading changes, captions and delivery themselves.

**Why:** the user asked for exactly this sequence ("after generating the clips ... once ask me to review ... after the review when I say go ahead use Palmier Pro to edit exactly like this").
**How to apply:** always do the one-clip trial before the full set, never skip the review pause, never assemble before "go ahead", and always use the 720p timeline and the exact grade from Timeline 1.
