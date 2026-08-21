# -*- coding: utf-8 -*-

"""
Stage 1 · Input Raw Audio -> Diarized/Transcribed JSON
=========================================================
Runs NVIDIA Sortformer speaker diarization + Whisper ASR.

Diarization model:
    nvidia/diar_sortformer_4spk-v1

ASR:
    faster-whisper
"""

# ============================================================
# Hugging Face authentication + PyTorch serialization patch
# ============================================================

import os
import functools
import torch


# ---- Hugging Face token ----
# Priority:
# 1. HF_TOKEN environment variable
# 2. HUGGINGFACEHUB_API_TOKEN
# 3. HuggingFace cached login

HF_TOKEN = (
    os.getenv("HF_TOKEN")
    or os.getenv("HUGGINGFACEHUB_API_TOKEN")
)


try:
    from huggingface_hub import login, HfFolder

    if not HF_TOKEN:
        HF_TOKEN = HfFolder.get_token()

    if HF_TOKEN:
        login(
            token=HF_TOKEN,
            add_to_git_credential=False
        )
        print("Hugging Face authentication successful")
    else:
        print(
            "WARNING: No Hugging Face token found. "
            "Set HF_TOKEN environment variable."
        )

except Exception as e:
    print(f"WARNING: HuggingFace login failed: {e}")


# ---- PyTorch 2.6+ checkpoint compatibility ----

try:
    import torch.serialization

    torch.serialization.add_safe_globals(
        [
            torch.torch_version.TorchVersion
        ]
    )

except Exception as e:
    print(
        f"WARNING: Could not add TorchVersion safe global: {e}"
    )


_original_torch_load = torch.load
_original_serialization_load = torch.serialization.load


@functools.wraps(_original_torch_load)
def _patched_torch_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _original_torch_load(*args, **kwargs)


@functools.wraps(_original_serialization_load)
def _patched_serialization_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _original_serialization_load(*args, **kwargs)


torch.load = _patched_torch_load
torch.serialization.load = _patched_serialization_load


# ============================================================
# Hugging Face Hub compatibility patch
# ============================================================
#
# Some NeMo / Sortformer versions still pass use_auth_token
# to huggingface_hub functions. Newer huggingface_hub versions
# expect token instead.
# ============================================================

try:
    import huggingface_hub

    _original_hf_download = huggingface_hub.hf_hub_download

    def _patched_hf_download(*args, **kwargs):
        if "use_auth_token" in kwargs:
            kwargs["token"] = kwargs.pop("use_auth_token")
        return _original_hf_download(*args, **kwargs)

    huggingface_hub.hf_hub_download = _patched_hf_download

    if hasattr(huggingface_hub, "snapshot_download"):

        _original_snapshot = huggingface_hub.snapshot_download

        def _patched_snapshot(*args, **kwargs):
            if "use_auth_token" in kwargs:
                kwargs["token"] = kwargs.pop("use_auth_token")
            return _original_snapshot(*args, **kwargs)

        huggingface_hub.snapshot_download = _patched_snapshot

    print(
        "Applied huggingface_hub patch "
        "(use_auth_token -> token)."
    )

except Exception as e:
    print(
        f"WARNING: Could not apply huggingface_hub compatibility "
        f"patch: {e}"
    )


# ============================================================
# Imports
# ============================================================

import json
import sys
import tempfile
from pathlib import Path
from typing import List, Dict


PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from speech_analysis_qa.speech_pipeline.common.config import (
    WHISPER_MODEL_SIZE,
    TARGET_SAMPLE_RATE,
)

from speech_analysis_qa.speech_pipeline.common.device_utils import (
    get_compute_device,
)


# ============================================================
# Sortformer configuration
# ============================================================

SORTFORMER_MODEL = "nvidia/diar_sortformer_4spk-v1"

_SORTFORMER_MODEL = None
_WHISPER_MODEL_CACHE = {}


# ============================================================
# Load Sortformer
# ============================================================

def _get_diarization_pipeline(token: str = None):

    global _SORTFORMER_MODEL

    if _SORTFORMER_MODEL is None:

        import traceback

        if not token:
            token = HF_TOKEN

        if not token:
            print(
                "WARNING: No HF token found. "
                "Sortformer model download may fail."
            )

        try:

            print(
                f"Loading Sortformer diarization model: "
                f"{SORTFORMER_MODEL}"
            )

            from nemo.collections.asr.models import (
                SortformerEncLabelModel
            )

            _SORTFORMER_MODEL = (
                SortformerEncLabelModel.from_pretrained(
                    SORTFORMER_MODEL
                )
            )

            _SORTFORMER_MODEL.eval()

            if torch.cuda.is_available():
                _SORTFORMER_MODEL = _SORTFORMER_MODEL.cuda()

            print(
                "Sortformer diarization model loaded successfully"
            )

        except Exception as exc:

            traceback.print_exc()

            raise RuntimeError(
                "Failed to load Sortformer diarization model.\n"
                f"Original error: {exc}"
            ) from exc

    return _SORTFORMER_MODEL


# ============================================================
# Load Whisper
# ============================================================

def _get_whisper_model(
    model_size: str = WHISPER_MODEL_SIZE
):
    global _WHISPER_MODEL_CACHE

    if model_size not in _WHISPER_MODEL_CACHE:

        import torch
        from faster_whisper import WhisperModel

        device = get_compute_device(
            os.getenv("LIGHT_ASR_DEVICE", "auto")
        )

        compute_type = "int8"

        _WHISPER_MODEL_CACHE[model_size] = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )

    return _WHISPER_MODEL_CACHE[model_size]


# ============================================================
# Cleanup
# ============================================================

def cleanup():

    global _SORTFORMER_MODEL
    global _WHISPER_MODEL_CACHE

    _SORTFORMER_MODEL = None
    _WHISPER_MODEL_CACHE.clear()

    import gc

    from speech_analysis_qa.speech_pipeline.common.device_utils import (
        clear_torch_cache
    )

    gc.collect()
    clear_torch_cache()


# ============================================================
# Audio loading
# ============================================================

def load_audio(
    file_path: str,
    target_sr: int = TARGET_SAMPLE_RATE
):

    import librosa

    audio, sr = librosa.load(
        file_path,
        sr=target_sr,
        mono=True
    )

    return audio, sr


# ============================================================
# Sortformer output parser
# ============================================================

def _parse_sortformer_output(predicted_segments):
    """
    Convert NVIDIA Sortformer diarization output into
    pyannote.core.Annotation.

    NeMo Sortformer diarize() returns:
        List[List[str]]

    Typical segment formats include:
        "0.00 1.52 speaker_0"
        "1.52 3.21 speaker_1"

    Some NeMo versions may instead return:
        [start, end, speaker]

    This function handles both.
    """

    from pyannote.core import Segment, Annotation

    annotation = Annotation()

    if predicted_segments is None:
        return annotation

    print(
        f"DEBUG: Sortformer output type: "
        f"{type(predicted_segments)}"
    )

    print(
        f"DEBUG: Sortformer output preview: "
        f"{repr(predicted_segments)[:2000]}"
    )

    # ========================================================
    # Sortformer normally returns:
    #
    # [
    #     [
    #         "start end speaker",
    #         "start end speaker",
    #         ...
    #     ]
    # ]
    #
    # We are processing ONE audio file, so unwrap the outer
    # batch dimension.
    # ========================================================

    if isinstance(predicted_segments, list):

        # Empty result
        if len(predicted_segments) == 0:
            return annotation

        # ----------------------------------------------------
        # If this is a batch containing one audio file,
        # unwrap it.
        # ----------------------------------------------------

        if (
            len(predicted_segments) == 1
            and isinstance(
                predicted_segments[0],
                (list, tuple)
            )
        ):
            predicted_segments = predicted_segments[0]

    # ========================================================
    # Handle dictionary output
    # ========================================================

    if isinstance(predicted_segments, dict):

        for key in [
            "segments",
            "diarization",
            "result",
            "predicted_segments",
        ]:

            if key in predicted_segments:

                predicted_segments = (
                    predicted_segments[key]
                )

                break

        else:

            if (
                "start" in predicted_segments
                and "end" in predicted_segments
            ):
                predicted_segments = [
                    predicted_segments
                ]

            else:

                print(
                    "WARNING: Unknown Sortformer "
                    f"dictionary output: "
                    f"{predicted_segments.keys()}"
                )

                return annotation

    # ========================================================
    # Make sure we have a sequence
    # ========================================================

    if not isinstance(
        predicted_segments,
        (list, tuple)
    ):

        print(
            "WARNING: Unexpected Sortformer output type: "
            f"{type(predicted_segments)}"
        )

        return annotation

    # ========================================================
    # Parse every segment
    # ========================================================

    for seg in predicted_segments:

        try:

            start = None
            end = None
            speaker = None

            # =================================================
            # CASE 1:
            #
            # Sortformer string:
            #
            # "0.00 1.52 speaker_0"
            # =================================================

            if isinstance(seg, str):

                line = seg.strip()

                if not line:
                    continue

                parts = line.split()

                if len(parts) >= 3:

                    try:

                        start = float(parts[0])
                        end = float(parts[1])
                        speaker = parts[2]

                    except (
                        ValueError,
                        TypeError,
                    ):

                        print(
                            "WARNING: Could not parse "
                            f"Sortformer string: {seg}"
                        )

                        continue

                else:

                    print(
                        "WARNING: Unexpected Sortformer "
                        f"segment string: {seg}"
                    )

                    continue

            # =================================================
            # CASE 2:
            #
            # Dictionary:
            #
            # {
            #   "start": ...,
            #   "end": ...,
            #   "speaker": ...
            # }
            # =================================================

            elif isinstance(seg, dict):

                start = seg.get("start")
                end = seg.get("end")

                speaker = seg.get(
                    "speaker"
                )

                if start is None:
                    start = seg.get(
                        "start_time"
                    )

                if end is None:
                    end = seg.get(
                        "end_time"
                    )

                if speaker is None:
                    speaker = (
                        seg.get("speaker_id")
                        or seg.get("label")
                    )

            # =================================================
            # CASE 3:
            #
            # [start, end, speaker]
            # =================================================

            elif isinstance(
                seg,
                (list, tuple)
            ):

                if len(seg) >= 3:

                    try:

                        start = float(seg[0])
                        end = float(seg[1])
                        speaker = str(seg[2])

                    except (
                        ValueError,
                        TypeError,
                    ):

                        print(
                            "WARNING: Could not parse "
                            f"Sortformer list: {seg}"
                        )

                        continue

            # =================================================
            # Unknown format
            # =================================================

            else:

                print(
                    "WARNING: Unknown Sortformer "
                    f"segment type: {type(seg)}"
                )

                continue

            # =================================================
            # Validate
            # =================================================

            if start is None or end is None:

                continue

            start = float(start)
            end = float(end)

            if speaker is None:

                speaker = "UNKNOWN"

            speaker = str(
                speaker
            )

            if speaker.lower() in [
                "unknown",
                "unk",
                "none",
                "",
            ]:

                continue

            if start < 0:
                continue

            if end <= 0:
                continue

            if start >= end:
                continue

            # =================================================
            # Normalize speaker name
            #
            # Sortformer speaker indexes can be:
            #
            # 0
            # 1
            # 2
            #
            # or:
            #
            # speaker_0
            # speaker_1
            #
            # Keep them stable for downstream processing.
            # =================================================

            if speaker.isdigit():

                speaker = (
                    f"SPEAKER_{int(speaker):02d}"
                )

            elif speaker.lower().startswith(
                "speaker_"
            ):

                suffix = speaker.split(
                    "_"
                )[-1]

                if suffix.isdigit():

                    speaker = (
                        f"SPEAKER_{int(suffix):02d}"
                    )

            # =================================================
            # Add to pyannote Annotation
            # =================================================

            annotation[
                Segment(
                    start,
                    end
                )
            ] = speaker

        except Exception as e:

            print(
                "WARNING: Failed to parse "
                f"Sortformer segment {repr(seg)}: {e}"
            )

            continue

    # ========================================================
    # Diagnostic summary
    # ========================================================

    speakers = set()

    total_duration = 0.0

    for (
        segment,
        _,
        speaker
    ) in annotation.itertracks(
        yield_label=True
    ):

        speakers.add(speaker)

        total_duration += (
            segment.end -
            segment.start
        )

    print(
        f"Sortformer parsed {len(speakers)} speaker(s)"
    )

    print(
        f"Sortformer speech duration: "
        f"{total_duration:.2f}s"
    )

    if speakers:

        print(
            "Sortformer speakers: "
            + ", ".join(
                sorted(speakers)
            )
        )

    else:

        print(
            "WARNING: Sortformer produced "
            "no usable speaker segments."
        )

    return annotation

# ============================================================
# Run Sortformer diarization
# ============================================================

def run_diarization(
    audio,
    sr: int,
    token: str
):

    import soundfile as sf

    pipeline = _get_diarization_pipeline(
        token
    )

    temp_file = None

    try:

        fd, temp_file = tempfile.mkstemp(
            suffix=".wav"
        )

        os.close(fd)

        sf.write(
            temp_file,
            audio,
            sr,
            subtype="PCM_16"
        )

        print(
            "Running NVIDIA Sortformer diarization..."
        )

        raw_output = pipeline.diarize(
            audio=temp_file,
            batch_size=1,
        )

        # ----------------------------------------------------
        # IMPORTANT:
        # Print the actual NeMo output before parsing.
        # ----------------------------------------------------

        # print(
        #     "DEBUG: Raw Sortformer output:"
        # )

        # print(
        #     repr(raw_output)[:5000]
        # )

        annotation = _parse_sortformer_output(
            raw_output
        )

        return annotation

    finally:

        if temp_file is not None:

            try:
                os.remove(temp_file)

            except Exception:
                pass

# ============================================================
# ASR normalization
# ============================================================

def _normalize_asr_segments(
    raw_segments
) -> List[Dict]:

    normalized = []

    for segment in raw_segments or []:

        if isinstance(segment, dict):

            normalized.append(segment)

            continue

        attrs = getattr(
            segment,
            "__dict__",
            {}
        )

        normalized.append(
            {
                "start": getattr(
                    segment,
                    "start",
                    attrs.get("start", 0)
                ),

                "end": getattr(
                    segment,
                    "end",
                    attrs.get("end", 0)
                ),

                "text": getattr(
                    segment,
                    "text",
                    attrs.get("text", "")
                ),
            }
        )

    return normalized


# ============================================================
# Whisper ASR
# ============================================================

def run_asr(
    audio_path: str,
    model_size: str = WHISPER_MODEL_SIZE
) -> List[Dict]:

    model = _get_whisper_model(
        model_size
    )

    result = model.transcribe(
        audio_path,
        word_timestamps=True
    )

    if isinstance(result, tuple):

        segments = result[0]

    elif isinstance(result, dict):

        segments = result.get(
            "segments",
            []
        )

    else:

        segments = result

    return _normalize_asr_segments(
        segments
    )


# ============================================================
# Assign speakers to ASR segments
# ============================================================

def assign_speakers_to_asr(
    diarization,
    asr_segments
):

    # --------------------------------------------------------
    # pyannote Annotation
    # --------------------------------------------------------

    if hasattr(
        diarization,
        "speaker_diarization"
    ):

        annotation = (
            diarization.speaker_diarization
        )

    else:

        annotation = diarization

    # --------------------------------------------------------
    # Convert diarization to list
    # --------------------------------------------------------

    speaker_segments = [

        {
            "start": segment.start,
            "end": segment.end,
            "speaker": speaker,
        }

        for (
            segment,
            _,
            speaker
        ) in annotation.itertracks(
            yield_label=True
        )
    ]

    speaker_segments.sort(
        key=lambda x: x["start"]
    )

    asr_segments = sorted(
        asr_segments,
        key=lambda x: x["start"]
    )

    output = []

    # --------------------------------------------------------
    # Match each Whisper segment to the speaker with the
    # largest temporal overlap.
    # --------------------------------------------------------

    for asr in asr_segments:

        best_overlap = 0
        best_speaker = "UNKNOWN"

        for sp in speaker_segments:

            overlap = max(
                0,

                min(
                    asr["end"],
                    sp["end"]
                )

                -

                max(
                    asr["start"],
                    sp["start"]
                )
            )

            if overlap > best_overlap:

                best_overlap = overlap
                best_speaker = sp["speaker"]

        output.append(
            {
                "start": asr["start"],
                "end": asr["end"],
                "speaker": best_speaker,
                "text": asr["text"].strip(),
            }
        )

    return output


# ============================================================
# Process one audio file
# ============================================================

def process_audio(
    file_path: str,
    hf_token: str = None
) -> List[Dict]:

    """
    Load, diarize, transcribe, and align.

    Returns the diarized segment list.
    """

    # --------------------------------------------------------
    # Load audio
    # --------------------------------------------------------

    audio, sr = load_audio(
        file_path
    )

    # --------------------------------------------------------
    # Sortformer diarization
    # --------------------------------------------------------

    print(
        "Running speaker diarization..."
    )

    diarization = run_diarization(
        audio,
        sr,
        hf_token
    )

    # --------------------------------------------------------
    # Whisper ASR
    # --------------------------------------------------------

    print(
        "Running Whisper ASR..."
    )

    asr_segments = run_asr(
        file_path
    )

    # --------------------------------------------------------
    # Speaker assignment
    # --------------------------------------------------------

    print(
        "Assigning speakers to transcribed segments..."
    )

    return assign_speakers_to_asr(
        diarization,
        asr_segments
    )


# ============================================================
# Main run function
# ============================================================

def run(
    audio_path: str,
    output_path: str
) -> List[Dict]:

    if not os.path.exists(
        audio_path
    ):

        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    segments = process_audio(
        audio_path
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            segments,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"Diarized transcript saved -> {output_path}"
    )

    return segments


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Stage 1: audio -> "
            "Sortformer diarized JSON"
        )
    )

    parser.add_argument(
        "audio_path"
    )

    parser.add_argument(
        "output_path"
    )

    args = parser.parse_args()

    run(
        args.audio_path,
        args.output_path
    )