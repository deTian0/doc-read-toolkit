# -*- coding: utf-8 -*-
"""Transcribe 思投社 mp3 with faster-whisper and write text + timed transcript."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel


def fmt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    return f"{m:02d}:{s:02d}.{ms:03d}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    parser.add_argument("--compute-type", default="auto")
    args = parser.parse_args()

    audio = args.audio.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    device = args.device
    compute_type = args.compute_type
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    print(f"audio={audio}", flush=True)
    print(f"model={args.model} device={device} compute_type={compute_type}", flush=True)

    t0 = time.time()
    try:
        model = WhisperModel(args.model, device=device, compute_type=compute_type)
    except Exception as exc:
        if device != "cpu":
            print(f"GPU load failed ({exc}); falling back to CPU int8", flush=True)
            device, compute_type = "cpu", "int8"
            model = WhisperModel(args.model, device=device, compute_type=compute_type)
        else:
            raise

    segments_iter, info = model.transcribe(
        str(audio),
        language="zh",
        task="transcribe",
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        condition_on_previous_text=True,
    )
    print(
        f"detected language={info.language} prob={info.language_probability:.3f} "
        f"duration={info.duration:.1f}s",
        flush=True,
    )

    segments = []
    texts = []
    for seg in segments_iter:
        item = {
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        }
        segments.append(item)
        texts.append(item["text"])
        print(f"[{fmt_ts(seg.start)} -> {fmt_ts(seg.end)}] {item['text']}", flush=True)

    full_text = "\n".join(t for t in texts if t).strip() + "\n"
    stem = audio.stem
    txt_path = out_dir / f"{stem}.txt"
    timed_path = out_dir / f"{stem}.timed.txt"
    json_path = out_dir / f"{stem}.json"

    txt_path.write_text(full_text, encoding="utf-8")
    timed_lines = [
        f"[{fmt_ts(s['start'])} -> {fmt_ts(s['end'])}] {s['text']}" for s in segments if s["text"]
    ]
    timed_path.write_text("\n".join(timed_lines) + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "audio": str(audio),
                "model": args.model,
                "device": device,
                "compute_type": compute_type,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "elapsed_sec": time.time() - t0,
                "segments": segments,
                "text": full_text,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"wrote {txt_path}", flush=True)
    print(f"wrote {timed_path}", flush=True)
    print(f"wrote {json_path}", flush=True)
    print(f"elapsed={time.time() - t0:.1f}s chars={len(full_text)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
