"""Mux real recorded UI with explicitly synthetic local narration and SRT.

Optional delivery helper: pip install imageio-ffmpeg==0.6.0
On Windows run powershell -File demo/narrate.ps1 after recording/verifying video.
"""
import json
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def timestamp(seconds):
    value = round(seconds * 1000)
    return f"{value // 3600000:02}:{value // 60000 % 60:02}:{value // 1000 % 60:02},{value % 1000:03}"


def main():
    demo = ROOT / "demo"
    metadata = json.loads((demo / "video-check.json").read_text(encoding="utf-8"))
    recording = json.loads((demo / "recording.json").read_text(encoding="utf-8"))
    spec = json.loads((demo / "narration.json").read_text(encoding="utf-8"))
    cues = recording["captions"]
    if len(cues) != len(spec["segments"]):
        raise ValueError("Recording captions changed; review narration before muxing")
    rate, frame_bytes = 22050, 2
    duration = metadata["duration"]
    soundtrack = bytearray(round(duration * rate) * frame_bytes)
    segments, subtitles = [], []
    for index, (cue, text) in enumerate(zip(cues, spec["segments"])):
        with wave.open(str(ROOT / "artifacts" / "narration" / f"{index}.wav"), "rb") as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (rate, 1, 2):
                raise ValueError("Unexpected narration audio format")
            audio = wav.readframes(wav.getnframes())
        start = float(cue["at_seconds"])
        length = len(audio) / (rate * frame_bytes)
        end = start + length
        available_end = float(cues[index + 1]["at_seconds"]) - 0.3 if index + 1 < len(cues) else duration - 0.3
        if end > available_end:
            raise ValueError(f"Narration segment {index} overlaps next scene by {end-available_end:.2f}s; shorten text")
        offset = round(start * rate) * frame_bytes
        soundtrack[offset:offset + len(audio)] = audio
        segments.append({"start_seconds": round(start, 3), "end_seconds": round(end, 3), "text": text})
        subtitles.append(f"{index+1}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n")
    audio_path = ROOT / "artifacts" / "narration" / "soundtrack.wav"
    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(soundtrack)
    output = demo / "QADAM-demo-narrated.mp4"
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(demo / "QADAM-demo.webm"), "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
        "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "-shortest", str(output),
    ], check=True)
    (demo / "QADAM-ru.srt").write_text("\n".join(subtitles), encoding="utf-8")
    (demo / "narration-check.json").write_text(json.dumps({
        "synthetic_voice": True, "voice": spec["voice"], "source_video": "QADAM-demo.webm",
        "source_recorded_at": recording["recorded_at"], "duration_seconds": duration,
        "audio_overlap": False, "segments": segments, "output": output.name,
        "video_content": "Actual UI recording; no recommendation responses modified",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": output.name, "synthetic_voice": True, "segments": len(segments), "duration": duration}))


if __name__ == "__main__":
    main()
