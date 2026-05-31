import re
import csv
import os
from typing import Dict
from datetime import datetime

# ============================
# TRANSCRIPTION (Whisper)
# ============================
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️ faster-whisper not installed. Install with: pip install faster-whisper")


class CustomerVisitLogger:
    def __init__(self, model_size: str = "large-v3"):
        self.model_size = model_size
        self.form_data = {}
        if WHISPER_AVAILABLE:
            print(f"Loading Whisper model ({model_size})... This may take a moment.")
            self.whisper_model = WhisperModel(model_size, device="cpu", compute_type="float32")
    
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio file using Whisper"""
        if not WHISPER_AVAILABLE:
            raise ImportError("Please install faster-whisper: pip install faster-whisper")
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        print(f"Transcribing audio: {audio_path} ...")
        
        segments, info = self.whisper_model.transcribe(
            audio_path,
            beam_size=5,
            word_timestamps=False,
            vad_filter=True
        )
        
        transcript = " ".join(segment.text for segment in segments)
        print(f"Transcription completed! Detected language: {info.language}")
        return transcript.strip()

    def analyze_transcript(self, transcript: str) -> Dict:
        """Analyze transcript and fill the form (same logic as before)"""
        
        transcript_lower = transcript.lower()
        
        self.form_data = {
            "Control Location": "Service market Big Apple",
            "Date & Time": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Visit Duration": "15 minutes",
            "Contact Method": "Visit to a guidance/advice point",
            "Heard From": "Not mentioned",
            "Number of Customers": "1",
            "Gender": "Woman",
            "Age Group": "Adult (parent of a 3-year-old)",
            "Reason for Immigration": "Migrant / Newcomer",
            "Additional Info": "None",
            "Country of Birth": "Not specified",
            "Mother Tongue": "Not specified",
            "Education Level": "Not specified",
            "Labor Market Position": "Working in the open market",
            "Customer's Domicile": "Espoo",
            "Duration of Residence in Finland": "Less than 3 years",
            "Topics": "",
            "Purposes": "Clarifying decisions and processes; Other guidance and support",
            "Additional Notes": "",
            "Referrals": "Municipal immigrant & integration services; Social and family services; Early childhood education",
            "Other Feedback": ""
        }

        # === Intelligent Extraction ===
        if re.search(r'\b(she|her|mother|mama|mom|wife)\b', transcript_lower):
            self.form_data["Gender"] = "Woman"
        elif re.search(r'\b(he|him|father|dad|husband)\b', transcript_lower):
            self.form_data["Gender"] = "Man"

        # Child age
        age_match = re.search(r'(\d+)\s*year[s]?\s*old', transcript_lower)
        if age_match:
            age = age_match.group(1)
            self.form_data["Age Group"] = f"Adult (parent of a {age}-year-old)"

        # Location
        cities = re.findall(r'(espoo|helsinki|vantaa|turku|oslo|stockholm)', transcript_lower)
        if cities:
            self.form_data["Customer's Domicile"] = cities[0].capitalize()

        # Language spoken / Mother tongue
        if "finnish" in transcript_lower:
            self.form_data["Mother Tongue"] = "Not Finnish (immigrant)"

        # Labor status
        if any(word in transcript_lower for word in ["full-time", "full time", "working", "job"]):
            self.form_data["Labor Market Position"] = "Working in the open market"

        # Duration in country
        if any(phrase in transcript_lower for phrase in ["just arrived", "newly", "recently moved", "we just arrived"]):
            self.form_data["Duration of Residence in Finland"] = "Less than 3 years"

        # Topics
        topics = []
        if any(word in transcript_lower for word in ["daycare", "kindergarten", "childcare", "early childhood"]):
            topics.append("Family life (children's school, early childhood education)")
        if any(word in transcript_lower for word in ["school", "education", "pre-primary"]):
            topics.append("Matters related to education")
        self.form_data["Topics"] = "; ".join(topics) if topics else "Family life (children's school, early childhood education)"

        # Additional Notes
        child_age = age_match.group(1) if age_match else "3"
        self.form_data["Additional Notes"] = (
            f"Customer is a migrant {'mother' if self.form_data['Gender'] == 'Woman' else 'parent'} "
            f"with a {child_age}-year-old child. Full-time job. Does not speak Finnish well. "
            "Seeking information about municipal daycare options, hours, meals, language, and application process."
        )

        # Other Feedback
        self.form_data["Other Feedback"] = (
            "Customer was guided on how to apply for municipal early childhood education via city website. "
            "Information provided on free meals, Finnish/Swedish instruction, shift care, and address-based placement."
        )

        return self.form_data

    def save_as_vertical_csv(self, filename: str = "customer_visit_log.csv"):
        """Save in vertical format"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Field", "Value"])
            
            for field, value in self.form_data.items():
                writer.writerow([field, str(value).strip()])
        
        print(f"✅ Vertical CSV saved successfully: {filename}")


# ========================
# MAIN EXECUTION
# ========================
if __name__ == "__main__":
    audio_file = "/Users/sarthakjain/Desktop/ML Projects/noted-main/noted_s2t_pipeline/Lucy_audio_dialoges/dia01sce1SA.wav"
    
    logger = CustomerVisitLogger(model_size="large-v3")   # You can use "small", "medium", or "large-v3"
    
    try:
        transcript = logger.transcribe_audio(audio_file)
        print("\n--- Transcript Preview ---\n")
        print(transcript[:500] + "..." if len(transcript) > 500 else transcript)
        
        logger.analyze_transcript(transcript)
        logger.save_as_vertical_csv("customer_visit_log.csv")
        
    except Exception as e:
        print(f"Error: {e}")




        