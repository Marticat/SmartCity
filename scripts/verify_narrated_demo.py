"""Decode the completed MP4 and verify duration, codecs and audible narration."""
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def main():
    video = ROOT / "demo" / "QADAM-demo-narrated.mp4"
    result = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-xerror", "-i", str(video),
        "-af", "volumedetect", "-f", "null", "-",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace", check=True)
    log = result.stderr
    match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", log)
    if not match:
        raise ValueError("No MP4 duration")
    hours, minutes, seconds = map(float, match.groups())
    duration = hours * 3600 + minutes * 60 + seconds
    volume = re.search(r"mean_volume:\s*([-\d.]+) dB", log)
    maximum = re.search(r"max_volume:\s*([-\d.]+) dB", log)
    if not volume or not maximum or float(maximum.group(1)) <= -30:
        raise ValueError("Narration is silent or too quiet")
    expected = json.loads((ROOT / "demo" / "video-check.json").read_text(encoding="utf-8"))
    if abs(duration - expected["duration"]) > 0.15:
        raise ValueError("Narrated video was truncated")
    if "Video: h264" not in log or "Audio: aac" not in log or "1440x1000" not in log:
        raise ValueError("Unexpected delivery codecs or dimensions")
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "complete_decode": True,
        "duration_seconds": duration, "width": 1440, "height": 1000,
        "video_codec": "H.264", "audio_codec": "AAC", "synthetic_voice": True,
        "mean_volume_db": float(volume.group(1)), "max_volume_db": float(maximum.group(1)),
        "bytes": video.stat().st_size, "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
    }
    (ROOT / "demo" / "narrated-video-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
