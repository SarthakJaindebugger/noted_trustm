import json
import pandas as pd
from pathlib import Path


# =========================
# CONFIGURATION
# =========================
INPUT_JSON = "/Users/sarthakjain/Desktop/ML Projects/noted-main/noted_s2t_pipeline/outputs/new_outputs_summarization/visit_log_dia03sce2SA.json"

# Change this to your desired output folder
OUTPUT_DIR = r"/Users/sarthakjain/Desktop/ML Projects/noted-main/noted_s2t_pipeline/outputs/new_outputs_summarization"


def json_to_qa_table(json_file, output_dir):
    """
    Convert transcript JSON into a 2-column Question/Answer table.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    metadata = data.get("metadata", {})
    extraction = data.get("extraction", {})

    def get_value(key, default="Not specified"):
        value = extraction.get(key, default)

        if value is None:
            return default

        if isinstance(value, str) and value.strip().lower() in {
            "",
            "not mentioned",
            "not specified",
        }:
            return default

        return value

    qa = [
        ("Control Location", "Not specified"),
        ("Contact Method", "Guidance/advice visit"),
        ("Number of Customers", "1"),
        ("Date & Time", metadata.get("date_time", "Not specified")),
        ("Gender", get_value("Gender")),
        ("Age Group", get_value("Age_Group")),
        ("Reason for Immigration", get_value("Reason_for_Immigration")),
        ("Labor Market Position", get_value("Labor_Market_Position")),
        ("Customer's Domicile", get_value("Customers_Domicile")),
        (
            "Duration of Residence in Finland",
            get_value("Duration_of_Residence_in_Finland"),
        ),
        ("Topics", get_value("Topics_Discussed")),
        ("Country of Birth", get_value("Country_of_Birth")),
        ("Mother Tongue", get_value("Mother_Tongue")),
        ("Education Level", get_value("Education_Level")),
        (
            "Additional Notes",
            (
                f"Services sought: {get_value('Services_Sought')}. "
                f"Guidance provided: {get_value('Guidance_Provided')}. "
                f"Referrals made: {get_value('Referrals_Made')}."
            ),
        ),
    ]

    df = pd.DataFrame(qa, columns=["Question", "Answer"])

    stem = Path(json_file).stem

    csv_path = output_dir / f"{stem}_qa.csv"
    #excel_path = output_dir / f"{stem}_qa.xlsx"

    df.to_csv(csv_path, index=False)
    #df.to_excel(excel_path, index=False)

    print(f"CSV saved to: {csv_path}")
    #print(f"Excel saved to: {excel_path}")

    return df


if __name__ == "__main__":
    json_to_qa_table(
        json_file=INPUT_JSON,
        output_dir=OUTPUT_DIR
    )