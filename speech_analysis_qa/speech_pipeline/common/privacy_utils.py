# -*- coding: utf-8 -*-
"""
common/privacy_utils.py
=========================
Anonymisation logic, refactored out of privacy_json.py into a reusable
class. Regex-based redaction (Finnish HETU / passport / phone), spaCy
NER-based name redaction, and address shortening are all encapsulated in
`PlaceholderMapper`, whose `entity_mapping` / `reverse_mapping` become the
"mapping.json" that stage 5 uses to de-anonymise the final results.
"""

import re
from collections import defaultdict
from typing import Dict, List, Optional

from speech_analysis_qa.speech_pipeline.common.config import REGEX_PATTERNS


class PlaceholderMapper:
    """Anonymises transcript segments and remembers original<->placeholder
    values so the mapping can be saved and later reversed."""

    def __init__(self, nlp):
        self.nlp = nlp
        self.entity_mapping: Dict[str, str] = {}
        self.reverse_mapping: Dict[str, str] = {}
        self._counters = defaultdict(int)

    # -- placeholder bookkeeping ------------------------------------------
    def _create_placeholder(self, prefix: str, original: str) -> str:
        if original in self.entity_mapping:
            return self.entity_mapping[original]

        self._counters[prefix] += 1
        placeholder = f"<{prefix}_{self._counters[prefix]}>"

        self.entity_mapping[original] = placeholder
        self.reverse_mapping[placeholder] = original
        return placeholder

    # -- regex pass (HETU / passport / phone) ------------------------------
    def _anonymize_regex(self, text: str) -> str:
        for prefix, pattern in REGEX_PATTERNS.items():
            def repl(match, prefix=prefix):
                return self._create_placeholder(prefix, match.group())
            text = re.sub(pattern, repl, text)
        return text

    # -- NER pass (names only) ---------------------------------------------
    def _anonymize_entities(self, text: str) -> str:
        doc = self.nlp(text)
        entities = sorted(doc.ents, key=lambda e: len(e.text), reverse=True)

        for ent in entities:
            if ent.label_ != "PERSON":
                continue
            placeholder = self._create_placeholder("PERSON", ent.text)
            text = re.sub(r"\b{}\b".format(re.escape(ent.text)), placeholder, text)
        return text

    # -- address shortening (keep only city/country) ------------------------
    def _redact_addresses(self, text: str) -> str:
        doc = self.nlp(text)
        gpe_entities = [ent for ent in doc.ents if ent.label_ == "GPE"]
        if not gpe_entities:
            return text

        spans_to_replace = []
        for ent in gpe_entities:
            start_tok = ent.start
            found_digit = False
            for i in range(ent.start - 1, max(ent.start - 7, -1), -1):
                if doc[i].like_num and any(c.isdigit() for c in doc[i].text):
                    start_tok = i
                    found_digit = True
                    break
            if not found_digit:
                continue

            end_tok = ent.end
            for i in range(ent.end, len(doc)):
                if doc[i].ent_type_ == "GPE":
                    end_tok = i + 1
                else:
                    break

            kept_parts = [tok.text for tok in doc[start_tok:end_tok] if tok.ent_type_ == "GPE"]
            if not kept_parts:
                continue

            replacement = ", ".join(dict.fromkeys(kept_parts))
            start_char = doc[start_tok].idx
            end_char = doc[end_tok - 1].idx + len(doc[end_tok - 1])
            spans_to_replace.append((start_char, end_char, replacement))

        spans_to_replace.sort(key=lambda x: x[0], reverse=True)
        for start_char, end_char, repl in spans_to_replace:
            text = text[:start_char] + repl + text[end_char:]
        return text

    # -- public entry point --------------------------------------------------
    def anonymize_text(self, text: str) -> str:
        text = self._anonymize_regex(text)
        text = self._anonymize_entities(text)
        text = self._redact_addresses(text)
        return text

    def anonymize_segments(self, segments: List[Dict]) -> List[Dict]:
        """Anonymise the "text" field of each segment, leaving start/end/
        speaker untouched (stage 3 needs those for timing)."""
        private_segments = []
        for seg in segments:
            seg = seg.copy()
            seg["text"] = self.anonymize_text(seg.get("text", ""))
            private_segments.append(seg)
        return private_segments


def load_spacy_model(model_name: Optional[str] = None):
    import spacy
    from speech_analysis_qa.speech_pipeline.common.config import SPACY_MODEL

    return spacy.load(model_name or SPACY_MODEL)
