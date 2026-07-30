# -*- coding: utf-8 -*-
"""
Stage 6 · Mapped JSON -> CRM form parsed JSON
========================================================================
Prepares the final speech-analysis output for the interactive CRM form by
copying the stage-5 mapped results into a CRM-ready JSON file in the
same run folder.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def split_list(value: Optional[str]) -> List[str]:
    if not value or value == "Not mentioned in transcript.":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def map_answer(value: Optional[str]) -> Optional[str]:
    if not value or value == "Not mentioned in transcript.":
        return None
    return value


def parse_other_list(value: Optional[str]) -> Tuple[List[str], str]:
    if not value or value == "Not mentioned in transcript.":
        return [], ""
    if isinstance(value, str) and value.startswith("Other:"):
        text = value.replace("Other:", "", 1).strip()
        return ["__other__"], text
    return split_list(value), ""


def guess_customer_count_from_metadata(metadata: dict) -> Optional[int]:
    if not metadata:
        return None
    speaker_roles = metadata.get("speaker_roles") or {}
    customers = [role for speaker, role in speaker_roles.items() if speaker != "UNKNOWN" and role == "customer"]
    return len(customers) if customers else None


def build_crm_form_payload(questionnaire: dict, metadata: dict) -> dict:
    additional_info, additional_info_other = parse_other_list(
        questionnaire.get("Additional Information about the customers")
    )
    contents, contents_other = parse_other_list(
        questionnaire.get("Contents of the customer visit")
    )

    return {
        "controlLocation": "",
        "date": "",
        "time": "",
        "visitDuration": metadata.get("visit_duration", ""),
        "contactMethod": split_list(questionnaire.get("What is the contact method used by Advisee(s)?")),
        "fieldWorkWhere": "",
        "heardFrom": map_answer(questionnaire.get("Heard from the guidance/advice position (if other where?)")) or "",
        "customerCount": guess_customer_count_from_metadata(metadata),
        "gender": "",
        "age": None,
        "immigrationReason": map_answer(questionnaire.get("Reason for Immigration")) or "",
        "additionalInfo": additional_info,
        "additionalInfoOther": additional_info_other,
        "birthCountry": map_answer(questionnaire.get("Customer birth country")) or "",
        "motherTongue": map_answer(questionnaire.get("Mother Tongue/Language")) or "",
        "educationLevel": map_answer(questionnaire.get("Education Level")) or "",
        "labourPosition": split_list(questionnaire.get("Position in labour market")),
        "domicile": map_answer(questionnaire.get("Customer Domicile")) or "",
        "residenceDuration": split_list(questionnaire.get("Duration of residence in Finland")),
        "contents": contents,
        "contentsOther": contents_other,
        "purpose": split_list(questionnaire.get("Purpose of visit")),
        "additionalInfoText": map_answer(questionnaire.get("Any Additional Information")) or "",
        "directedTo": map_answer(questionnaire.get("Where the customer is directed")) or "",
        "otherFeedback": map_answer(questionnaire.get("Any other Feedback")) or "",
    }


def render_html_template(form_payload: dict, questionnaire: dict, template_path: Path) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    initial_data = {
        "form": form_payload,
        "questionnaire": questionnaire,
    }
    json_text = json.dumps(initial_data, ensure_ascii=False).replace("</", "<\\/")
    injection = f"<script>window.initialData = {json_text};</script>"

    if "<!-- INITIAL_FORM_DATA_PLACEHOLDER -->" not in html:
        raise ValueError("CRM form template is missing INITIAL_FORM_DATA_PLACEHOLDER")

    return html.replace("<!-- INITIAL_FORM_DATA_PLACEHOLDER -->", injection)


def run(mapped_results_path: str, metadata_path: str, output_path: str, html_output_path: str) -> dict:
    with open(mapped_results_path, "r", encoding="utf-8") as f:
        mapped = json.load(f)

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    questionnaire = mapped.get("questionnaire", mapped)
    form_payload = build_crm_form_payload(questionnaire, metadata)
    output = {
        "questionnaire": questionnaire,
        "metadata": metadata,
        "form": form_payload,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    template_path = REPO_ROOT / "crm_forms" / "crm_form_template.html"
    html = render_html_template(form_payload, questionnaire, template_path)
    with open(html_output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"CRM form parsed JSON -> {output_path}")
    print(f"CRM form HTML -> {html_output_path}")
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 6: mapped JSON -> crm form parsed JSON")
    parser.add_argument("mapped_results_path")
    parser.add_argument("metadata_path")
    parser.add_argument("output_path")
    parser.add_argument("html_output_path")
    args = parser.parse_args()
    run(
        args.mapped_results_path,
        args.metadata_path,
        args.output_path,
        args.html_output_path,
    )
