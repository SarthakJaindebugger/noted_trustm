#!/usr/bin/env python3
"""
Pyannote diarization on Callhome dataset.
Fixed HF download argument issue.
"""




import os
import sys

# Force patch before any other import that might use hf_hub_download
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


import os, sys, time, json, argparse, glob
from pathlib import Path
import torch, librosa
from pyannote.audio import Pipeline
from pyannote.core import Segment, Annotation
from pyannote.metrics.diarization import DiarizationErrorRate

# ============================================================
# HARDCODED PATHS
# ============================================================
AUDIO_DIR = Path("/scratch/work/jains6/noted/noted-main/age_gender_prediction/diarization/callhome/audio")
RTTM_DIR  = Path("/scratch/work/jains6/noted/noted-main/age_gender_prediction/diarization/callhome/rttm")
OUTPUT_DIR = Path("./pyannote_output")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SAMPLE_RATE = 16000
PYANNOTE_MODEL = "pyannote/speaker-diarization-3.1"

# ============================================================
# PATCH huggingface_hub TO FIX 'use_auth_token' ISSUE
# ============================================================
def patch_hf_download():
    try:
        import huggingface_hub
        from huggingface_hub import hf_hub_download
        original_hf_hub_download = hf_hub_download

        def patched_hf_hub_download(*args, **kwargs):
            # If 'use_auth_token' is in kwargs, move it to 'token'
            if 'use_auth_token' in kwargs:
                kwargs['token'] = kwargs.pop('use_auth_token')
            return original_hf_hub_download(*args, **kwargs)

        huggingface_hub.hf_hub_download = patched_hf_hub_download
        print("Applied huggingface_hub patch (use_auth_token → token).")
    except Exception as e:
        print(f"WARNING: Could not patch hf_hub_download: {e}")

# Apply patch BEFORE importing pyannote.audio (it may import huggingface_hub)
patch_hf_download()

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
# PYTORCH 2.6+ COMPATIBILITY
# ============================================================
def patch_torch_for_pyannote():
    try:
        if hasattr(torch, "serialization"):
            add_safe_globals = getattr(torch.serialization, "add_safe_globals", None)
            if callable(add_safe_globals):
                try:
                    add_safe_globals([torch.torch_version.TorchVersion])
                except Exception:
                    pass
    except Exception:
        pass
    if getattr(torch.load, "_pyannote_patch", False):
        return
    original_torch_load = torch.load
    def patched_torch_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return original_torch_load(*args, **kwargs)
    patched_torch_load._pyannote_patch = True
    torch.load = patched_torch_load

# ============================================================
# AUDIO / RTTM UTILITIES
# ============================================================
def get_audio_duration(path):
    return float(librosa.get_duration(path=path))

def load_audio(file_path, target_sr=SAMPLE_RATE):
    audio, sr = librosa.load(file_path, sr=target_sr, mono=True)
    return audio, sr

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
# PYANNOTE PIPELINE (with error handling)
# ============================================================
_pipeline = None
def get_pipeline():
    global _pipeline
    if _pipeline is None:
        patch_torch_for_pyannote()
        from pyannote.audio import Pipeline
        print("Loading Pyannote pipeline...")
        try:
            _pipeline = Pipeline.from_pretrained(PYANNOTE_MODEL)
            if torch.cuda.is_available():
                _pipeline.to(torch.device("cuda"))
            print("Pyannote pipeline loaded successfully.")
        except Exception as e:
            print(f"ERROR loading Pyannote pipeline: {e}")
            raise RuntimeError(f"Failed to load Pyannote pipeline: {e}")
    return _pipeline

def run_pyannote(audio_path, rttm_ref_path, output_dir, file_id):
    pipeline = get_pipeline()
    audio, sr = load_audio(audio_path)
    waveform = torch.from_numpy(audio).float().unsqueeze(0)

    reset_gpu_memory_stats()
    before_alloc, _ = get_current_gpu_memory()

    start_time = time.perf_counter()
    diarization = pipeline({"waveform": waveform, "sample_rate": sr})
    synchronize_cuda()
    inference_time = time.perf_counter() - start_time

    peak_alloc, peak_res = get_peak_gpu_memory()
    after_alloc, _ = get_current_gpu_memory()

    if hasattr(diarization, "speaker_diarization"):
        ann = diarization.speaker_diarization
    else:
        ann = diarization

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

    # Validate paths
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

    # Try loading the pipeline once before processing any files
    try:
        _ = get_pipeline()
    except Exception as e:
        print(f"FATAL: Could not load Pyannote pipeline: {e}")
        sys.exit(1)

    results = []
    total_inference_time = 0.0
    total_der = 0.0

    print("\n" + "="*70)
    print("PYANNOTE DIARIZATION ON CALLHOME DATASET")
    print("="*70)
    print(f"Device: {DEVICE}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Total VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.3f} GB")

    for audio_path, rttm_path, dur in file_list:
        file_id = os.path.splitext(os.path.basename(audio_path))[0]
        print(f"\nProcessing: {file_id} ({dur:.2f}s)")
        try:
            res = run_pyannote(audio_path, rttm_path, str(output_dir), file_id)
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