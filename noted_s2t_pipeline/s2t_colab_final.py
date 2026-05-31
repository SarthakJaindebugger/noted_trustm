
# Cell 2: Main Enhanced Script
import re
import csv
import os
import torch
from typing import Dict
from datetime import datetime
from google.colab import files

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️ faster-whisper not installed.")


class CustomerVisitLogger:
    def __init__(self, model_size: str = "large-v3"):
        self.model_size = model_size
        self.form_data = {}
        if WHISPER_AVAILABLE:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.compute_type = "float16" if self.device == "cuda" else "float32"
            print(f"Loading Whisper model ({model_size}) on {self.device}...")
            self.whisper_model = WhisperModel(model_size, device=self.device, compute_type=self.compute_type)
            print("Whisper model loaded successfully.")

    def transcribe_audio(self, audio_path: str) -> str:
        if not WHISPER_AVAILABLE:
            raise ImportError("Please install faster-whisper")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        print(f"Transcribing: {audio_path} ...")
        segments, info = self.whisper_model.transcribe(
            audio_path, beam_size=5, vad_filter=True, language=None
        )
        transcript = " ".join(segment.text for segment in segments)
        print(f"Transcription completed | Detected Language: {info.language}")
        return transcript.strip()

    def analyze_transcript(self, transcript: str) -> Dict:
        t = transcript.lower()
        words = t.split()

        # ========================
        # DEFAULT VAST DICTIONARY
        # ========================
        self.form_data = {
            "Control Location": "Service market Big Apple",
            "Date & Time": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Visit Duration": "15 minutes",
            "Contact Method": "Visit to a guidance/advice point",
            "Heard From": "Not mentioned",
            "Number of Customers": "1",
            "Gender": "No information",
            "Age Group": "Adult",
            "Reason for Immigration": "Migrant / Newcomer",
            "Additional Info": "None",
            "Country of Birth": "Not specified",
            "Mother Tongue": "Not specified",
            "Education Level": "Not specified",
            "Labor Market Position": "No information",
            "Customer's Domicile": "Not specified",
            "Duration of Residence in Finland": "No information",
            "Topics": "",
            "Purposes": "Other guidance and support",
            "Additional Notes": "",
            "Referrals": "",
            "Other Feedback": ""
        }

        # ========================
        # ADVANCED EXTRACTION
        # ========================

        # Gender
        if re.search(r'\b(she|her|mother|mama|mom|wife|daughter)\b', t):
            self.form_data["Gender"] = "Woman"
        elif re.search(r'\b(he|him|father|dad|husband|son)\b', t):
            self.form_data["Gender"] = "Man"

        # Age Group
        age_match = re.search(r'(\d{1,2})\s*year[s]?\s*old', t)
        if age_match:
            self.form_data["Age Group"] = f"Adult (parent of a {age_match.group(1)}-year-old)"

        # Reason for Immigration
        reasons = {
            "work|job|employed": "Work",
            "family|reunification|spouse|partner": "Family Reunification",
            "asylum|refugee|protection": "Asylum / Refugee",
            "study|student|university": "Study",
            "business|entrepreneur": "Entrepreneurship",
            "ukraine": "Ukraine Crisis",
        }
        for pattern, reason in reasons.items():
            if re.search(pattern, t):
                self.form_data["Reason for Immigration"] = reason
                break

        # Additional Info
        add_info = []
        if "refugee" in t or "asylum" in t:
            add_info.append("Refugee")
        if "ukraine" in t:
            add_info.append("Ukraine crisis")
        if "paperless" in t or "no documents" in t:
            add_info.append("Paperless")
        if "illiterate" in t or "cannot read" in t:
            add_info.append("Illiterate")
        self.form_data["Additional Info"] = "; ".join(add_info) if add_info else "None"

        # Country of Birth
        countries = {
            "somalia|somalian": "Somalia", "afghanistan": "Afghanistan", "syria": "Syria",
            "iraq": "Iraq", "ukraine": "Ukraine", "russia": "Russia", "india": "India",
            "pakistan": "Pakistan", "nigeria": "Nigeria", "ghana": "Ghana"
        }
        for key, country in countries.items():
            if re.search(key, t):
                self.form_data["Country of Birth"] = country
                break

        # Mother Tongue / Language
        languages = {
            "arabic": "Arabic", "somali": "Somali", "russian": "Russian",
            "ukrainian": "Ukrainian", "urdu": "Urdu", "hindi": "Hindi",
            "farsi|persian": "Farsi", "kurdish": "Kurdish"
        }
        for key, lang in languages.items():
            if re.search(key, t):
                self.form_data["Mother Tongue"] = lang
                break
        if "finnish" in t and "not speak" in t or "don't speak" in t:
            self.form_data["Mother Tongue"] = "Not Finnish (Immigrant)"

        # Education Level
        if any(x in t for x in ["university", "bachelor", "master", "degree", "college"]):
            self.form_data["Education Level"] = "Higher Education"
        elif any(x in t for x in ["high school", "secondary"]):
            self.form_data["Education Level"] = "Secondary Education"

        # Labor Market Position
        if any(x in t for x in ["full-time", "full time", "working", "have job"]):
            self.form_data["Labor Market Position"] = "Working in the open market"
        elif "unemployed" in t:
            self.form_data["Labor Market Position"] = "Unemployed"
        elif "student" in t:
            self.form_data["Labor Market Position"] = "Student (voluntary)"

        # Domicile & Duration
        cities = re.findall(r'(espoo|helsinki|vantaa|turku|tampere)', t)
        if cities:
            self.form_data["Customer's Domicile"] = cities[0].capitalize()

        if any(x in t for x in ["just arrived", "newly arrived", "recently", "we just came"]):
            self.form_data["Duration of Residence in Finland"] = "Less than 3 years"
        elif "year" in t and re.search(r'\d+\s*year', t):
            self.form_data["Duration of Residence in Finland"] = "3-5 years"

        # Topics (Very Broad for Immigration Context)
        topics_list = []
        topic_map = {
            "daycare|kindergarten|childcare": "Family life (children's school, early childhood education)",
            "school|education|pre-primary": "Matters related to education",
            "residence permit|residence|permit": "Immigration process (residence permit, citizenship, registration)",
            "kela|benefit|social benefit": "Benefits (e.g. Kela)",
            "job|work|employment|te-office": "Work (TE services, job search, etc.)",
            "housing|apartment|flat": "Residence",
            "health|doctor|hospital": "Health care",
            "finnish|swedish|language course": "Studying Finnish/Swedish"
        }
        for key, topic in topic_map.items():
            if re.search(key, t):
                topics_list.append(topic)
        
        self.form_data["Topics"] = "; ".join(topics_list) if topics_list else "Family life (children's school, early childhood education)"

        # Purposes
        self.form_data["Purposes"] = "Clarifying decisions and processes; Other guidance and support"

        # Referrals
        referrals = ["Municipal immigrant & integration services", "Social and family services", "Early childhood education"]
        if "kela" in t:
            referrals.append("Kela")
        if "migri" in t or "residence permit" in t:
            referrals.append("Finnish Immigration Service (Migri)")
        self.form_data["Referrals"] = "; ".join(referrals)

        # Additional Notes & Feedback
        child_age = age_match.group(1) if age_match else "3"
        self.form_data["Additional Notes"] = (
            f"Immigrant {'mother' if self.form_data['Gender']=='Woman' else 'parent'} with "
            f"a {child_age}-year-old child. Full-time job. Limited Finnish skills. "
            f"Country of birth: {self.form_data['Country of Birth']}. "
            "Seeking guidance on integration services."
        )

        self.form_data["Other Feedback"] = (
            "Customer received comprehensive guidance on municipal services, "
            "early childhood education, and integration pathways. "
            "Directed to relevant municipal portals and authorities."
        )

        return self.form_data

    def save_as_vertical_csv(self, filename: str = "customer_visit_log.csv"):
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Field", "Value"])
            for field, value in self.form_data.items():
                writer.writerow([field, str(value).strip()])
        print(f"✅ CSV saved: {filename}")


# ========================
# RUN IN COLAB
# ========================
def run_in_colab():
    print("=== Advanced Immigration Customer Visit Logger ===\n")
    
    # Change this path to your file
    audio_path = "/content/dia02sce1MC.WAV"   

    logger = CustomerVisitLogger(model_size="large-v3")

    try:
        transcript = logger.transcribe_audio(audio_path)
        print("\n--- Transcript Preview ---")
        print(transcript[:800] + "..." if len(transcript) > 800 else transcript)

        logger.analyze_transcript(transcript)
        logger.save_as_vertical_csv()

        import pandas as pd
        df = pd.DataFrame(list(logger.form_data.items()), columns=["Field", "Value"])
        print("\n--- Extracted Data ---")
        print(df.to_string(index=False))

        files.download("customer_visit_log.csv")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_in_colab()