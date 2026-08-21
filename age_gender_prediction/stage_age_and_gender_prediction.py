# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-

"""
Speaker Diarization + Age Group + Gender Estimation
====================================================
"""

# ============================================================
# 1. IMPORTS
# ============================================================

import os
# Disable numba caching to fix librosa import issues
os.environ['NUMBA_CACHE_DIR'] = '/tmp/numba_cache'
os.environ['NUMBA_DISABLE_CACHE'] = '1'

import argparse
import contextlib
import functools
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import numpy as np
import torch
import torch.nn as nn
import librosa
"""
Speaker Diarization + Age Group + Gender Estimation
====================================================

Pipeline:
    1. pyannote/speaker-diarization-3.1 splits the audio into speaker turns.
    2. For every speaker, several *independent* speech segments (no
       concatenation across turns) are fed one at a time into audEERING's
       wav2vec2 age/gender model.
    3. Per-segment predictions are combined into a single robust estimate
       per speaker using duration-weighted statistics (longer, cleaner
       segments count for more than short/noisy ones).
    4. Speakers whose voice is judged to belong to a minor (either via the
       age head or the gender model's "child" class) are reported as
       Not Available, as a safety measure.

Output example:
    Speaker_00: Gender: Male, Age: 30-49, Gender Confidence: 0.87, Age Confidence: 0.75, Segments Used: 6/6
    Speaker_01: Gender: Not Available, Age: Not Available, Gender Confidence: Not Available, Age Confidence: Not Available

Usage:
    python speaker_age_gender_diarization.py --audio /path/to/file.wav
    (falls back to AUDIO_PATH below if --audio is not given)
"""

# ============================================================
# 1. IMPORTS
# ============================================================

import os
import argparse
import contextlib
import functools
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import numpy as np
import torch
import torch.nn as nn
import librosa


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("diarization")


# ============================================================
# 2. CONFIGURATION
# ============================================================

AUDIO_PATH_DEFAULT = (
    "/scratch/work/jains6/noted/noted-main/"
    "knowledgebase/users_admin_data/users/alice/"
    "recordings/dia01sce1SA_1fb1239a.wav"
)

HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")

DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
AGE_GENDER_MODEL = "audeering/wav2vec2-large-robust-24-ft-age-gender"

SAMPLE_RATE = 16000

# --- Speaker speech selection -------------------------------------------
MAX_SEGMENT_SECONDS = 10.0                 # cap per individual clip fed to the model
MAX_SPEECH_SECONDS_PER_SPEAKER = 60.0      # cap on total audio analyzed per speaker
MAX_SEGMENTS_PER_SPEAKER = 20              # hard cap on number of clips (compute bound)
MIN_SEGMENT_SECONDS = 2.0                  # a clip shorter than this is unreliable for the model
MIN_SPEECH_SECONDS_PER_SPEAKER = 5.0       # speaker needs at least this much *total* diarized speech

# --- Safety -----------------------------------------------------------
CHILD_PROB_THRESHOLD = 0.5                 # gender head "child" class veto threshold

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

AGE_GROUPS = {
    "a": "Under 18",
    "b": "18-29",
    "c": "30-49",
    "d": "50-64",
    "e": "Over 65",
}


def age_to_group(age: float):
    if age < 18:
        return "a", AGE_GROUPS["a"]
    elif age < 30:
        return "b", AGE_GROUPS["b"]
    elif age < 50:
        return "c", AGE_GROUPS["c"]
    elif age < 65:
        return "d", AGE_GROUPS["d"]
    else:
        return "e", AGE_GROUPS["e"]


# ============================================================
# 3. SCOPED CHECKPOINT-LOADING COMPATIBILITY PATCH
# ============================================================
#
# PyTorch >= 2.6 defaults torch.load(weights_only=True), which breaks
# loading some older pretrained checkpoints (pyannote, audEERING) that
# were pickled with weights_only=False in mind. Rather than permanently
# disabling this security check for the whole process (which is what a
# global monkeypatch does), we only relax it for the duration of the
# model-loading calls and then restore the original behavior.

@contextlib.contextmanager
def relaxed_checkpoint_loading():
    original_torch_load = torch.load
    original_serialization_load = torch.serialization.load

    try:
        torch.serialization.add_safe_globals([torch.torch_version.TorchVersion])
    except Exception as e:
        log.warning("safe-global registration failed: %s", e)

    @functools.wraps(original_torch_load)
    def patched_torch_load(*args, **kwargs):
        # Force this rather than setdefault(): some callers (e.g. Lightning's
        # checkpoint loader on torch>=2.6) pass weights_only=True explicitly,
        # and setdefault would silently leave that in place, defeating the
        # patch. This is safe specifically because it only applies for the
        # lifetime of this context manager, around trusted model loads.
        kwargs["weights_only"] = False
        return original_torch_load(*args, **kwargs)

    @functools.wraps(original_serialization_load)
    def patched_serialization_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return original_serialization_load(*args, **kwargs)

    torch.load = patched_torch_load
    torch.serialization.load = patched_serialization_load
    try:
        yield
    finally:
        torch.load = original_torch_load
        torch.serialization.load = original_serialization_load


# ============================================================
# 4. HUGGING FACE AUTH
# ============================================================

def authenticate_huggingface(token: Optional[str]) -> None:
    if not token:
        try:
            from huggingface_hub import HfFolder
            token = HfFolder.get_token()
        except Exception:
            token = None

    if not token:
        log.warning("No Hugging Face token found; gated models may fail to load.")
        return

    try:
        from huggingface_hub import login
        login(token=token, add_to_git_credential=False)
        log.info("Hugging Face authentication successful.")
    except Exception as e:
        log.warning("Hugging Face login failed: %s", e)


# ============================================================
# 5. MODEL DEFINITIONS (audEERING age/gender head)
# ============================================================

from transformers import Wav2Vec2Processor, Wav2Vec2Model, Wav2Vec2PreTrainedModel


class ModelHead(nn.Module):
    def __init__(self, config, num_labels):
        super().__init__()
        self.dense = nn.Linear(config.hidden_size, config.hidden_size)
        self.dropout = nn.Dropout(config.final_dropout)
        self.out_proj = nn.Linear(config.hidden_size, num_labels)

    def forward(self, features, **kwargs):
        x = self.dropout(features)
        x = torch.tanh(self.dense(x))
        x = self.dropout(x)
        return self.out_proj(x)


class AgeGenderModel(Wav2Vec2PreTrainedModel):
    """
    gender classes: 0 = female, 1 = male, 2 = child
    age: single continuous regression output, pre-scaled to ~[0, 1] * 100 years
    """

    def __init__(self, config):
        super().__init__(config)
        self.config = config
        self.wav2vec2 = Wav2Vec2Model(config)
        self.age = ModelHead(config, 1)
        self.gender = ModelHead(config, 3)
        self.post_init()

    def forward(self, input_values, attention_mask=None):
        outputs = self.wav2vec2(input_values, attention_mask=attention_mask)
        hidden_states = outputs[0]  # (batch, feature_time, hidden)

        if attention_mask is not None:
            # attention_mask is defined at the RAW AUDIO SAMPLE rate, but
            # hidden_states has already been downsampled by the conv
            # feature extractor (stride ~320x). They must not be multiplied
            # directly -- project the mask down to feature-frame resolution
            # first using Wav2Vec2's own helper, then masked-mean-pool so
            # padded timesteps (relevant once clips are batched together)
            # don't bias the pooled representation. With a single-clip
            # batch this reduces to a plain mean, since nothing is padded.
            feat_lengths = self.wav2vec2._get_feat_extract_output_lengths(
                attention_mask.sum(-1)
            )
            feat_mask = torch.zeros(
                hidden_states.shape[:2], dtype=hidden_states.dtype, device=hidden_states.device
            )
            for i, length in enumerate(feat_lengths):
                feat_mask[i, : int(length)] = 1.0
            feat_mask = feat_mask.unsqueeze(-1)
            summed = (hidden_states * feat_mask).sum(dim=1)
            counts = feat_mask.sum(dim=1).clamp(min=1e-6)
            pooled = summed / counts
        else:
            pooled = torch.mean(hidden_states, dim=1)

        age_logits = self.age(pooled)
        gender_logits = self.gender(pooled)
        return pooled, age_logits, gender_logits


# ============================================================
# 6. DATA STRUCTURES
# ============================================================

@dataclass
class SegmentPrediction:
    duration: float
    age: float
    age_group_code: str
    female: float
    male: float
    child: float


@dataclass
class SpeakerResult:
    speaker: str
    available: bool
    gender: Optional[str] = None
    age_group: Optional[str] = None
    gender_confidence: Optional[float] = None
    age_confidence: Optional[float] = None
    segments_used: int = 0
    segments_attempted: int = 0
    reason: Optional[str] = None


# ============================================================
# 7. AUDIO / SEGMENT HELPERS
# ============================================================

def load_audio(path: str, sample_rate: int) -> np.ndarray:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Audio file not found:\n{path}")
    audio, _ = librosa.load(path, sr=sample_rate, mono=True)
    return audio.astype(np.float32)


def collect_speaker_segments(annotation) -> Dict[str, List[dict]]:
    """All diarized turns per speaker, unfiltered by length (used for the
    'does this speaker talk enough overall' eligibility check)."""
    speaker_segments: Dict[str, List[dict]] = {}
    for segment, _, speaker in annotation.itertracks(yield_label=True):
        start, end = float(segment.start), float(segment.end)
        speaker_segments.setdefault(speaker, []).append(
            {"start": start, "end": end, "duration": end - start}
        )
    return dict(sorted(speaker_segments.items()))


def select_analysis_segments(segments: List[dict]) -> List[dict]:
    """
    Pick which turns actually get sent to the model.

    Strategy: only consider turns long enough to yield a reliable
    embedding (>= MIN_SEGMENT_SECONDS), prefer longer/cleaner turns,
    but keep temporal spread across the recording rather than only
    taking the first N seconds -- a speaker who is quiet early and
    talkative later shouldn't be judged only on their first turns.
    """
    usable = [s for s in segments if s["duration"] >= MIN_SEGMENT_SECONDS]
    if not usable:
        return []

    # Sort candidates by duration (longest = usually cleanest audio),
    # but interleave picks from early/middle/late thirds of the speaker's
    # timeline for temporal diversity.
    usable_sorted_by_time = sorted(usable, key=lambda s: s["start"])
    n = len(usable_sorted_by_time)
    thirds = [
        usable_sorted_by_time[: n // 3 or n],
        usable_sorted_by_time[n // 3: 2 * n // 3] or usable_sorted_by_time,
        usable_sorted_by_time[2 * n // 3:] or usable_sorted_by_time,
    ]
    for bucket in thirds:
        bucket.sort(key=lambda s: s["duration"], reverse=True)

    interleaved = []
    seen_ids = set()
    idx = 0
    while len(interleaved) < n and idx < n:
        bucket = thirds[idx % 3]
        pos = idx // 3
        if pos < len(bucket):
            cand = bucket[pos]
            key = (cand["start"], cand["end"])
            if key not in seen_ids:
                interleaved.append(cand)
                seen_ids.add(key)
        idx += 1

    selected = []
    total_duration = 0.0
    for seg in interleaved:
        if total_duration >= MAX_SPEECH_SECONDS_PER_SPEAKER:
            break
        if len(selected) >= MAX_SEGMENTS_PER_SPEAKER:
            break
        clip_len = min(seg["duration"], MAX_SEGMENT_SECONDS)
        clip_len = min(clip_len, MAX_SPEECH_SECONDS_PER_SPEAKER - total_duration)
        if clip_len < MIN_SEGMENT_SECONDS:
            continue
        selected.append({"start": seg["start"], "end": seg["start"] + clip_len, "duration": clip_len})
        total_duration += clip_len

    return selected


def extract_clip(audio: np.ndarray, sr: int, start: float, end: float) -> np.ndarray:
    start_sample = max(0, int(start * sr))
    end_sample = min(len(audio), int(end * sr))
    if end_sample <= start_sample:
        return np.array([], dtype=np.float32)
    clip = audio[start_sample:end_sample]
    return clip.astype(np.float32)


def preprocess_clip(clip: np.ndarray, sr: int) -> Optional[np.ndarray]:
    """Trim leading/trailing silence and peak-normalize. Returns None if
    nothing usable remains."""
    if clip.size == 0:
        return None

    try:
        trimmed, _ = librosa.effects.trim(clip, top_db=30)
    except Exception:
        trimmed = clip

    if trimmed.size < int(MIN_SEGMENT_SECONDS * sr * 0.5):
        # trimming ate almost the whole clip (mostly silence) -> skip
        return None

    peak = np.max(np.abs(trimmed))
    if peak > 1e-4:
        trimmed = trimmed / peak * 0.95

    return trimmed.astype(np.float32)


# ============================================================
# 8. INFERENCE
# ============================================================

def predict_segment(clip: np.ndarray, processor, model, device) -> Optional[SegmentPrediction]:
    inputs = processor(clip, sampling_rate=SAMPLE_RATE, return_tensors="pt", padding=True)
    input_values = inputs["input_values"].to(device)
    attention_mask = inputs.get("attention_mask")
    if attention_mask is not None:
        attention_mask = attention_mask.to(device)

    with torch.no_grad():
        _, age_output, gender_output = model(input_values, attention_mask=attention_mask)

    age_value = float(age_output[0, 0].detach().cpu().item())
    if not np.isfinite(age_value):
        return None

    # audEERING's age head output is already ~normalized to [0, 1] * 100y;
    # no sigmoid is applied here, matching the official model usage.
    estimated_age = float(np.clip(age_value * 100.0, 0.0, 100.0))
    age_code, _ = age_to_group(estimated_age)

    gender_probs = torch.softmax(gender_output, dim=1)[0].detach().cpu().numpy()
    if not np.all(np.isfinite(gender_probs)):
        return None

    return SegmentPrediction(
        duration=0.0,  # filled in by caller
        age=estimated_age,
        age_group_code=age_code,
        female=float(gender_probs[0]),
        male=float(gender_probs[1]),
        child=float(gender_probs[2]),
    )


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cum_weights = np.cumsum(weights)
    cutoff = weights.sum() / 2.0
    idx = np.searchsorted(cum_weights, cutoff)
    idx = min(idx, len(values) - 1)
    return float(values[idx])


def aggregate_speaker(speaker: str, predictions: List[SegmentPrediction]) -> SpeakerResult:
    ages = np.array([p.age for p in predictions], dtype=np.float64)
    weights = np.array([p.duration for p in predictions], dtype=np.float64)
    weights = np.where(weights <= 0, 1e-6, weights)

    # Remove extreme outliers (duration-agnostic IQR filter), but never
    # collapse below 3 samples if we have that many to begin with.
    keep_mask = np.ones(len(ages), dtype=bool)
    if len(ages) >= 5:
        q1, q3 = np.percentile(ages, [25, 75])
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        candidate_mask = (ages >= lower) & (ages <= upper)
        if candidate_mask.sum() >= 3:
            keep_mask = candidate_mask

    kept_ages = ages[keep_mask]
    kept_weights = weights[keep_mask]

    final_age = weighted_median(kept_ages, kept_weights)
    final_age_code, final_age_label = age_to_group(final_age)

    # Age confidence: duration-weighted share of the *same* filtered
    # sample set that agrees with the final age group (consistent with
    # how final_age itself was computed, unlike a mismatched raw count).
    kept_codes = np.array([p.age_group_code for i, p in enumerate(predictions) if keep_mask[i]])
    agree_weight = kept_weights[kept_codes == final_age_code].sum()
    age_confidence = float(agree_weight / kept_weights.sum())

    # Gender: duration-weighted mean over ALL usable segments (gender is
    # less affected by momentary outliers than a raw pitch/age estimate).
    female = np.array([p.female for p in predictions])
    male = np.array([p.male for p in predictions])
    child = np.array([p.child for p in predictions])
    w = weights / weights.sum()

    female_mean = float(np.sum(female * w))
    male_mean = float(np.sum(male * w))
    child_mean = float(np.sum(child * w))

    class_probs = {"Female": female_mean, "Male": male_mean, "Child": child_mean}
    top_class = max(class_probs, key=class_probs.get)
    top_prob = class_probs[top_class]

    # --- Safety: two independent minor-voice signals ---
    # 1) the regression age head puts them under 18
    # 2) the classification head's "child" class independently wins
    is_minor = (final_age_code == "a") or (child_mean >= CHILD_PROB_THRESHOLD) or (top_class == "Child")

    if is_minor:
        return SpeakerResult(
            speaker=speaker,
            available=False,
            reason="voice judged to belong to a minor",
            segments_attempted=len(predictions),
        )

    final_gender = "Male" if male_mean >= female_mean else "Female"
    gender_confidence = male_mean if final_gender == "Male" else female_mean

    return SpeakerResult(
        speaker=speaker,
        available=True,
        gender=final_gender,
        age_group=final_age_label,
        gender_confidence=gender_confidence,
        age_confidence=age_confidence,
        segments_used=len(predictions),
        segments_attempted=len(predictions),
    )


# ============================================================
# 9. MAIN PIPELINE
# ============================================================

def load_diarization_pipeline():
    from pyannote.audio import Pipeline
    log.info("Loading diarization model: %s", DIARIZATION_MODEL)
    with relaxed_checkpoint_loading():
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL)
    pipeline.to(DEVICE)
    log.info("Diarization model loaded.")
    return pipeline


def load_age_gender_model():
    log.info("Loading age/gender model: %s", AGE_GENDER_MODEL)
    processor = Wav2Vec2Processor.from_pretrained(AGE_GENDER_MODEL)
    with relaxed_checkpoint_loading():
        model = AgeGenderModel.from_pretrained(AGE_GENDER_MODEL)
    model.to(DEVICE)
    model.eval()
    log.info("Age/gender model loaded.")
    return processor, model


def run_diarization(pipeline, audio: np.ndarray, sr: int):
    waveform = torch.from_numpy(audio).float().unsqueeze(0)
    diarization = pipeline({"waveform": waveform, "sample_rate": sr})
    annotation = getattr(diarization, "speaker_diarization", diarization)
    return annotation


def process_speaker(speaker: str, segments: List[dict], audio: np.ndarray, sr: int,
                     processor, model, device) -> SpeakerResult:
    total_speech_all = sum(s["duration"] for s in segments)
    if total_speech_all < MIN_SPEECH_SECONDS_PER_SPEAKER:
        return SpeakerResult(speaker=speaker, available=False,
                              reason="not enough total diarized speech")

    analysis_segments = select_analysis_segments(segments)
    if not analysis_segments:
        return SpeakerResult(speaker=speaker, available=False,
                              reason="no segment long enough to analyze")

    predictions: List[SegmentPrediction] = []
    for seg in analysis_segments:
        raw_clip = extract_clip(audio, sr, seg["start"], seg["end"])
        clip = preprocess_clip(raw_clip, sr)
        if clip is None:
            continue
        try:
            pred = predict_segment(clip, processor, model, device)
        except Exception as e:
            log.warning("[%s] segment prediction failed: %s", speaker, e)
            continue
        if pred is None:
            continue
        pred.duration = seg["duration"]
        predictions.append(pred)

    if not predictions:
        return SpeakerResult(speaker=speaker, available=False,
                              reason="all segment predictions failed",
                              segments_attempted=len(analysis_segments))

    result = aggregate_speaker(speaker, predictions)
    result.segments_attempted = len(analysis_segments)
    return result


def format_result(result: SpeakerResult) -> str:
    if not result.available:
        return (
            f"{result.speaker}: Gender: Not Available, Age: Not Available, "
            f"Gender Confidence: Not Available, Age Confidence: Not Available"
            + (f"  ({result.reason})" if result.reason else "")
        )
    return (
        f"{result.speaker}: Gender: {result.gender}, Age: {result.age_group}, "
        f"Gender Confidence: {result.gender_confidence:.3f}, "
        f"Age Confidence: {result.age_confidence:.3f}, "
        f"Segments Used: {result.segments_used}/{result.segments_attempted}"
    )


def main():
    parser = argparse.ArgumentParser(description="Speaker diarization + age/gender estimation")
    parser.add_argument("--audio", type=str, default=AUDIO_PATH_DEFAULT, help="Path to input audio file")
    args = parser.parse_args()

    log.info("Device: %s", DEVICE)

    authenticate_huggingface(HF_TOKEN)

    diarization_pipeline = load_diarization_pipeline()
    processor, age_gender_model = load_age_gender_model()

    log.info("Loading audio: %s", args.audio)
    audio = load_audio(args.audio, SAMPLE_RATE)
    log.info("Audio duration: %.2fs", len(audio) / SAMPLE_RATE)

    log.info("Running diarization...")
    annotation = run_diarization(diarization_pipeline, audio, SAMPLE_RATE)
    speaker_segments = collect_speaker_segments(annotation)

    for speaker, segments in speaker_segments.items():
        total = sum(s["duration"] for s in segments)
        log.info("%s: %d turns, %.2fs total speech", speaker, len(segments), total)

    print()
    print("=" * 70)
    print("SPEAKER AGE GROUP / GENDER ESTIMATION")
    print("=" * 70)
    for speaker, segments in speaker_segments.items():
        result = process_speaker(speaker, segments, audio, SAMPLE_RATE,
                                  processor, age_gender_model, DEVICE)
        print(format_result(result))

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()