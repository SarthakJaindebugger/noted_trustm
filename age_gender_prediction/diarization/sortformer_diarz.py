#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================
# EARLY PATCH for huggingface_hub (use_auth_token → token)
# ============================================================
import os
import sys
import huggingface_hub

_original_hf_download = huggingface_hub.hf_hub_download
def _patched_hf_download(*args, **kwargs):
    if 'use_auth_token' in kwargs:
        kwargs['token'] = kwargs.pop('use_auth_token')
    return _original_hf_download(*args, **kwargs)
huggingface_hub.hf_hub_download = _patched_hf_download

if hasattr(huggingface_hub, 'snapshot_download'):
    _original_snapshot = huggingface_hub.snapshot_download
    def _patched_snapshot(*args, **kwargs):
        if 'use_auth_token' in kwargs:
            kwargs['token'] = kwargs.pop('use_auth_token')
        return _original_snapshot(*args, **kwargs)
    huggingface_hub.snapshot_download = _patched_snapshot

print("Applied huggingface_hub patch (use_auth_token → token).")

# ============================================================
# Now import the rest
# ============================================================
import time
import json
import argparse
import glob
import tempfile
from pathlib import Path
import torch
import librosa
import soundfile as sf
from nemo.collections.asr.models import SortformerEncLabelModel
from pyannote.core import Segment, Annotation
from pyannote.metrics.diarization import DiarizationErrorRate

# ============================================================
# HARDCODED PATHS
# ============================================================
AUDIO_DIR = Path("/scratch/work/jains6/noted/noted-main/age_gender_prediction/diarization/callhome/audio")
RTTM_DIR  = Path("/scratch/work/jains6/noted/noted-main/age_gender_prediction/diarization/callhome/rttm")
OUTPUT_DIR = Path("./sortformer_output")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SAMPLE_RATE = 16000
SORTFORMER_MODEL = "nvidia/diar_sortformer_4spk-v1"

# ============================================================
# GPU HELPERS
# ============================================================
def synchronize_cuda():
    if torch.cuda.is_available():
        torch.cuda.synchronize()

def reset_gpu_memory_stats():
    if not torch.cuda.is_available():
        return
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()

def get_peak_gpu_memory():
    if not torch.cuda.is_available():
        return 0.0, 0.0
    torch.cuda.synchronize()
    peak_alloc = torch.cuda.max_memory_allocated() / (1024 ** 3)
    peak_res = torch.cuda.max_memory_reserved() / (1024 ** 3)
    return peak_alloc, peak_res

def get_current_gpu_memory():
    if not torch.cuda.is_available():
        return 0.0, 0.0
    torch.cuda.synchronize()
    allocated = torch.cuda.memory_allocated() / (1024 ** 3)
    reserved = torch.cuda.memory_reserved() / (1024 ** 3)
    return allocated, reserved

# ============================================================
# AUDIO / RTTM UTILITIES
# ============================================================
def get_audio_duration(path):
    return float(librosa.get_duration(path=path))

def read_rttm(rttm_path):
    ann = Annotation()
    with open(rttm_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 8:
                continue
            start = float(parts[3])
            dur = float(parts[4])
            speaker = parts[7]
            seg = Segment(start, start + dur)
            ann[seg] = speaker
    return ann

def write_rttm(annotation, file_id, output_path):
    with open(output_path, 'w') as f:
        for segment, track, speaker in annotation.itertracks(yield_label=True):
            start = segment.start
            dur = segment.end - segment.start
            f.write(f"SPEAKER {file_id} 1 {start:.3f} {dur:.3f} <NA> <NA> {speaker} <NA>\n")

def convert_to_mono_temp(audio_path, target_sr=SAMPLE_RATE):
    audio, sr = librosa.load(audio_path, sr=target_sr, mono=True)
    fd, temp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(temp_path, audio, target_sr, subtype="PCM_16")
    return temp_path

def get_all_files(audio_dir, rttm_dir):
    audio_files = sorted(glob.glob(str(audio_dir / "*.wav")))
    if not audio_files:
        raise ValueError(f"No .wav files found in {audio_dir}")
    file_list = []
    for af in audio_files:
        base = os.path.splitext(os.path.basename(af))[0]
        rttm_path = rttm_dir / (base + ".rttm")
        if not rttm_path.exists():
            print(f"Warning: RTTM for {base} not found, skipping.")
            continue
        dur = get_audio_duration(af)
        file_list.append((af, str(rttm_path), dur))
    total_dur = sum(d for _, _, d in file_list)
    print(f"Found {len(file_list)} audio files, total duration {total_dur/3600:.2f} hours")
    return file_list

# ============================================================
# SORTFORMER MODEL
# ============================================================
_model = None
def get_sortformer_model():
    global _model
    if _model is None:
        print("Loading Sortformer model...")
        _model = SortformerEncLabelModel.from_pretrained(SORTFORMER_MODEL)
        _model.eval()
        if torch.cuda.is_available():
            _model = _model.cuda()
        print("Sortformer loaded.")
    return _model

def parse_sortformer_output(predicted_segments):
    """
    Convert Sortformer output to pyannote Annotation.
    Handles string timestamps, unknown speakers, and various formats.
    """
    ann = Annotation()
    if predicted_segments is None:
        return ann

    # If it's a dict, try to extract the list of segments
    if isinstance(predicted_segments, dict):
        for key in ['segments', 'diarization', 'result', 'predicted_segments']:
            if key in predicted_segments:
                predicted_segments = predicted_segments[key]
                break
        else:
            # Maybe it's a single segment dict?
            if "start" in predicted_segments and "end" in predicted_segments and "speaker" in predicted_segments:
                predicted_segments = [predicted_segments]
            else:
                print(f"  Warning: Unknown dict format: {predicted_segments.keys()}")
                return ann

    # Now iterate over segments (list or tuple)
    if not isinstance(predicted_segments, (list, tuple)):
        print("  Warning: Unexpected output type; skipping.")
        return ann

    for seg in predicted_segments:
        try:
            # -------- Extract start, end, speaker --------
            if isinstance(seg, dict):
                start = seg.get("start")
                end = seg.get("end")
                speaker = seg.get("speaker")
                # Some keys might have underscores
                if start is None:
                    start = seg.get("start_time")
                if end is None:
                    end = seg.get("end_time")
                if speaker is None:
                    speaker = seg.get("speaker_id") or seg.get("label")
            elif isinstance(seg, (list, tuple)) and len(seg) >= 3:
                # Try to guess the order; prefer numeric values
                numeric_vals = []
                string_vals = []
                for val in seg:
                    try:
                        numeric_vals.append(float(val))
                    except (TypeError, ValueError):
                        string_vals.append(str(val))
                if len(numeric_vals) >= 2:
                    # Use the first two numeric as start/end (or min/max)
                    start = min(numeric_vals[:2])
                    end = max(numeric_vals[:2])
                    speaker = string_vals[0] if string_vals else "UNKNOWN"
                else:
                    # Fallback: assume (start, end, speaker)
                    start = float(seg[0])
                    end = float(seg[1])
                    speaker = str(seg[2]) if len(seg) > 2 else "UNKNOWN"
            else:
                # Cannot parse this segment
                continue

            # -------- Convert to float if string --------
            if isinstance(start, str):
                start = float(start)
            if isinstance(end, str):
                end = float(end)
            if speaker is None:
                speaker = "UNKNOWN"
            else:
                speaker = str(speaker)

            # -------- Skip invalid or unknown speakers --------
            if speaker.lower() in ["unk", "unknown", "none", ""]:
                continue
            if start >= end or start < 0 or end <= 0:
                continue

            ann[Segment(start, end)] = speaker

        except (ValueError, TypeError, KeyError) as e:
            print(f"  Warning: Skipping segment {seg} (error: {e})")
            continue

    return ann

def run_sortformer(audio_path, rttm_ref_path, output_dir, file_id):
    model = get_sortformer_model()
    temp_path = convert_to_mono_temp(audio_path)
    try:
        reset_gpu_memory_stats()
        before_alloc, _ = get_current_gpu_memory()

        start_time = time.perf_counter()
        # Sortformer.diarize expects audio path or list of paths
        raw_output = model.diarize(audio=temp_path, batch_size=1)
        synchronize_cuda()
        inference_time = time.perf_counter() - start_time

        peak_alloc, peak_res = get_peak_gpu_memory()
        after_alloc, _ = get_current_gpu_memory()

        # Parse the output
        ann = parse_sortformer_output(raw_output)

        hyp_path = os.path.join(output_dir, f"{file_id}.rttm")
        write_rttm(ann, file_id, hyp_path)

        ref_ann = read_rttm(rttm_ref_path)
        metric = DiarizationErrorRate()
        der = metric(ref_ann, ann, detailed=True)
        der_value = der.get('diarization_error_rate', 1.0)

        speakers = set()
        for seg, _, spk in ann.itertracks(yield_label=True):
            speakers.add(spk)

        return {
            "file": audio_path,
            "file_id": file_id,
            "der": der_value,
            "inference_time_sec": inference_time,
            "num_speakers": len(speakers),
            "peak_vram_allocated_gb": peak_alloc,
            "peak_vram_reserved_gb": peak_res,
            "gpu_allocated_before_gb": before_alloc,
            "gpu_allocated_after_gb": after_alloc,
            "hypothesis_rttm": hyp_path,
            "reference_rttm": rttm_ref_path,
        }
    finally:
        try:
            os.remove(temp_path)
        except:
            pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio_dir", type=str, default=str(AUDIO_DIR))
    parser.add_argument("--rttm_dir", type=str, default=str(RTTM_DIR))
    parser.add_argument("--output_dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    audio_dir = Path(args.audio_dir)
    rttm_dir = Path(args.rttm_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not audio_dir.exists():
        print(f"ERROR: Audio directory {audio_dir} does not exist.")
        sys.exit(1)
    if not rttm_dir.exists():
        print(f"ERROR: RTTM directory {rttm_dir} does not exist.")
        sys.exit(1)

    file_list = get_all_files(audio_dir, rttm_dir)
    if not file_list:
        print("No files found.")
        sys.exit(1)

    # Preload model
    try:
        _ = get_sortformer_model()
    except Exception as e:
        print(f"FATAL: Could not load Sortformer model: {e}")
        sys.exit(1)

    results = []
    total_inference_time = 0.0
    total_der = 0.0

    print("\n" + "="*70)
    print("SORTFORMER DIARIZATION ON CALLHOME DATASET")
    print("="*70)
    print(f"Device: {DEVICE}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Total VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.3f} GB")

    for audio_path, rttm_path, dur in file_list:
        file_id = os.path.splitext(os.path.basename(audio_path))[0]
        print(f"\nProcessing: {file_id} ({dur:.2f}s)")
        try:
            res = run_sortformer(audio_path, rttm_path, str(output_dir), file_id)
            results.append(res)
            total_inference_time += res["inference_time_sec"]
            total_der += res["der"]
            print(f"  DER: {res['der']:.4f}")
            print(f"  Time: {res['inference_time_sec']:.3f}s")
            print(f"  Peak VRAM allocated: {res['peak_vram_allocated_gb']:.3f} GB")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"file": audio_path, "file_id": file_id, "error": str(e)})

    num_ok = sum(1 for r in results if "der" in r)
    if num_ok > 0:
        avg_der = total_der / num_ok
        avg_time = total_inference_time / num_ok
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Total audio files processed: {len(file_list)}")
        print(f"Successful: {num_ok}")
        print(f"Average DER: {avg_der:.4f}")
        print(f"Total inference time: {total_inference_time:.3f}s")
        print(f"Average inference time per file: {avg_time:.3f}s")
        peak_alloc_all = max([r.get("peak_vram_allocated_gb", 0) for r in results if "peak_vram_allocated_gb" in r])
        print(f"Max peak VRAM allocated: {peak_alloc_all:.3f} GB")
    else:
        print("No successful runs.")

    if args.json:
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()