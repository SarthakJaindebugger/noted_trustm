"""
FAQ Generator — reads all submitted CRM forms, collects Q20 (Additional Info)
and Q22 (Other Feedback) text, sends to LLM to produce short Q&A pairs.
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "speech_analysis_qa" / "speech_pipeline"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

SKIP_VALUES = {"Not mentioned in transcript.", "", None}


def _collect_texts_from_forms() -> List[str]:
    """Collect Q20 and Q22 text from all submitted CRM forms."""
    from services.admin_audio_analysis import get_submitted_crm_root

    root = get_submitted_crm_root()
    if not root.exists():
        return []

    texts = []
    for file_path in root.glob("*.json"):
        if not file_path.is_file():
            continue
        try:
            record = json.loads(file_path.read_text(encoding="utf-8"))
            f = record.get("form", {})
            q = record.get("questionnaire", {})

            q20 = f.get("additionalInfoText") or q.get("Any Additional Information", "")
            q22 = f.get("otherFeedback") or q.get("Any other Feedback", "")

            if q20 and q20 not in SKIP_VALUES:
                texts.append(q20)
            if q22 and q22 not in SKIP_VALUES:
                texts.append(q22)
        except Exception:
            continue

    return texts


def generate_faqs_from_forms() -> List[Dict[str, str]]:
    """Generate FAQ entries from all submitted form texts using LLM."""
    from speech_analysis_qa.speech_pipeline.common.config import HF_TOKEN, QA_MODEL_NAME
    from speech_analysis_qa.speech_pipeline.common.llm_utils import load_llm, ask_question
    from speech_analysis_qa.speech_pipeline.common.json_utils import extract_json

    texts = _collect_texts_from_forms()
    if not texts:
        logger.info("No Q20/Q22 texts found in submitted forms.")
        return []

    combined = "\n---\n".join(texts[:20])

    logger.info(f"Generating FAQs from {len(texts)} text entries...")
    tokenizer, model = load_llm(QA_MODEL_NAME, HF_TOKEN)

    prompt = f"""You are an expert at creating FAQ documents for immigration advisory services.

Below are notes from multiple customer service encounters (additional info and feedback from advisors). Based on these, generate 8-10 frequently asked questions that customers commonly have, with short practical answers.

Rules:
- Each question should be SHORT (one line, under 15 words)
- Each answer should be SHORT and practical (1-2 sentences max)
- Focus on the most common and useful topics across all entries
- Questions should be from the CUSTOMER's perspective
- Answers should be what an advisor would tell them

Customer service notes:
\"\"\"
{combined}
\"\"\"

Return ONLY a JSON array of objects with "question" and "answer" keys.
Example: [{{"question": "How do I apply for daycare?", "answer": "Contact your municipality's early childhood education office or apply online through espoo.fi."}}]"""

    raw = ask_question(tokenizer, model, prompt, max_new_tokens=1024)

    try:
        parsed = extract_json(raw)
        if isinstance(parsed, list):
            faqs = []
            for item in parsed:
                if isinstance(item, dict) and "question" in item and "answer" in item:
                    faqs.append({
                        "question": str(item["question"]).strip(),
                        "answer": str(item["answer"]).strip(),
                    })
            logger.info(f"Generated {len(faqs)} FAQs.")
            return faqs[:10]
    except Exception:
        pass

    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            faqs = [{"question": str(x.get("question", "")), "answer": str(x.get("answer", ""))}
                    for x in parsed if isinstance(x, dict) and "question" in x]
            return faqs[:10]
    except Exception:
        pass

    logger.error("Failed to parse LLM FAQ output")
    return []
