# -*- coding: utf-8 -*-
"""
Stage 4 · Private Transcript -> Questions & Answers JSON (private)
======================================================================
Runs the structured questionnaire (common/questions.py) plus a summary,
"Any Additional Information" and "Any other Feedback" over the PRIVATE
(placeholder-containing) transcript, using retrieval-augmented context.
Output still contains <PERSON_1>-style placeholders -- de-anonymisation
happens in stage 5.

Refactored from privacy_rag_2_outputs.py. LLM plumbing now comes from
common/llm_utils.py + common/json_utils.py, retrieval comes from
common/retrieval_utils.py, and the question bank comes from
common/questions.py, so none of that is redefined here.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from speech_analysis_qa.speech_pipeline.common.config import (
    HF_TOKEN, QA_MODEL_NAME, EMBED_MODEL_NAME, CHUNK_SIZE, OVERLAP, TOP_K,
    MAX_CHARS_FOR_FULL_CONTEXT, PLACEHOLDER_NOTE,
)
from speech_analysis_qa.speech_pipeline.common.text_utils import segments_to_text
from speech_analysis_qa.speech_pipeline.common.json_utils import clean_answer, extract_json
from speech_analysis_qa.speech_pipeline.common.llm_utils import load_llm, ask_question, unload_llm
from speech_analysis_qa.speech_pipeline.common.retrieval_utils import Retriever
from speech_analysis_qa.speech_pipeline.common.questions import QUESTION_GROUPS


# --------------------------------------------------------------------
# Summary / additional-info / feedback generators
# --------------------------------------------------------------------
def generate_summary(tokenizer, model, full_text: str) -> str:
    # The Q&A model has a 2,048-token window; the detailed prompt itself uses
    # much of it, so keep this source excerpt deliberately small.
    truncated = full_text[:1800]
    prompt = f"""
    You are an expert conversation summarizer.

    The transcript below has been PRIVACY-PRESERVED. Personal information has been
    intentionally replaced with placeholders such as:
{PLACEHOLDER_NOTE}
    Rules:
    1. Treat every placeholder as the ORIGINAL value.
    2. NEVER replace placeholders with words such as anonymous/unknown/redacted/hidden.
    3. NEVER invent or guess the original values.
    4. Preserve placeholders exactly as they appear.
    5. Summarize ONLY information explicitly present in the transcript. Do not infer.
    6. Do NOT include reasoning or <think> tags. Return ONLY the summary text.

    Write a concise factual summary (maximum 150 words) covering:
    - Main topics discussed
    - Important customer circumstances
    - Decisions made
    - Advice provided by the advisor
    - Action items or next steps

    Transcript
    -------------------------
    {truncated}
    -------------------------

    Summary:
    """
    return clean_answer(ask_question(tokenizer, model, prompt, max_new_tokens=256).strip())


def _generate_short_field(tokenizer, model, field_name: str, task_text: str,
                           transcript: str, previous_answers: Dict, max_new_tokens: int) -> str:
    previous = json.dumps(previous_answers, indent=2, ensure_ascii=False)
    prompt = f"""
    You are an expert analyst extracting metadata from a PRIVACY-PRESERVING (ANONYMIZED) customer-advisor conversation.
    Your task is to produce ONLY the value for "{field_name}".

    The transcript has been intentionally anonymized. Placeholders such as:
{PLACEHOLDER_NOTE}
    QUESTIONNAIRE ANSWERS
    {previous}

    TRANSCRIPT
    {transcript}

    TASK
    {task_text}

    OUTPUT RULES: Return ONLY the answer text (1-3 sentences). No JSON, no reasoning, no <think>, no markdown.
    """
    return clean_answer(ask_question(tokenizer, model, prompt, max_new_tokens=max_new_tokens).strip())


def generate_additional_information(tokenizer, model, transcript: str, previous_answers: Dict) -> str:
    task_text = """
    The questionnaire above already captures: contact method, immigration reason,
    customer background, education, birth country, language, domicile, employment
    status, duration in Finland, visit contents, purpose of visit, referral
    destination. Avoid word-for-word repeating those exact answers.

    From the transcript, extract any other useful detail an advisor/case worker
    would want on record -- e.g. the customer's specific situation or constraints,
    what they were told or promised, options discussed, numbers/facts mentioned
    (capacities, counts, timelines), next steps, or anything noteworthy about the
    conversation. It is fine if this lightly overlaps with a questionnaire topic as
    long as it adds detail beyond the short questionnaire answer.

    Only return "Not mentioned in transcript." if the transcript truly contains
    nothing beyond what's already a direct 1:1 duplicate of a questionnaire answer.
    Prefer extracting SOMETHING concrete over defaulting to "Not mentioned."
    """
    return _generate_short_field(tokenizer, model, "Any Additional Information", task_text,
                                  transcript, previous_answers, max_new_tokens=256)


def generate_feedback(tokenizer, model, transcript: str, previous_answers: Dict) -> str:
    task_text = """
    Look for anything resembling feedback: advisor's professional observations or
    recommendations, comments about the service/session itself, difficulties the
    advisor noted, suggestions the advisor gave beyond directly answering the
    customer's question, tone/satisfaction cues, or process/communication notes
    (e.g. things left unresolved, follow-ups the advisor promised to do).

    Only return "Not mentioned in transcript." if there is truly no such content
    anywhere in the transcript. Prefer extracting SOMETHING concrete over
    defaulting to "Not mentioned."
    """
    return _generate_short_field(tokenizer, model, "Any other Feedback", task_text,
                                  transcript, previous_answers, max_new_tokens=256)




# --------------------------------------------------------------------
# Questionnaire instruction block (shared across all groups)
# --------------------------------------------------------------------
INSTRUCTION = f"""
    You are an expert analyst extracting structured data from a PRIVACY-PRESERVING (ANONYMIZED) customer-advisor conversation.

    ====================================================
    IMPORTANT - ANONYMIZED TRANSCRIPT
    ====================================================
    The transcript has been intentionally anonymized. Personal information has been
    replaced with placeholders such as:
{PLACEHOLDER_NOTE}
    Always output them exactly as they appear in the transcript.

    ====================================================
    EXTRACTION RULES
    ====================================================
    1. Questions with listed options
       - Read the whole conversation context carefully before deciding -- the relevant
         detail may be mentioned only briefly or indirectly.
       - Select the option whose description most closely matches what actually
         happened/was discussed, even if the wording differs.
       - Only answer "Not mentioned in transcript." if the topic is genuinely absent.
       - Return the COMPLETE option text exactly as written (letter + description).
    2. Questions containing an "If something else type" / "If other, then type" option
       - If a listed option clearly matches, return the full option text.
       - If NONE apply, extract a short custom description from the transcript instead
         of returning the "other" placeholder option.
       - If nothing relevant is present, return "Not mentioned in transcript."
    3. Ques.21 (Where the customer is directed)
       - The answer MUST be exactly one of the provided options, full text.
       - If the conversation itself IS the guidance session, use "Case closed" or
         "Customer service continues/Make a new appointment", whichever fits.
       - Never invent a destination that isn't one of the listed options.
    4. Questions without options
       - Give a concise factual answer using only the transcript. Do not infer or guess.
       - Keep any actual placeholder (<PERSON_n>, <FINNISH_HETU_n>, <PASSPORT_n>,
         <PHONE_n>) exactly as is.
    5. Address / domicile / birth-place style questions
       - City and country are plain, real text (e.g. "Espoo, Finland"), never a
         <CITY_n>/<COUNTRY_n> placeholder -- copy the real words as they appear.
       - Do not add street names, postal codes, or other address details.
    6. Missing information -> "Not mentioned in transcript."
    7. Use ONLY the supplied summary and retrieved transcript. Do not hallucinate.
       Return ONLY a valid JSON object. Use the EXACT question text as the JSON key.
       Never alter, remove, or replace any placeholder in the returned values.
"""


def _build_group_prompt(group: Dict, context: str, summary: str) -> str:
    questions_with_ids = ""
    for q in group["questions"]:
        questions_with_ids += f"{q['id']}) {q['text']}\n"
        if q.get("options"):
            questions_with_ids += "Options:\n" + "".join(f"  {opt}\n" for opt in q["options"])
            if q.get("allow_other", False):
                questions_with_ids += (
                    '\nNOTE:\n- If none of the listed options apply, DO NOT choose '
                    '"If something else type" or "If other, then type".\n'
                    "- Instead, extract a short custom answer from the transcript.\n"
                )
            else:
                questions_with_ids += (
                    "\nNOTE:\n- The answer MUST be one of the listed options.\n"
                    '- Otherwise return:\n  "Not mentioned in transcript."\n'
                )
        questions_with_ids += "\n"

    combined_context = f"Summary of the conversation:\n{summary}\n\nRelevant transcript excerpts:\n{context}\n"

    return f"""
      You are an expert conversation analyst extracting structured information from a PRIVACY-PRESERVING (ANONYMIZED) customer-advisor conversation.

      IMPORTANT:
      - The conversation has been intentionally anonymized before being provided to you.
      - Personal information has been replaced with placeholders enclosed in angle brackets.
      - These placeholders represent the ORIGINAL values and MUST be treated as factual information.

      Examples of placeholders include (but are not limited to):
{PLACEHOLDER_NOTE}
      Rules:
      1. Treat placeholders exactly as if they were the original values.
      2. NEVER replace placeholders with "Unknown"/"Anonymous"/"Redacted"/"Not mentioned"/invented values.
      3. If a placeholder answers the question, return the placeholder exactly as it appears.
      4. Use ONLY the information provided in the conversation. Do not infer, guess, or invent.
      5. If the transcript truly does not contain enough information, return exactly
         "Not mentioned in transcript." (or "Not determined" if specified by the instructions).
      6. Do NOT output reasoning or <think> tags. Return ONLY the final JSON.

      --------------------------------------------------------
      Conversation Context
      --------------------------------------------------------
      {combined_context}

      --------------------------------------------------------
      Questions
      --------------------------------------------------------
      {questions_with_ids}

      --------------------------------------------------------
      Instructions
      --------------------------------------------------------
      {INSTRUCTION}

      Return ONLY a valid JSON object. The JSON keys MUST exactly match the question texts.
      Do not include markdown, explanations, or any additional text.
      """


def _clean_group_result(result: Dict) -> Dict:
    cleaned = {}
    for key, value in result.items():
        clean_key = re.sub(r"^Ques\.\d+\)\s*", "", key).strip()
        if isinstance(value, str):
            clean_value = re.sub(r"^[a-z]{1,2}\)\s*", "", value.strip(), flags=re.IGNORECASE)
        else:
            clean_value = value
        cleaned[clean_key] = clean_value
    return cleaned


def run_questionnaire(tokenizer, model, retriever: Retriever, summary: str) -> Dict:
    all_results: Dict = {}

    for group in QUESTION_GROUPS:
        group_id = group["id"]
        print(f"\n--- Processing {group_id} ---")

        query_text = "\n".join(
            q["text"] + ("\nOptions: " + ", ".join(q["options"]) if q.get("options") else "")
            for q in group["questions"]
        )
        context = retriever.get_context(query_text, top_k=TOP_K)
        prompt = _build_group_prompt(group, context, summary)
        # Reserve most of the context window for the prompt and retrieved text.
        answer = ask_question(tokenizer, model, prompt, max_new_tokens=256)

        try:
            result = _clean_group_result(extract_json(answer))
        except Exception as e:
            print(f"Failed to parse JSON for {group_id}: {e}\nRaw model output:\n{answer}")
            result = {q["text"]: "Not determined" for q in group["questions"]}

        for key, value in result.items():
            if key in all_results:
                print(f"WARNING: Duplicate key detected: {key}")
            all_results[key] = value

        print(f"Finished {group_id}")

    return all_results


def run(private_transcript_path: str, output_path: str) -> Dict:
    with open(private_transcript_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    full_text = segments_to_text(segments)

    tokenizer, model = load_llm(QA_MODEL_NAME, HF_TOKEN)
    retriever = Retriever(EMBED_MODEL_NAME, full_text, MAX_CHARS_FOR_FULL_CONTEXT, CHUNK_SIZE, OVERLAP)

    try:
        print("Generating conversation summary...")
        summary = generate_summary(tokenizer, model, full_text)

        all_results = run_questionnaire(tokenizer, model, retriever, summary)

        print("Generating additional information...")
        additional_context = retriever.get_context(
            "additional information context special circumstances follow up plans constraints", top_k=8)
        all_results["Any Additional Information"] = generate_additional_information(
            tokenizer, model, additional_context, all_results)

        print("Generating feedback...")
        feedback_context = retriever.get_context(
            "advisor feedback recommendation improvement follow up comments observations", top_k=8)
        all_results["Any other Feedback"] = generate_feedback(
            tokenizer, model, feedback_context, all_results)


        private_output = {"summary": summary, "questionnaire": all_results}
    finally:
        retriever.close()
        unload_llm(QA_MODEL_NAME, HF_TOKEN)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(private_output, f, indent=2, ensure_ascii=False)
    print(f"\nPrivate (placeholder) Q&A JSON -> {output_path}")
    return private_output


def cleanup():
    unload_llm(QA_MODEL_NAME, HF_TOKEN)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 4: private transcript -> private Q&A JSON")
    parser.add_argument("private_transcript_path")
    parser.add_argument("output_path")
    args = parser.parse_args()
    run(args.private_transcript_path, args.output_path)
