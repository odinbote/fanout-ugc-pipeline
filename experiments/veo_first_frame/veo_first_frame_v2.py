import base64, os, subprocess, time, requests

API = "https://openrouter.ai/api/v1"
KEY = os.environ["OPENROUTER_API_KEY"]
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

FIRST_FRAME_URL = os.environ.get("FIRST_FRAME_URL")
if not FIRST_FRAME_URL:
    with open("frame1.png", "rb") as f:
        FIRST_FRAME_URL = "data:image/png;base64," + base64.b64encode(f.read()).decode()

PROMPT = '''
The provided image is the first frame; continue from it exactly. Same woman, hair
tied back with the ponytail over her left shoulder, small gold hoops, sage-grey
cap-sleeve tee, grey sweatpants, sitting cross-legged on the bed, white blinds behind
her, lamp off, flat overcast daylight on her face, matte skin, no shine. Front-facing
phone camera held at arm's length, slight handheld sway, framing drifts a little.
Static lens, no zoom, no push-in, single continuous shot, no cuts.

Keep her exact face, skin texture, freckles and under-eye shadow throughout — the
skin never gets smoother, brighter or warmer. Head stays nearly square to the camera,
slight tilts only, no three-quarter turns.

Subtle, relaxed delivery: small mouth movements, relaxed jaw, eyebrows mostly still,
natural blinks. Not performing, like talking to a friend on FaceTime. She moves the
way people do on a call — small weight shifts, a breath, a look away and back. Her
hands are not fixed and move loosely while she talks.
'''.strip()

body = {
    "model": "google/veo-3.1",
    "prompt": PROMPT,
    "duration": 8,
    "resolution": "1080p",
    "aspect_ratio": "9:16",
    "frame_images": [{
        "type": "image_url",
        "image_url": {"url": FIRST_FRAME_URL},
        "frame_type": "first_frame",
    }],
}

r = requests.post(f"{API}/videos", headers=HEADERS, json=body, timeout=120)
if not r.ok:
    print("SUBMIT ERROR", r.status_code, r.text); raise SystemExit(1)
job = r.json()
job_id = job["id"]
polling_url = job.get("polling_url", f"{API}/videos/{job_id}")
print("submitted job:", job_id)

status = job.get("status", "pending")
for _ in range(90):
    if status in ("completed", "failed", "cancelled", "expired"):
        break
    time.sleep(10)
    s = requests.get(polling_url, headers=HEADERS, timeout=30)
    s.raise_for_status()
    js = s.json()
    status = js.get("status", status)
    print("status:", status)
    if status == "failed":
        print(js)

if status != "completed":
    raise SystemExit(f"video generation {status}")

d = requests.get(f"{API}/videos/{job_id}/content?index=0", headers=HEADERS, timeout=600)
d.raise_for_status()
open("out2.mp4", "wb").write(d.content)
print("saved out2.mp4")

subprocess.run(["ffmpeg", "-y", "-i", "out2.mp4", "-an", "-c:v", "copy", "out2_silent.mp4"], check=False)
print("saved out2_silent.mp4")
