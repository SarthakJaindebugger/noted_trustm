# -*- coding: utf-8 -*-
"""
common/device_utils.py
======================
Helper utilities for selecting a compute device and clearing GPU/MPS caches.
"""

from __future__ import annotations

from typing import Any


def is_cuda_available() -> bool:
    import torch

    return getattr(torch.cuda, "is_available", lambda: False)()


def is_mps_available() -> bool:
    import torch

    return getattr(getattr(torch, "backends", None), "mps", None) is not None and getattr(
        torch.backends.mps, "is_available", lambda: False
    )()


def get_compute_device(preferred: str = "auto") -> str:
    """Return the best available device for the requested preference."""
    preferred = (preferred or "auto").strip().lower()
    if preferred in ("auto", ""):
        if is_cuda_available():
            return "cuda"
        if is_mps_available():
            return "mps"
        return "cpu"

    if preferred.startswith("cuda"):
        return preferred if is_cuda_available() else "cpu"

    if preferred == "mps":
        return "mps" if is_mps_available() else "cpu"

    return preferred


def get_quantized_device_map() -> Any:
    """Return a device map for quantized models that prefers CUDA if available."""
    if is_cuda_available():
        return "auto"
    return {"": "cpu"}


def clear_torch_cache() -> None:
    import torch

    if is_cuda_available():
        torch.cuda.empty_cache()
    elif is_mps_available():
        try:
            torch.mps.empty_cache()
        except Exception:
            pass
