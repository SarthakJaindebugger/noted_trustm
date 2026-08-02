import torch

# Monkey-patch torch.load
_original_load = torch.load

def patched_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _original_load(*args, **kwargs)

torch.load = patched_load

from pyannote.audio import Pipeline

pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token="YOUR_REAL_HF_TOKEN",   # not "YOUR_TOKEN"
)

print("Loaded successfully!")