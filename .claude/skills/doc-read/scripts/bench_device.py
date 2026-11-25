#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quick CPU vs GPU bench for ASR / OCR used by doc-read."""

from __future__ import annotations

import argparse
import ctypes
import os
import time
from pathlib import Path


def ensure_cuda_dll_path() -> Path | None:
    # Local conda env ships cublas under Library/bin.
    candidates: list[Path] = []
    py = os.environ.get("DOC_READ_PYTHON")
    if py:
        candidates.append(Path(py).resolve().parent / "Library" / "bin")
    root = os.environ.get("DOC_READ_ROOT")
    if root:
        candidates.append(Path(root) / ".conda" / "doc-read" / "Library" / "bin")
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / ".conda" / "doc-read" / "Library" / "bin")
    seen: set[Path] = set()
    for bin_dir in candidates:
        try:
            bin_dir = bin_dir.resolve()
        except OSError:
            continue
        if bin_dir in seen:
            continue
        seen.add(bin_dir)
        dll = bin_dir / "cublas64_12.dll"
        if dll.exists():
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(str(bin_dir))
            except Exception:
                pass
            try:
                ctypes.WinDLL(str(dll))
                print(f"[cuda] cublas loadable from {bin_dir}")
            except Exception as e:
                print(f"[cuda] cublas present but not loadable: {e}")
            return bin_dir
    print("[cuda] cublas64_12.dll not found in local env")
    return None


def bench_asr(audio: Path, device: str, compute_type: str) -> dict:
    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    model = WhisperModel("small", device=device, compute_type=compute_type)
    t_load = time.perf_counter() - t0
    t1 = time.perf_counter()
    segments, info = model.transcribe(str(audio), language="zh", vad_filter=True)
    texts = [s.text.strip() for s in segments]
    t_infer = time.perf_counter() - t1
    duration = float(getattr(info, "duration", 0) or 0)
    return {
        "task": "asr",
        "device": device,
        "compute_type": compute_type,
        "load_s": round(t_load, 2),
        "infer_s": round(t_infer, 2),
        "total_s": round(t_load + t_infer, 2),
        "audio_s": round(duration, 2),
        "segments": len(texts),
        "chars": sum(len(t) for t in texts),
        "rtf": round(t_infer / max(duration, 1e-6), 3),
    }


def bench_ocr(image: Path, rounds: int = 3) -> dict:
    from rapidocr_onnxruntime import RapidOCR
    import onnxruntime as ort

    providers = ort.get_available_providers()
    ocr = RapidOCR()

    def once():
        t0 = time.perf_counter()
        result, elapse = ocr(str(image))
        dt = time.perf_counter() - t0
        lines = [item[1] for item in (result or []) if len(item) >= 2]
        return dt, elapse, len(lines)

    once()  # warmup
    walls = []
    last = None
    for _ in range(rounds):
        last = once()
        walls.append(last[0])
    return {
        "task": "ocr",
        "providers": providers,
        "image": str(image),
        "image_bytes": image.stat().st_size,
        "rounds": rounds,
        "avg_s": round(sum(walls) / len(walls), 3),
        "min_s": round(min(walls), 3),
        "max_s": round(max(walls), 3),
        "lines": last[1] if False else last[2],
        "engine_elapse": last[1],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asr", type=Path, help="audio file for ASR bench")
    parser.add_argument("--ocr", type=Path, help="image file for OCR bench")
    parser.add_argument("--asr-device", default="cuda", choices=["cpu", "cuda"])
    parser.add_argument("--compute-type", default="float16")
    args = parser.parse_args()

    ensure_cuda_dll_path()

    if args.asr:
        print(f"=== ASR {args.asr_device}/{args.compute_type} ===", flush=True)
        try:
            result = bench_asr(args.asr, args.asr_device, args.compute_type)
            print("RESULT", result, flush=True)
        except Exception as e:
            print(f"FAILED {type(e).__name__}: {e}", flush=True)
            if args.asr_device == "cuda" and args.compute_type != "int8_float16":
                print("=== ASR cuda/int8_float16 fallback ===", flush=True)
                result = bench_asr(args.asr, "cuda", "int8_float16")
                print("RESULT", result, flush=True)
            else:
                raise

    if args.ocr:
        print("=== OCR ===", flush=True)
        print("RESULT", bench_ocr(args.ocr), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
