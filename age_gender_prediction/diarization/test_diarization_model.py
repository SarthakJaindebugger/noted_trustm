# #/scratch/work/jains6/noted/tf_py_311/bin/python3.11 /scratch/work/jains6/noted/noted-main/age_gender_prediction/test_diarization_model.py

#WESPEAKER AND SORTFORMER
# import os
# import time
# import json
# import argparse
# import tempfile

# import torch
# import librosa
# import soundfile as sf
# from huggingface_hub import snapshot_download


# # ============================================================
# # CONFIGURATION
# # ============================================================

# AUDIO_PATH = (
#     "/scratch/work/jains6/noted/noted-main/"
#     "knowledgebase/users_admin_data/users/demo/recordings/"
#     "dia01sce1MC.WAV"
# )

# SAMPLE_RATE = 16000

# DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# WESPEAKER_MODEL = "Wespeaker/wespeaker-ecapa-tdnn512-LM"

# SORTFORMER_MODEL = "nvidia/diar_sortformer_4spk-v1"


# # ============================================================
# # FIX WESPEAKER / SCIKIT-LEARN COMPATIBILITY
# # ============================================================

# def patch_sklearn_for_wespeaker():

#     """
#     Compatibility fix for older WeSpeaker versions.

#     Older WeSpeaker code calls:

#         check_array(..., force_all_finite=...)

#     Newer scikit-learn versions use:

#         ensure_all_finite

#     We patch the sklearn validation function AND the
#     commonly imported aliases before importing WeSpeaker.
#     """

#     import inspect

#     try:

#         import sklearn
#         import sklearn.utils
#         import sklearn.utils.validation as validation

#         print(
#             f"scikit-learn version: "
#             f"{sklearn.__version__}"
#         )

#         original_check_array = (
#             validation.check_array
#         )

#         signature = inspect.signature(
#             original_check_array
#         )

#         # ----------------------------------------------------
#         # If old API is already supported, nothing to do.
#         # ----------------------------------------------------

#         if "force_all_finite" in signature.parameters:

#             print(
#                 "WeSpeaker/sklearn compatibility patch "
#                 "not required."
#             )

#             return

#         # ----------------------------------------------------
#         # New sklearn API
#         # ----------------------------------------------------

#         def check_array_compat(*args, **kwargs):

#             if "force_all_finite" in kwargs:

#                 kwargs["ensure_all_finite"] = (
#                     kwargs.pop("force_all_finite")
#                 )

#             return original_check_array(
#                 *args,
#                 **kwargs
#             )

#         # ----------------------------------------------------
#         # Patch validation module
#         # ----------------------------------------------------

#         validation.check_array = (
#             check_array_compat
#         )

#         # ----------------------------------------------------
#         # Patch sklearn.utils.check_array
#         # ----------------------------------------------------

#         if hasattr(
#             sklearn.utils,
#             "check_array"
#         ):

#             sklearn.utils.check_array = (
#                 check_array_compat
#             )

#         print(
#             "Applied sklearn compatibility patch "
#             "for WeSpeaker."
#         )

#     except Exception as e:

#         print(
#             "WARNING: Could not patch sklearn:"
#         )

#         print(
#             f"  {type(e).__name__}: {e}"
#         )


# # IMPORTANT:
# # This MUST happen before importing wespeaker.
# patch_sklearn_for_wespeaker()


# # ============================================================
# # GPU HELPERS
# # ============================================================

# def synchronize_cuda():

#     if torch.cuda.is_available():

#         torch.cuda.synchronize()


# def reset_gpu_memory_stats():

#     if not torch.cuda.is_available():

#         return

#     torch.cuda.synchronize()

#     torch.cuda.empty_cache()

#     torch.cuda.reset_peak_memory_stats()

#     torch.cuda.synchronize()


# def get_peak_gpu_memory():

#     if not torch.cuda.is_available():

#         return 0.0, 0.0

#     torch.cuda.synchronize()

#     peak_alloc = (
#         torch.cuda.max_memory_allocated()
#         / (1024 ** 3)
#     )

#     peak_reserved = (
#         torch.cuda.max_memory_reserved()
#         / (1024 ** 3)
#     )

#     return peak_alloc, peak_reserved


# def get_current_gpu_memory():

#     if not torch.cuda.is_available():

#         return 0.0, 0.0

#     torch.cuda.synchronize()

#     allocated = (
#         torch.cuda.memory_allocated()
#         / (1024 ** 3)
#     )

#     reserved = (
#         torch.cuda.memory_reserved()
#         / (1024 ** 3)
#     )

#     return allocated, reserved


# # ============================================================
# # AUDIO
# # ============================================================

# def get_audio_duration(audio_path):

#     return float(
#         librosa.get_duration(
#             path=audio_path
#         )
#     )


# def convert_to_mono_temp(
#     audio_path,
#     target_sr=SAMPLE_RATE
# ):

#     audio, sr = librosa.load(
#         audio_path,
#         sr=target_sr,
#         mono=True
#     )

#     fd, temp_path = tempfile.mkstemp(
#         suffix=".wav"
#     )

#     os.close(fd)

#     sf.write(
#         temp_path,
#         audio,
#         target_sr,
#         subtype="PCM_16"
#     )

#     return temp_path


# # ============================================================
# # SPEAKER EXTRACTION
# # ============================================================

# def extract_speaker_from_segment(segment):

#     """
#     Extract ONLY the speaker ID from one diarization segment.

#     Expected formats include:

#         [start, end, speaker]

#         (start, end, speaker)

#         {"start": ..., "end": ..., "speaker": ...}

#     IMPORTANT:
#     Do NOT treat start/end times as speaker IDs.
#     """

#     # --------------------------------------------------------
#     # Dictionary
#     # --------------------------------------------------------

#     if isinstance(segment, dict):

#         for key in [
#             "speaker",
#             "speaker_id",
#             "speaker_label",
#             "label"
#         ]:

#             if key in segment:

#                 return str(
#                     segment[key]
#                 )

#         return None

#     # --------------------------------------------------------
#     # List / tuple
#     # --------------------------------------------------------

#     if isinstance(
#         segment,
#         (list, tuple)
#     ):

#         if len(segment) >= 3:

#             # Typical:
#             #
#             # [start, end, speaker]

#             return str(
#                 segment[2]
#             )

#         return None

#     # --------------------------------------------------------
#     # String
#     # --------------------------------------------------------

#     if isinstance(
#         segment,
#         str
#     ):

#         parts = segment.split()

#         if len(parts) >= 3:

#             return str(
#                 parts[-1]
#             )

#         return None

#     return None


# def extract_speakers(result):

#     """
#     Extract unique speaker IDs from diarization output.
#     """

#     speakers = set()

#     if result is None:

#         return speakers

#     # ========================================================
#     # LIST / TUPLE
#     # ========================================================

#     if isinstance(
#         result,
#         (list, tuple)
#     ):

#         for segment in result:

#             speaker = (
#                 extract_speaker_from_segment(
#                     segment
#                 )
#             )

#             if speaker is not None:

#                 speakers.add(
#                     speaker
#                 )

#         return speakers

#     # ========================================================
#     # STRING
#     # ========================================================

#     if isinstance(
#         result,
#         str
#     ):

#         for line in result.splitlines():

#             line = line.strip()

#             if not line:

#                 continue

#             speaker = (
#                 extract_speaker_from_segment(
#                     line
#                 )
#             )

#             if speaker is not None:

#                 speakers.add(
#                     speaker
#                 )

#         return speakers

#     # ========================================================
#     # DICTIONARY
#     # ========================================================

#     if isinstance(
#         result,
#         dict
#     ):

#         # Direct speaker field

#         for key in [
#             "speaker",
#             "speaker_id",
#             "speaker_label"
#         ]:

#             if key in result:

#                 value = result[key]

#                 if isinstance(
#                     value,
#                     (list, tuple, set)
#                 ):

#                     for speaker in value:

#                         speakers.add(
#                             str(speaker)
#                         )

#                 else:

#                     speakers.add(
#                         str(value)
#                     )

#                 return speakers

#         # Speaker list

#         for key in [
#             "speakers",
#             "labels"
#         ]:

#             if key in result:

#                 value = result[key]

#                 if isinstance(
#                     value,
#                     (list, tuple, set)
#                 ):

#                     for speaker in value:

#                         speakers.add(
#                             str(speaker)
#                         )

#                 return speakers

#     return speakers


# # ============================================================
# # WESPEAKER
# # ============================================================

# def run_wespeaker(audio_path):

#     print()
#     print("=" * 70)
#     print("WESPEAKER")
#     print("=" * 70)

#     # Import AFTER sklearn patch

#     import wespeaker

#     print(
#         "Loading WeSpeaker..."
#     )

#     model_dir = snapshot_download(
#         repo_id=WESPEAKER_MODEL
#     )

#     print(
#         f"Model directory:\n{model_dir}"
#     )

#     model = wespeaker.load_model(
#         model_dir
#     )

#     # --------------------------------------------------------
#     # GPU
#     # --------------------------------------------------------

#     if torch.cuda.is_available():

#         gpu_configured = False

#         try:

#             model.set_device(
#                 "cuda:0"
#             )

#             gpu_configured = True

#             print(
#                 "WeSpeaker device: CUDA"
#             )

#         except Exception as e:

#             print(
#                 f"model.set_device failed: {e}"
#             )

#         if not gpu_configured:

#             try:

#                 model.set_gpu(0)

#                 gpu_configured = True

#                 print(
#                     "WeSpeaker device: CUDA"
#                 )

#             except Exception as e:

#                 print(
#                     f"model.set_gpu failed: {e}"
#                 )

#     else:

#         print(
#             "WeSpeaker device: CPU"
#         )

#     # --------------------------------------------------------
#     # Prepare audio
#     # --------------------------------------------------------

#     temp_path = (
#         convert_to_mono_temp(
#             audio_path
#         )
#     )

#     try:

#         reset_gpu_memory_stats()

#         before_alloc, before_reserved = (
#             get_current_gpu_memory()
#         )

#         # ----------------------------------------------------
#         # Timing
#         # ----------------------------------------------------

#         start = time.perf_counter()

#         diar_result = model.diarize(
#             temp_path
#         )

#         synchronize_cuda()

#         inference_time = (
#             time.perf_counter()
#             - start
#         )

#         # ----------------------------------------------------
#         # Memory
#         # ----------------------------------------------------

#         peak_alloc, peak_reserved = (
#             get_peak_gpu_memory()
#         )

#         after_alloc, after_reserved = (
#             get_current_gpu_memory()
#         )

#         # ----------------------------------------------------
#         # Speakers
#         # ----------------------------------------------------

#         speakers = extract_speakers(
#             diar_result
#         )

#         print(
#             f"WeSpeaker inference time: "
#             f"{inference_time:.3f} s"
#         )

#         print(
#             f"WeSpeaker speakers detected: "
#             f"{len(speakers)}"
#         )

#         print(
#             f"WeSpeaker peak VRAM allocated: "
#             f"{peak_alloc:.3f} GB"
#         )

#         print(
#             f"WeSpeaker peak VRAM reserved: "
#             f"{peak_reserved:.3f} GB"
#         )

#         print(
#             f"WeSpeaker GPU allocated before: "
#             f"{before_alloc:.3f} GB"
#         )

#         print(
#             f"WeSpeaker GPU allocated after: "
#             f"{after_alloc:.3f} GB"
#         )

#         if speakers:

#             print(
#                 "WeSpeaker speaker IDs: "
#                 + ", ".join(
#                     sorted(speakers)
#                 )
#             )

#         return (
#             inference_time,
#             len(speakers),
#             peak_alloc,
#             peak_reserved
#         )

#     finally:

#         try:

#             os.remove(
#                 temp_path
#             )

#         except Exception:

#             pass

#         if torch.cuda.is_available():

#             torch.cuda.empty_cache()

#             torch.cuda.synchronize()


# # ============================================================
# # SORTFORMER
# # ============================================================

# def run_sortformer(audio_path):

#     print()
#     print("=" * 70)
#     print("NVIDIA SORTFORMER")
#     print("=" * 70)

#     from nemo.collections.asr.models import (
#         SortformerEncLabelModel
#     )

#     print(
#         "Loading NVIDIA Sortformer..."
#     )

#     model = (
#         SortformerEncLabelModel
#         .from_pretrained(
#             SORTFORMER_MODEL
#         )
#     )

#     model.eval()

#     if torch.cuda.is_available():

#         model = model.cuda()

#         print(
#             "Sortformer device: CUDA"
#         )

#     else:

#         print(
#             "Sortformer device: CPU"
#         )

#     # --------------------------------------------------------
#     # Prepare audio
#     # --------------------------------------------------------

#     temp_path = (
#         convert_to_mono_temp(
#             audio_path
#         )
#     )

#     try:

#         reset_gpu_memory_stats()

#         before_alloc, before_reserved = (
#             get_current_gpu_memory()
#         )

#         # ----------------------------------------------------
#         # Timing
#         # ----------------------------------------------------

#         start = time.perf_counter()

#         predicted_segments = (
#             model.diarize(
#                 audio=temp_path,
#                 batch_size=1
#             )
#         )

#         synchronize_cuda()

#         inference_time = (
#             time.perf_counter()
#             - start
#         )

#         # ----------------------------------------------------
#         # GPU memory
#         # ----------------------------------------------------

#         peak_alloc, peak_reserved = (
#             get_peak_gpu_memory()
#         )

#         after_alloc, after_reserved = (
#             get_current_gpu_memory()
#         )

#         # ----------------------------------------------------
#         # Speaker extraction
#         # ----------------------------------------------------

#         speakers = extract_speakers(
#             predicted_segments
#         )

#         print(
#             f"Sortformer inference time: "
#             f"{inference_time:.3f} s"
#         )

#         print(
#             f"Sortformer speakers detected: "
#             f"{len(speakers)}"
#         )

#         print(
#             f"Sortformer peak VRAM allocated: "
#             f"{peak_alloc:.3f} GB"
#         )

#         print(
#             f"Sortformer peak VRAM reserved: "
#             f"{peak_reserved:.3f} GB"
#         )

#         print(
#             f"Sortformer GPU allocated before: "
#             f"{before_alloc:.3f} GB"
#         )

#         print(
#             f"Sortformer GPU allocated after: "
#             f"{after_alloc:.3f} GB"
#         )

#         if speakers:

#             print(
#                 "Sortformer speaker IDs: "
#                 + ", ".join(
#                     sorted(speakers)
#                 )
#             )

#         return (
#             inference_time,
#             len(speakers),
#             peak_alloc,
#             peak_reserved
#         )

#     finally:

#         try:

#             os.remove(
#                 temp_path
#             )

#         except Exception:

#             pass

#         if torch.cuda.is_available():

#             del model

#             torch.cuda.empty_cache()

#             torch.cuda.synchronize()


# # ============================================================
# # MAIN
# # ============================================================

# def main():

#     parser = argparse.ArgumentParser()

#     parser.add_argument(
#         "--audio",
#         type=str,
#         default=AUDIO_PATH
#     )

#     parser.add_argument(
#         "--json",
#         action="store_true"
#     )

#     args = parser.parse_args()

#     audio_path = args.audio

#     # --------------------------------------------------------
#     # Validate
#     # --------------------------------------------------------

#     if not os.path.isfile(
#         audio_path
#     ):

#         raise FileNotFoundError(
#             f"Audio file not found: "
#             f"{audio_path}"
#         )

#     # --------------------------------------------------------
#     # Duration
#     # --------------------------------------------------------

#     duration = (
#         get_audio_duration(
#             audio_path
#         )
#     )

#     print()
#     print("=" * 70)
#     print("DIARIZATION MODEL COMPARISON")
#     print("=" * 70)

#     print(
#         f"Audio: {audio_path}"
#     )

#     print(
#         f"Audio duration: "
#         f"{duration:.2f} seconds"
#     )

#     print(
#         f"Device: {DEVICE}"
#     )

#     if torch.cuda.is_available():

#         gpu_name = (
#             torch.cuda.get_device_name(0)
#         )

#         total_vram = (
#             torch.cuda
#             .get_device_properties(0)
#             .total_memory
#             / (1024 ** 3)
#         )

#         print(
#             f"GPU: {gpu_name}"
#         )

#         print(
#             f"Total GPU VRAM: "
#             f"{total_vram:.3f} GB"
#         )

#     results = {

#         "audio": audio_path,

#         "audio_duration_seconds": duration,

#         "device": DEVICE
#     }

#     # ========================================================
#     # WESPEAKER
#     # ========================================================

#     try:

#         (
#             t,
#             speakers,
#             peak_alloc,
#             peak_reserved
#         ) = run_wespeaker(
#             audio_path
#         )

#         results["wespeaker"] = {

#             "status": "success",

#             "time_seconds": t,

#             "speakers": speakers,

#             "peak_vram_allocated_gb":
#                 peak_alloc,

#             "peak_vram_reserved_gb":
#                 peak_reserved
#         }

#     except Exception as e:

#         print()
#         print("=" * 70)
#         print("WESPEAKER FAILED")
#         print("=" * 70)

#         print(
#             f"Error type: "
#             f"{type(e).__name__}"
#         )

#         print(
#             f"Error: {e}"
#         )

#         results["wespeaker"] = {

#             "status": "failed",

#             "error_type":
#                 type(e).__name__,

#             "error": str(e)
#         }

#         if torch.cuda.is_available():

#             torch.cuda.empty_cache()

#             torch.cuda.synchronize()

#     # ========================================================
#     # SORTFORMER
#     # ========================================================

#     try:

#         (
#             t,
#             speakers,
#             peak_alloc,
#             peak_reserved
#         ) = run_sortformer(
#             audio_path
#         )

#         results["sortformer"] = {

#             "status": "success",

#             "time_seconds": t,

#             "speakers": speakers,

#             "peak_vram_allocated_gb":
#                 peak_alloc,

#             "peak_vram_reserved_gb":
#                 peak_reserved
#         }

#     except Exception as e:

#         print()
#         print("=" * 70)
#         print("SORTFORMER FAILED")
#         print("=" * 70)

#         print(
#             f"Error type: "
#             f"{type(e).__name__}"
#         )

#         print(
#             f"Error: {e}"
#         )

#         results["sortformer"] = {

#             "status": "failed",

#             "error_type":
#                 type(e).__name__,

#             "error": str(e)
#         }

#     # ========================================================
#     # FINAL RESULTS
#     # ========================================================

#     print()
#     print("=" * 70)
#     print("FINAL RESULTS")
#     print("=" * 70)

#     print(
#         f"\nAudio duration: "
#         f"{duration:.2f} seconds"
#     )

#     for model_name in [
#         "wespeaker",
#         "sortformer"
#     ]:

#         print()
#         print(
#             model_name.upper()
#         )

#         print(
#             "-" * 50
#         )

#         data = results.get(
#             model_name
#         )

#         if data is None:

#             print(
#                 "STATUS: NO RESULT"
#             )

#             continue

#         if data["status"] == "failed":

#             print(
#                 "STATUS: FAILED"
#             )

#             print(
#                 f"Error type: "
#                 f"{data['error_type']}"
#             )

#             print(
#                 f"Error: "
#                 f"{data['error']}"
#             )

#         else:

#             print(
#                 "STATUS: SUCCESS"
#             )

#             print(
#                 f"Time: "
#                 f"{data['time_seconds']:.3f} s"
#             )

#             print(
#                 f"Speakers: "
#                 f"{data['speakers']}"
#             )

#             print(
#                 f"Peak VRAM allocated: "
#                 f"{data['peak_vram_allocated_gb']:.3f} GB"
#             )

#             print(
#                 f"Peak VRAM reserved: "
#                 f"{data['peak_vram_reserved_gb']:.3f} GB"
#             )

#     print()
#     print("=" * 70)

#     # --------------------------------------------------------
#     # JSON output
#     # --------------------------------------------------------

#     if args.json:

#         print()
#         print(
#             json.dumps(
#                 results,
#                 indent=2
#             )
#         )


# # ============================================================
# # ENTRY POINT
# # ============================================================

# if __name__ == "__main__":
#     main()









#PYANNOTE 
#/scratch/work/jains6/noted/tf_py_311/bin/python3.11 /scratch/work/jains6/noted/noted-main/age_gender_prediction/test_diarization_model.py
import os
import time
import json
import argparse

import torch
import librosa


# ============================================================
# CONFIGURATION
# ============================================================

AUDIO_PATH = (
    "/scratch/work/jains6/noted/noted-main/"
    "knowledgebase/users_admin_data/users/demo/recordings/"
    "dia01sce1MC.WAV"
)

SAMPLE_RATE = 16000

DEVICE = (
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)

PYANNOTE_MODEL = "pyannote/speaker-diarization-3.1"

HF_TOKEN = (
    os.getenv("HF_TOKEN")
    or os.getenv("HUGGINGFACEHUB_API_TOKEN")
)


# ============================================================
# GLOBAL
# ============================================================

_DIARIZATION_PIPELINE = None


# ============================================================
# PYTORCH 2.6+ COMPATIBILITY FIX
# ============================================================

def patch_torch_for_pyannote():
    """
    Compatibility fix for Pyannote checkpoints with
    PyTorch >= 2.6.

    PyTorch 2.6 changed torch.load() default behavior to:

        weights_only=True

    Some Pyannote/Lightning checkpoints require:

        weights_only=False

    We force weights_only=False because the checkpoint is
    downloaded from the trusted Hugging Face Pyannote model.
    """

    # --------------------------------------------------------
    # 1. Allowlist TorchVersion
    # --------------------------------------------------------

    try:

        if hasattr(torch, "serialization"):

            add_safe_globals = getattr(
                torch.serialization,
                "add_safe_globals",
                None
            )

            if callable(add_safe_globals):

                try:

                    add_safe_globals(
                        [
                            torch.torch_version.TorchVersion
                        ]
                    )

                    print(
                        "Added TorchVersion to "
                        "PyTorch safe globals."
                    )

                except Exception as e:

                    print(
                        "WARNING: Could not add "
                        "TorchVersion to safe globals:"
                    )

                    print(
                        f"  {type(e).__name__}: {e}"
                    )

    except Exception as e:

        print(
            "WARNING: TorchVersion allowlist "
            f"failed: {e}"
        )

    # --------------------------------------------------------
    # 2. Patch torch.load
    # --------------------------------------------------------

    if getattr(
        torch.load,
        "_pyannote_patch",
        False
    ):

        return

    original_torch_load = torch.load

    def patched_torch_load(
        *args,
        **kwargs
    ):

        # IMPORTANT:
        #
        # Do NOT use setdefault().
        #
        # Pyannote/Lightning may explicitly pass:
        #
        #     weights_only=True
        #
        # Therefore we MUST overwrite it.

        kwargs["weights_only"] = False

        return original_torch_load(
            *args,
            **kwargs
        )

    patched_torch_load._pyannote_patch = True

    torch.load = patched_torch_load

    print(
        "Applied PyTorch torch.load patch:"
    )

    print(
        "  weights_only = False"
    )


# ============================================================
# LOAD PYANNOTE PIPELINE
# ============================================================

def _get_diarization_pipeline(token: str):

    global _DIARIZATION_PIPELINE

    if _DIARIZATION_PIPELINE is None:

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Apply the PyTorch patch BEFORE importing Pyannote.
        # ----------------------------------------------------

        patch_torch_for_pyannote()

        from pyannote.audio import Pipeline

        # ----------------------------------------------------
        # HF TOKEN
        # ----------------------------------------------------

        if not token:

            print(
                "WARNING: HF_TOKEN is not set."
            )

            print(
                "Pyannote may require authentication "
                "for speaker-diarization-3.1."
            )

        else:

            print(
                "HF_TOKEN detected."
            )

        # ----------------------------------------------------
        # Load pipeline
        # ----------------------------------------------------

        try:

            print(
                "Loading Pyannote pipeline..."
            )

            # Follow your old working code:
            #
            # Do NOT pass token/use_auth_token.
            #
            # Hugging Face authentication is handled
            # through the environment.

            _DIARIZATION_PIPELINE = (
                Pipeline.from_pretrained(
                    PYANNOTE_MODEL
                )
            )

        except Exception as exc:

            raise RuntimeError(
                "Failed to load the pyannote "
                "diarization pipeline. "
                "Make sure HF_TOKEN is set and "
                "that you have accepted the model "
                "terms for "
                "pyannote/speaker-diarization-3.1. "
                f"Original error: {exc}"
            ) from exc

        # ----------------------------------------------------
        # Validate
        # ----------------------------------------------------

        if _DIARIZATION_PIPELINE is None:

            raise RuntimeError(
                "Pipeline.from_pretrained returned None."
            )

    return _DIARIZATION_PIPELINE


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

    peak_alloc = (
        torch.cuda.max_memory_allocated()
        / (1024 ** 3)
    )

    peak_res = (
        torch.cuda.max_memory_reserved()
        / (1024 ** 3)
    )

    return peak_alloc, peak_res


def get_current_gpu_memory():

    if not torch.cuda.is_available():

        return 0.0, 0.0

    torch.cuda.synchronize()

    allocated = (
        torch.cuda.memory_allocated()
        / (1024 ** 3)
    )

    reserved = (
        torch.cuda.memory_reserved()
        / (1024 ** 3)
    )

    return allocated, reserved


# ============================================================
# AUDIO
# ============================================================

def get_audio_duration(audio_path):

    return float(
        librosa.get_duration(
            path=audio_path
        )
    )


def load_audio(
    file_path,
    target_sr=SAMPLE_RATE
):

    audio, sr = librosa.load(
        file_path,
        sr=target_sr,
        mono=True
    )

    return audio, sr


# ============================================================
# PYANNOTE DIARIZATION
# ============================================================

def run_pyannote(audio_path):

    print()
    print("=" * 70)
    print("PYANNOTE DIARIZATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Load pipeline
    # --------------------------------------------------------

    pipeline = _get_diarization_pipeline(
        HF_TOKEN
    )

    # --------------------------------------------------------
    # Move to GPU
    # --------------------------------------------------------

    if torch.cuda.is_available():

        pipeline.to(
            torch.device("cuda")
        )

        print(
            "Pyannote device: CUDA"
        )

    else:

        print(
            "Pyannote device: CPU"
        )

    # --------------------------------------------------------
    # Load audio
    # --------------------------------------------------------

    audio, sr = load_audio(
        audio_path
    )

    waveform = (
        torch.from_numpy(
            audio
        )
        .float()
        .unsqueeze(0)
    )

    print(
        f"Sample rate: {sr} Hz"
    )

    print(
        f"Samples: {len(audio)}"
    )

    # --------------------------------------------------------
    # GPU memory reset
    # --------------------------------------------------------

    reset_gpu_memory_stats()

    before_alloc, before_reserved = (
        get_current_gpu_memory()
    )

    # --------------------------------------------------------
    # INFERENCE
    # --------------------------------------------------------

    print(
        "Running Pyannote diarization..."
    )

    start_time = time.perf_counter()

    diarization = pipeline(
        {
            "waveform": waveform,
            "sample_rate": sr
        }
    )

    # --------------------------------------------------------
    # CUDA synchronization
    # --------------------------------------------------------

    synchronize_cuda()

    inference_time = (
        time.perf_counter()
        - start_time
    )

    # --------------------------------------------------------
    # GPU memory
    # --------------------------------------------------------

    peak_alloc, peak_res = (
        get_peak_gpu_memory()
    )

    after_alloc, after_reserved = (
        get_current_gpu_memory()
    )

    # --------------------------------------------------------
    # Get annotation
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
    # Extract speakers
    # --------------------------------------------------------

    speakers = set()

    for (
        segment,
        track,
        speaker
    ) in annotation.itertracks(
        yield_label=True
    ):

        speakers.add(
            str(speaker)
        )

    num_speakers = len(
        speakers
    )

    # --------------------------------------------------------
    # Print
    # --------------------------------------------------------

    print(
        f"Pyannote inference time: "
        f"{inference_time:.3f} s"
    )

    print(
        f"Pyannote speakers detected: "
        f"{num_speakers}"
    )

    print(
        f"Pyannote peak VRAM allocated: "
        f"{peak_alloc:.3f} GB"
    )

    print(
        f"Pyannote peak VRAM reserved: "
        f"{peak_res:.3f} GB"
    )

    print(
        f"Pyannote GPU allocated before: "
        f"{before_alloc:.3f} GB"
    )

    print(
        f"Pyannote GPU allocated after: "
        f"{after_alloc:.3f} GB"
    )

    if speakers:

        print(
            "Pyannote speaker IDs: "
            + ", ".join(
                sorted(speakers)
            )
        )

    return (
        inference_time,
        num_speakers,
        peak_alloc,
        peak_res
    )


# ============================================================
# CLEANUP
# ============================================================

def cleanup():

    global _DIARIZATION_PIPELINE

    _DIARIZATION_PIPELINE = None

    import gc

    gc.collect()

    if torch.cuda.is_available():

        torch.cuda.empty_cache()

        torch.cuda.synchronize()


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Pyannote speaker diarization "
            "benchmark"
        )
    )

    parser.add_argument(
        "--audio",
        type=str,
        default=AUDIO_PATH,
        help="Path to audio file"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    audio_path = args.audio

    # --------------------------------------------------------
    # Check audio
    # --------------------------------------------------------

    if not os.path.isfile(
        audio_path
    ):

        raise FileNotFoundError(
            f"Audio file not found: "
            f"{audio_path}"
        )

    # --------------------------------------------------------
    # Duration
    # --------------------------------------------------------

    duration = (
        get_audio_duration(
            audio_path
        )
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("PYANNOTE DIARIZATION BENCHMARK")
    print("=" * 70)

    print(
        f"Audio: {audio_path}"
    )

    print(
        f"Duration: {duration:.2f} s"
    )

    print(
        f"Device: {DEVICE}"
    )

    # --------------------------------------------------------
    # GPU information
    # --------------------------------------------------------

    if torch.cuda.is_available():

        gpu_name = (
            torch.cuda.get_device_name(0)
        )

        total_vram = (
            torch.cuda
            .get_device_properties(0)
            .total_memory
            / (1024 ** 3)
        )

        print(
            f"GPU: {gpu_name}"
        )

        print(
            f"Total GPU VRAM: "
            f"{total_vram:.3f} GB"
        )

    # --------------------------------------------------------
    # Run
    # --------------------------------------------------------

    try:

        (
            inference_time,
            num_speakers,
            peak_alloc,
            peak_res
        ) = run_pyannote(
            audio_path
        )

        result = {

            "model": "pyannote",

            "audio_duration": duration,

            "time_seconds":
                inference_time,

            "speakers":
                num_speakers,

            "peak_vram_allocated_gb":
                peak_alloc,

            "peak_vram_reserved_gb":
                peak_res
        }

    except Exception as e:

        print()
        print("=" * 70)
        print("PYANNOTE FAILED")
        print("=" * 70)

        print(
            f"Error type: "
            f"{type(e).__name__}"
        )

        print(
            f"Error: {e}"
        )

        result = {

            "model": "pyannote",

            "audio_duration": duration,

            "error": str(e),

            "error_type":
                type(e).__name__
        }

    finally:

        cleanup()

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    if args.json:

        print(
            json.dumps(
                result,
                indent=2
            )
        )

    else:

        print()
        print("=" * 70)
        print("FINAL RESULTS")
        print("=" * 70)

        if "error" in result:

            print(
                "STATUS: FAILED"
            )

            print(
                f"Error type: "
                f"{result['error_type']}"
            )

            print(
                f"Error: "
                f"{result['error']}"
            )

        else:

            print(
                "STATUS: SUCCESS"
            )

            print(
                f"Time: "
                f"{result['time_seconds']:.3f} s"
            )

            print(
                f"Speakers: "
                f"{result['speakers']}"
            )

            print(
                f"Peak VRAM allocated: "
                f"{result['peak_vram_allocated_gb']:.3f} GB"
            )

            print(
                f"Peak VRAM reserved: "
                f"{result['peak_vram_reserved_gb']:.3f} GB"
            )

        print(
            "=" * 70
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()