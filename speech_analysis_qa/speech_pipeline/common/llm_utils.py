# -*- coding: utf-8 -*-
"""
common/llm_utils.py
=====================
One `load_llm()` + one `ask_question()` used by every stage that needs a
chat-style LLM call (speaker-role identification in stage 3, structured
Q&A in stage 4). Previously pyannote_to_json.py and
privacy_rag_2_outputs.py each defined their own near-identical
`ask_question`; this is the single, de-duplicated version.
"""

from typing import Dict, List, Optional, Tuple

_LLM_CACHE: Dict[Tuple[str, str], Tuple[object, object]] = {}


def _cache_key(model_name: str, hf_token: str = "") -> Tuple[str, str]:
    return model_name, hf_token or ""


def load_llm(model_name: str, hf_token: str = ""):
    """Load a 4-bit quantised causal LM + tokenizer. Returns (tokenizer, model)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    cache_key = _cache_key(model_name, hf_token)
    if cache_key in _LLM_CACHE:
        return _LLM_CACHE[cache_key]

    tokenizer = AutoTokenizer.from_pretrained(model_name, use_auth_token=hf_token or None)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        llm_int8_enable_fp32_cpu_offload=True,
    )
    use_auth_token = hf_token or None
    from speech_analysis_qa.speech_pipeline.common.device_utils import get_quantized_device_map

    device_map = get_quantized_device_map()

    try:
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map=device_map,
            dtype=torch.float16,
            low_cpu_mem_usage=True,
            use_auth_token=use_auth_token,
        )
    except ValueError as exc:
        if "offload the whole model to the disk" in str(exc):
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=bnb_config,
                device_map={"": "cpu"},
                torch_dtype=torch.float16,
                use_auth_token=use_auth_token,
            )
        else:
            raise

    _LLM_CACHE[cache_key] = (tokenizer, model)
    return tokenizer, model


def unload_llm(model_name: Optional[str] = None, hf_token: Optional[str] = None):
    import gc
    import torch

    if model_name is None:
        keys = list(_LLM_CACHE.keys())
    else:
        keys = [_cache_key(model_name, hf_token or "")]

    for key in keys:
        tokenizer, model = _LLM_CACHE.pop(key, (None, None))
        if model is not None:
            try:
                model.to("cpu")
            except Exception:
                pass
            del model
        if tokenizer is not None:
            del tokenizer

    gc.collect()
    from speech_analysis_qa.speech_pipeline.common.device_utils import clear_torch_cache

    clear_torch_cache()


def unload_all_llms():
    unload_llm()


def _context_window(tokenizer, model) -> int:
    """Return the usable model context length, ignoring tokenizer sentinels."""
    candidates = [
        getattr(getattr(model, "config", None), "max_position_embeddings", None),
        getattr(getattr(model, "config", None), "n_positions", None),
        getattr(tokenizer, "model_max_length", None),
    ]
    valid = [value for value in candidates if isinstance(value, int) and 0 < value < 1_000_000]
    return min(valid) if valid else 2048


def _trim_chat_inputs(inputs, max_input_tokens: int):
    """Keep the prompt's instructions and final question within the context window."""
    import torch

    input_length = inputs["input_ids"].shape[-1]
    if input_length <= max_input_tokens:
        return inputs

    # Keep both ends: system/prompt rules are at the beginning and the question
    # plus output instructions are at the end.  Retrieval keeps transcript
    # excerpts small, so this is only a final safety net.
    head_length = max_input_tokens // 2
    tail_length = max_input_tokens - head_length
    for key, value in inputs.items():
        if getattr(value, "ndim", 0) >= 2 and value.shape[-1] == input_length:
            inputs[key] = value[..., :head_length]
            inputs[key] = torch.cat((inputs[key], value[..., -tail_length:]), dim=-1)
    print(
        f"WARNING: Prompt was {input_length} tokens; trimmed to "
        f"{max_input_tokens} tokens to fit the model context window."
    )
    return inputs


def ask_question(
    tokenizer,
    model,
    question: str,
    conversation_history: Optional[List[Dict]] = None,
    max_new_tokens: int = 2048,
    do_sample: bool = False,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    repetition_penalty: float = 1.0,
    enable_thinking: bool = False,
) -> str:
    """Send one chat turn to the loaded model and return the decoded reply."""
    import torch

    messages = (conversation_history or []) + [{"role": "user", "content": question}]

    try:
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            enable_thinking=enable_thinking,
        )
    except TypeError:
        # Older tokenizer that doesn't accept enable_thinking.
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )

    context_window = _context_window(tokenizer, model)
    # Always reserve at least one token for generation.  Callers should use
    # modest output limits so retrieved context remains available.
    max_input_tokens = max(1, context_window - min(max_new_tokens, 256))
    inputs = _trim_chat_inputs(inputs, max_input_tokens)
    input_length = inputs["input_ids"].shape[-1]
    max_new_tokens = min(max_new_tokens, max(1, context_window - input_length))
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            temperature=temperature,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
        )

    generated_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(generated_tokens, skip_special_tokens=True)
