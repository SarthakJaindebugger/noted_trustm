#!/usr/bin/env python3
"""
Download and prepare the Luganda Callhome Diarization Dataset.

Compatible with:
    Python 3.9
    datasets 4.x
    Audio(decode=False)
    TorchCodec 0.7.x

Audio is decoded manually with librosa.
"""

import os
import argparse
import tempfile

import librosa
import soundfile as sf

from pathlib import Path
from datasets import load_dataset, Audio
from tqdm import tqdm


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(
    "/scratch/work/jains6/noted/noted-main/"
    "age_gender_prediction/diarization/callhome"
)

AUDIO_DIR = BASE_DIR / "audio"
RTTM_DIR = BASE_DIR / "rttm"

DATASET_NAME = (
    "Beijuka/luganda_callhome_diarization_dataset_MHDP"
)


# ============================================================
# AUDIO EXTRACTION
# ============================================================

def load_audio_from_example(audio_info, example_idx):
    """
    Extract an audio file from a Hugging Face Audio(decode=False)
    example.

    Returns:
        audio_path
        temporary_audio

    temporary_audio=True means the returned file should be deleted
    after processing.
    """

    if not isinstance(audio_info, dict):
        raise TypeError(
            f"Example {example_idx}: unexpected audio type: "
            f"{type(audio_info)}"
        )

    audio_bytes = audio_info.get("bytes")
    audio_path = audio_info.get("path")

    # --------------------------------------------------------
    # CASE 1:
    # Raw bytes are available.
    # --------------------------------------------------------

    if audio_bytes is not None:

        tmp = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        )

        try:

            tmp.write(audio_bytes)
            tmp.close()

            return tmp.name, True

        except Exception:

            tmp.close()

            try:
                os.remove(tmp.name)
            except OSError:
                pass

            raise

    # --------------------------------------------------------
    # CASE 2:
    # Path exists and is a real local file.
    # --------------------------------------------------------

    if audio_path:

        if os.path.isfile(audio_path):

            return audio_path, False

    # --------------------------------------------------------
    # CASE 3:
    # Neither bytes nor a local path exists.
    # --------------------------------------------------------

    raise FileNotFoundError(
        f"Example {example_idx}: audio cannot be accessed.\n"
        f"path={audio_path!r}\n"
        f"bytes_available={audio_bytes is not None}"
    )


# ============================================================
# FILE ID
# ============================================================

def get_file_id(audio_info, example_idx):
    """
    Generate a stable file ID.

    If Hugging Face provides a path:
        use its filename.

    If path is None:
        use example_XXXX.
    """

    if isinstance(audio_info, dict):

        original_path = audio_info.get("path")

        if original_path:

            return Path(
                original_path
            ).stem

    return f"example_{example_idx:04d}"


# ============================================================
# WRITE RTTM
# ============================================================

def write_rttm(
    rttm_path,
    file_id,
    starts,
    ends,
    speakers
):
    """
    Write pyannote-compatible RTTM.
    """

    with open(
        rttm_path,
        "w",
        encoding="utf-8"
    ) as f:

        for start, end, speaker in zip(
            starts,
            ends,
            speakers
        ):

            start = float(start)
            end = float(end)

            duration = end - start

            f.write(
                f"SPEAKER "
                f"{file_id} "
                f"1 "
                f"{start:.3f} "
                f"{duration:.3f} "
                f"<NA> "
                f"<NA> "
                f"{speaker} "
                f"<NA>\n"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Prepare Luganda Callhome "
            "diarization dataset"
        )
    )

    parser.add_argument(
        "--subset_hours",
        type=float,
        default=None,
        help=(
            "Process only up to N hours "
            "of audio"
        )
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Reprocess files that already "
            "exist"
        )
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Create output directories
    # --------------------------------------------------------

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    RTTM_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    print("=" * 70)
    print(
        "CALLHOME DIARIZATION DATASET PREPARATION"
    )
    print("=" * 70)

    print(
        f"Dataset: {DATASET_NAME}"
    )

    print(
        f"Audio output: {AUDIO_DIR}"
    )

    print(
        f"RTTM output:  {RTTM_DIR}"
    )

    # --------------------------------------------------------
    # Load dataset
    # --------------------------------------------------------

    print(
        "\nLoading dataset from Hugging Face..."
    )

    dataset = load_dataset(
        DATASET_NAME,
        split="train"
    )

    print(
        f"Total examples: {len(dataset)}"
    )

    # --------------------------------------------------------
    # Disable automatic audio decoding
    # --------------------------------------------------------

    print(
        "Disabling automatic audio decoding..."
    )

    dataset = dataset.cast_column(
        "audio",
        Audio(decode=False)
    )

    print(
        "Audio decoding disabled successfully."
    )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    total_duration = 0.0
    processed = 0
    skipped = 0
    failed = 0

    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    for idx, example in enumerate(
        tqdm(
            dataset,
            desc="Processing"
        )
    ):

        audio_info = example["audio"]

        # ----------------------------------------------------
        # Determine file ID BEFORE loading audio
        # ----------------------------------------------------

        file_id = get_file_id(
            audio_info,
            idx
        )

        audio_out_path = (
            AUDIO_DIR / f"{file_id}.wav"
        )

        rttm_path = (
            RTTM_DIR / f"{file_id}.rttm"
        )

        # ----------------------------------------------------
        # Skip already processed examples
        # ----------------------------------------------------

        if (
            not args.overwrite
            and audio_out_path.exists()
            and rttm_path.exists()
        ):

            skipped += 1

            continue

        # ----------------------------------------------------
        # Audio extraction
        # ----------------------------------------------------

        temporary_audio = False
        audio_path = None

        try:

            audio_path, temporary_audio = (
                load_audio_from_example(
                    audio_info,
                    idx
                )
            )

            # ------------------------------------------------
            # Load audio
            # ------------------------------------------------

            audio_array, sr = librosa.load(
                audio_path,
                sr=None,
                mono=True
            )

            # ------------------------------------------------
            # Save WAV
            # ------------------------------------------------

            sf.write(
                audio_out_path,
                audio_array,
                sr
            )

            # ------------------------------------------------
            # Duration
            # ------------------------------------------------

            duration = (
                len(audio_array)
                / float(sr)
            )

            # ------------------------------------------------
            # RTTM annotations
            # ------------------------------------------------

            starts = example[
                "timestamps_start"
            ]

            ends = example[
                "timestamps_end"
            ]

            speakers = example[
                "speakers"
            ]

            write_rttm(
                rttm_path,
                file_id,
                starts,
                ends,
                speakers
            )

            total_duration += duration
            processed += 1

            # ------------------------------------------------
            # Report path=None cases
            # ------------------------------------------------

            if isinstance(
                audio_info,
                dict
            ):

                if not audio_info.get(
                    "path"
                ):

                    print(
                        f"\nExample {idx}: "
                        f"audio path is None; "
                        f"using ID {file_id}"
                    )

            # ------------------------------------------------
            # Progress report
            # ------------------------------------------------

            if processed % 10 == 0:

                print(
                    f"\nProcessed: "
                    f"{processed}"
                )

                print(
                    f"Skipped: "
                    f"{skipped}"
                )

                print(
                    f"Failed: "
                    f"{failed}"
                )

                print(
                    f"New duration: "
                    f"{total_duration / 3600:.2f} hours"
                )

        except Exception as exc:

            failed += 1

            print(
                f"\nWARNING: Failed example "
                f"{idx} ({file_id})"
            )

            print(
                f"Error type: "
                f"{type(exc).__name__}"
            )

            print(
                f"Error: "
                f"{exc}"
            )

            # ------------------------------------------------
            # Continue rather than killing the entire
            # 380-example dataset.
            # ------------------------------------------------

            continue

        finally:

            # ------------------------------------------------
            # Delete temporary extracted audio
            # ------------------------------------------------

            if (
                temporary_audio
                and audio_path
                and os.path.exists(
                    audio_path
                )
            ):

                try:
                    os.remove(
                        audio_path
                    )

                except OSError:
                    pass

        # ----------------------------------------------------
        # Subset limit
        # ----------------------------------------------------

        if (
            args.subset_hours is not None
            and total_duration
            >= args.subset_hours * 3600
        ):

            print(
                f"\nReached subset limit of "
                f"{args.subset_hours} hours."
            )

            break

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print("\n")
    print("=" * 70)
    print(
        "DATASET PREPARATION COMPLETE"
    )
    print("=" * 70)

    print(
        f"Dataset examples: "
        f"{len(dataset)}"
    )

    print(
        f"Newly processed: "
        f"{processed}"
    )

    print(
        f"Already existing/skipped: "
        f"{skipped}"
    )

    print(
        f"Failed: "
        f"{failed}"
    )

    print(
        f"New audio duration: "
        f"{total_duration / 3600:.2f} hours"
    )

    print(
        f"\nAudio files:"
    )

    print(
        f"  {AUDIO_DIR}"
    )

    print(
        f"\nRTTM files:"
    )

    print(
        f"  {RTTM_DIR}"
    )

    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()