import base64, os, subprocess, time, requests

API = "https://openrouter.ai/api/v1"
KEY = os.environ["OPENROUTER_API_KEY"]
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

FIRST_FRAME_URL = os.environ.get("FIRST_FRAME_URL")
if not FIRST_FRAME_URL:
    with open("frame1.png", "rb") as f:
        FIRST_FRAME_URL = "data:image/png;base64," + base64.b64encode(f.read()).decode()

PROMPT = '''
[Image1] is the first frame. Same woman, hair tied back with the ponytail over her
left shoulder, small gold hoops, sage-grey cap-sleeve tee, grey sweatpants, sitting
cross-legged on the bed, white blinds behind her, lamp off, same flat overcast
daylight on her face, no shine. Arm's-length front-camera handheld, slight natural
sway, framing drifts a little, no zoom, no push-in, no cuts.

Preserve the exact skin texture, freckles, under-eye shadow and matte finish of
[Image1] throughout — skin does not get smoother, brighter or warmer at any point.
Head stays nearly square to the camera, no more than a slight tilt, no three-quarter
turns.

Subtle, relaxed delivery — small mouth movements, jaw relaxed, eyebrows mostly still.
Not performing. Like talking to a friend. Natural blinks. Only her mouth moves when
she speaks.

She moves the way people do on a call — small weight shifts, a breath, a look away
and back. Her hands are not fixed: the right hand comes off her jaw within the first
second and gestures loosely while she talks, the left hand fidgets with the duvet or
rests on her knee.

One small eye-roll at the start, then eye contact with a guilty half-smile.
She says "This feels like cheating... but it works."
Her right hand drops from her jaw into a small shrug on "cheating" and stays down in
her lap.
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
open("out4.mp4", "wb").write(d.content)
print("saved out4.mp4")

