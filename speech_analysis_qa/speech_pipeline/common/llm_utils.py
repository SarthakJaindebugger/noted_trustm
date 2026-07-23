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

from typing import List, Dict, Optional


def load_llm(model_name: str, hf_token: str = ""):
    """Load a 4-bit quantised causal LM + tokenizer. Returns (tokenizer, model)."""
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

    tokenizer = AutoTokenizer.from_pretrained(model_name, token=hf_token or None)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
        token=hf_token or None,
    )
    return tokenizer, model


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
