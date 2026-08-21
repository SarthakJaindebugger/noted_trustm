#!/usr/bin/env python3
"""
Mozilla Common Voice Dataset Downloader from Kaggle
Downloads exactly 1000 utterances with gender and age labels
"""

import os
import csv
import json
import requests
import random
import time
import shutil
import glob
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set
import pandas as pd
from tqdm import tqdm
import subprocess

# ============================================================================
# HARD-CODED CONFIGURATION - CHANGE THESE PATHS
# ============================================================================

# Main directory where everything will be stored
BASE_DIR = Path("/scratch/work/jains6/noted/noted-main/age_gender_prediction/dataset")

# Number of utterances to download
NUM_UTTERANCES = 1000

# Kaggle dataset path
KAGGLE_DATASET = "mozillaorg/common-voice"

# ============================================================================
# KAGGLE API SETUP
# ============================================================================

def check_kaggle_installed():
    """Check if Kaggle CLI is installed"""
    try:
        subprocess.run(["kaggle", "--version"], capture_output=True, check=True)
        return True
    except:
        return False

def check_kaggle_credentials():
    """Check if Kaggle credentials are set up"""
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_json = kaggle_dir / "kaggle.json"
    return kaggle_json.exists()

def setup_kaggle_instructions():
    """Print instructions for setting up Kaggle"""
    print("\n" + "="*60)
    print("KAGGLE API SETUP REQUIRED")
    print("="*60)
    print("\nTo download from Kaggle, you need to:")
    print("\n1. Go to https://www.kaggle.com/")
    print("2. Click on your profile picture → Account")
    print("3. Scroll to 'API' section")
    print("4. Click 'Create New API Token'")
    print("5. This downloads a 'kaggle.json' file")
    print("\n6. Place the file in ~/.kaggle/kaggle.json")
    print("   (On Windows: %USERPROFILE%\.kaggle\kaggle.json)")
    print("\n7. Set permissions (Linux/Mac):")
    print("   chmod 600 ~/.kaggle/kaggle.json")
    print("\nOr use environment variables:")
    print("   export KAGGLE_USERNAME=your-username")
    print("   export KAGGLE_KEY=your-api-key")
    print("="*60)

class CommonVoiceKaggleDownloader:
    """Download Common Voice dataset from Kaggle with age and gender labels"""
    
    def __init__(self, base_dir: Path, num_utterances: int = 1000):
        self.base_dir = Path(base_dir)
        self.num_utterances = num_utterances
        
        # Create directory structure
        self.audio_dir = self.base_dir / "audio" / "common_voice"
        self.metadata_dir = self.base_dir / "metadata"
        self.output_dir = self.base_dir / "output"
        self.kaggle_dir = self.base_dir / "kaggle_download"
        
        # Create all directories
        for d in [self.audio_dir, self.metadata_dir, self.output_dir, self.kaggle_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # Store metadata
        self.speaker_metadata: Dict[str, Dict] = {}
        self.audio_files: List[Path] = []
        
        # Age group mapping
        self.age_group_map = {
            'teens': '0-19',
            'twenties': '20-29',
            'thirties': '30-39',
            'fourties': '40-49',
            'fifties': '50-59',
            'sixties': '60-69',
            'seventies': '70-79',
            'eighties': '80-89',
            'nineties': '90+'
        }
    
    def download_from_kaggle(self) -> bool:
        """Download the dataset using Kaggle CLI"""
        print(f"\n{'='*60}")
        print("Downloading Common Voice from Kaggle...")
        print(f"  Dataset: {KAGGLE_DATASET}")
        print(f"{'='*60}")
        
        # Check if already downloaded
        zip_files = list(self.kaggle_dir.glob("*.zip"))
        if zip_files:
            print(f"  Found existing zip file: {zip_files[0].name}")
            return True
        
        # Check Kaggle CLI
        if not check_kaggle_installed():
            print("\n❌ Kaggle CLI not installed!")
            print("Install with: pip install kaggle")
            return False
        
        # Check credentials
        if not check_kaggle_credentials():
            setup_kaggle_instructions()
            return False
        
        # Download the dataset
        print(f"\n  Downloading from Kaggle...")
        print(f"  This may take a while (13.5 GB)...")
        
        try:
            # Download using Kaggle CLI
            cmd = [
                "kaggle", "datasets", "download",
                "-d", KAGGLE_DATASET,
                "-p", str(self.kaggle_dir)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"  ✗ Download failed: {result.stderr}")
                return False
            
            print(f"  ✓ Download completed!")
            
            # Unzip the dataset
            zip_files = list(self.kaggle_dir.glob("*.zip"))
            if not zip_files:
                print("  ✗ No zip file found after download")
                return False
            
            zip_path = zip_files[0]
            print(f"\n  Extracting {zip_path.name}...")
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get total files for progress bar
                total_files = len(zip_ref.namelist())
                with tqdm(total=total_files, desc="Extracting") as pbar:
                    for file in zip_ref.namelist():
                        zip_ref.extract(file, self.kaggle_dir)
                        pbar.update(1)
            
            print(f"  ✓ Extracted to {self.kaggle_dir}")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Kaggle command failed: {e}")
            return False
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False
    
    def find_metadata_files(self) -> List[Path]:
        """Find all CSV metadata files in the extracted dataset"""
        csv_files = []
        
        # Look for CSV files in the kaggle directory
        for csv_path in self.kaggle_dir.rglob("*.csv"):
            # Skip the cv-invalid.csv if present
            if 'invalid' not in csv_path.name:
                csv_files.append(csv_path)
        
        print(f"\n  Found {len(csv_files)} metadata CSV files:")
        for csv_file in csv_files:
            print(f"    - {csv_file.name}")
        
        return csv_files
    
    def parse_metadata(self) -> bool:
        """Parse all CSV metadata files"""
        print(f"\n{'='*60}")
        print("Parsing metadata for gender and age labels...")
        print(f"{'='*60}")
        
        csv_files = self.find_metadata_files()
        
        if not csv_files:
            print("  ✗ No metadata CSV files found")
            return False
        
        # Combine all metadata
        all_data = []
        total_audio_files = 0
        
        for csv_path in csv_files:
            try:
                df = pd.read_csv(csv_path)
                print(f"\n  Processing {csv_path.name}:")
                print(f"    - {len(df)} entries")
                print(f"    - Columns: {df.columns.tolist()}")
                
                # Filter for rows with age and gender
                if 'gender' in df.columns and 'age' in df.columns:
                    # Keep only rows with valid gender and age
                    filtered_df = df[df['gender'].notna() & df['age'].notna()]
                    print(f"    - {len(filtered_df)} entries with gender and age")
                    all_data.append(filtered_df)
                    total_audio_files += len(filtered_df)
                else:
                    print(f"    - Skipping: no gender/age columns")
                    
            except Exception as e:
                print(f"  ✗ Error reading {csv_path.name}: {e}")
        
        if not all_data:
            print("\n  ✗ No data with gender and age labels found")
            return False
        
        # Combine all data
        combined_df = pd.concat(all_data, ignore_index=True)
        print(f"\n  Total entries with gender and age: {len(combined_df)}")
        
        # Build speaker metadata from combined data
        speaker_info = {}
        
        for _, row in combined_df.iterrows():
            # Extract speaker ID from filename
            filename = row['filename']
            # Common Voice format: speaker_id/audio_id.mp3
            speaker_id = filename.split('/')[0] if '/' in filename else filename.split('_')[0]
            
            if speaker_id not in speaker_info:
                speaker_info[speaker_id] = {
                    'gender': row['gender'],
                    'age': row['age'],
                    'accent': row.get('accent', 'unknown'),
                    'samples': []
                }
            speaker_info[speaker_id]['samples'].append(filename)
        
        print(f"\n  Found {len(speaker_info)} unique speakers")
        
        # Store metadata
        for speaker_id, info in speaker_info.items():
            gender = info['gender']
            age = info['age']
            
            # Normalize gender
            if isinstance(gender, str):
                gender = gender.lower()
                if gender in ['male', 'm']:
                    gender = 'M'
                elif gender in ['female', 'f']:
                    gender = 'F'
                else:
                    gender = 'other'
            
            # Normalize age group
            if isinstance(age, str):
                age = age.lower()
                # Convert age group to standard format
                age_group = age
                for key, value in self.age_group_map.items():
                    if key in age:
                        age_group = value
                        break
            else:
                age_group = 'unknown'
            
            self.speaker_metadata[speaker_id] = {
                'gender': gender,
                'age': age_group,
                'accent': info['accent'],
                'num_samples': len(info['samples'])
            }
        
        # Print statistics
        print(f"\n  Metadata Statistics:")
        print(f"    - Total speakers: {len(self.speaker_metadata)}")
        
        # Gender distribution
        gender_count = sum(1 for s in self.speaker_metadata.values() if s['gender'] != 'unknown')
        print(f"    - With gender labels: {gender_count} ({gender_count/len(self.speaker_metadata)*100:.1f}%)")
        
        if gender_count > 0:
            gender_dist = {}
            for s in self.speaker_metadata.values():
                if s['gender'] != 'unknown':
                    gender_dist[s['gender']] = gender_dist.get(s['gender'], 0) + 1
            print(f"    - Gender distribution: {gender_dist}")
        
        # Age distribution
        age_count = sum(1 for s in self.speaker_metadata.values() if s['age'] != 'unknown')
        print(f"    - With age labels: {age_count} ({age_count/len(self.speaker_metadata)*100:.1f}%)")
        
        if age_count > 0:
            age_dist = {}
            for s in self.speaker_metadata.values():
                if s['age'] != 'unknown':
                    age_dist[s['age']] = age_dist.get(s['age'], 0) + 1
            print(f"    - Age distribution: {age_dist}")
        
        return True
    
    def find_audio_files(self) -> List[Path]:
        """Find all MP3 files in the extracted dataset"""
        mp3_files = list(self.kaggle_dir.rglob("*.mp3"))
        print(f"\n  Found {len(mp3_files)} MP3 files")
        return mp3_files
    
    def select_and_copy_audio_files(self) -> List[Path]:
        """Select exactly 1000 utterances and copy them to the audio directory"""
        print(f"\n{'='*60}")
        print(f"Selecting {self.num_utterances} utterances with age and gender labels...")
        print(f"{'='*60}")
        
        # Find all MP3 files
        all_mp3_files = self.find_audio_files()
        
        if not all_mp3_files:
            print("  ✗ No MP3 files found")
            return []
        
        # Filter speakers with both age and gender
        speakers_with_both = []
        for speaker_id, meta in self.speaker_metadata.items():
            if meta['gender'] != 'unknown' and meta['age'] != 'unknown':
                speakers_with_both.append(speaker_id)
        
        print(f"  Found {len(speakers_with_both)} speakers with both age and gender labels")
        
        if not speakers_with_both:
            print("  ⚠️  No speakers with both labels. Using speakers with gender only.")
            speakers_with_both = [s for s, meta in self.speaker_metadata.items() if meta['gender'] != 'unknown']
        
        # Group MP3 files by speaker
        speaker_mp3_files = {}
        for mp3_path in all_mp3_files:
            # Extract speaker ID from path
            # Common Voice structure: speaker_id/audio_id.mp3
            parent_dir = mp3_path.parent.name
            if parent_dir in self.speaker_metadata:
                speaker_id = parent_dir
            else:
                # Try extracting from filename
                speaker_id = mp3_path.stem.split('_')[0] if '_' in mp3_path.stem else None
            
            if speaker_id and speaker_id in speakers_with_both:
                if speaker_id not in speaker_mp3_files:
                    speaker_mp3_files[speaker_id] = []
                speaker_mp3_files[speaker_id].append(mp3_path)
        
        print(f"  Found {sum(len(files) for files in speaker_mp3_files.values())} files from labeled speakers")
        print(f"  Across {len(speaker_mp3_files)} speakers")
        
        if not speaker_mp3_files:
            print("  ✗ No files from labeled speakers found")
            return []
        
        # Select files, distributing across speakers
        selected_files = []
        speakers_list = list(speaker_mp3_files.keys())
        random.shuffle(speakers_list)
        
        # For each speaker, take 1-3 files
        for speaker_id in speakers_list:
            if len(selected_files) >= self.num_utterances:
                break
            files = speaker_mp3_files[speaker_id]
            num_to_take = min(random.randint(1, 3), len(files), self.num_utterances - len(selected_files))
            selected_files.extend(files[:num_to_take])
        
        # If we still need more files, take from random speakers
        if len(selected_files) < self.num_utterances:
            remaining_needed = self.num_utterances - len(selected_files)
            all_remaining_files = []
            for speaker_id in speakers_list:
                remaining_files = [f for f in speaker_mp3_files[speaker_id] if f not in selected_files]
                all_remaining_files.extend(remaining_files)
            
            random.shuffle(all_remaining_files)
            selected_files.extend(all_remaining_files[:remaining_needed])
        
        # If we still don't have enough, take from any speaker
        if len(selected_files) < self.num_utterances:
            remaining_needed = self.num_utterances - len(selected_files)
            all_mp3_files = [f for f in all_mp3_files if f not in selected_files]
            random.shuffle(all_mp3_files)
            selected_files.extend(all_mp3_files[:remaining_needed])
        
        print(f"\n  Selected {len(selected_files)} utterances")
        
        # Copy selected files to audio directory
        print(f"\n  Copying files to {self.audio_dir}...")
        copied_paths = []
        
        with tqdm(total=len(selected_files), desc="Copying files") as pbar:
            for src_path in selected_files:
                # Preserve the original structure
                rel_path = src_path.relative_to(self.kaggle_dir)
                dest_path = self.audio_dir / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                shutil.copy2(src_path, dest_path)
                copied_paths.append(dest_path)
                pbar.update(1)
        
        print(f"  ✓ Copied {len(copied_paths)} files to {self.audio_dir}")
        return copied_paths
    
    def create_csv(self, audio_files: List[Path]) -> pd.DataFrame:
        """Create CSV with audio_path, gender, and age labels"""
        print(f"\n{'='*60}")
        print("Creating CSV with audio paths, gender, and age...")
        print(f"{'='*60}")
        
        data = []
        labeled_count = 0
        
        for audio_path in tqdm(audio_files, desc="Processing audio files"):
            # Extract speaker ID from path
            rel_path = audio_path.relative_to(self.audio_dir)
            speaker_id = str(rel_path).split('/')[0] if '/' in str(rel_path) else None
            
            if speaker_id is None or speaker_id not in self.speaker_metadata:
                continue
            
            metadata = self.speaker_metadata[speaker_id]
            gender = metadata['gender']
            age = metadata['age']
            
            if gender != 'unknown' and age != 'unknown':
                labeled_count += 1
            
            # Convert to relative path from base_dir
            try:
                rel_audio_path = audio_path.relative_to(self.base_dir)
            except ValueError:
                rel_audio_path = audio_path
            
            data.append({
                "audio_path": str(rel_audio_path),
                "speaker_id": speaker_id,
                "gender": gender,
                "age": age,
                "age_group": age
            })
        
        df = pd.DataFrame(data)
        
        # Save CSV
        csv_path = self.output_dir / f"common_voice_1000_utterances.csv"
        df.to_csv(csv_path, index=False)
        
        print(f"\n  ✓ CSV saved to: {csv_path}")
        print(f"\n  Statistics:")
        print(f"    - Total utterances: {len(df)}")
        print(f"    - With both age & gender: {labeled_count} ({labeled_count/len(df)*100:.1f}%)")
        print(f"    - With age: {len(df[df['age'] != 'unknown'])}")
        print(f"    - With gender: {len(df[df['gender'] != 'unknown'])}")
        
        if len(df[df['gender'] != 'unknown']) > 0:
            print(f"\n  Gender distribution:")
            gender_counts = df[df['gender'] != 'unknown']['gender'].value_counts()
            for gender, count in gender_counts.items():
                print(f"    - {gender}: {count} ({count/len(df)*100:.1f}%)")
        
        if len(df[df['age'] != 'unknown']) > 0:
            print(f"\n  Age group distribution:")
            age_counts = df[df['age'] != 'unknown']['age'].value_counts()
            for age_group, count in age_counts.items():
                print(f"    - {age_group}: {count} ({count/len(df)*100:.1f}%)")
        
        return df
    
    def run_full_pipeline(self):
        """Run the complete download and processing pipeline"""
        print(f"{'='*60}")
        print(f"COMMON VOICE FROM KAGGLE - {self.num_utterances} UTTERANCES")
        print(f"Dataset: {KAGGLE_DATASET}")
        print(f"Base directory: {self.base_dir}")
        print(f"{'='*60}")
        
        # Step 1: Download from Kaggle
        if not self.download_from_kaggle():
            print("\n  ✗ Failed to download from Kaggle. Exiting.")
            return
        
        # Step 2: Parse metadata
        if not self.parse_metadata():
            print("\n  ✗ Failed to parse metadata. Exiting.")
            return
        
        # Step 3: Select and copy 1000 utterances
        audio_files = self.select_and_copy_audio_files()
        
        if not audio_files:
            print("\n  ✗ No audio files were selected. Please check the dataset.")
            return
        
        print(f"\n  Successfully prepared {len(audio_files)} audio files")
        
        # Step 4: Create CSV
        df = self.create_csv(audio_files)
        
        # Step 5: Print summary
        print(f"\n{'='*60}")
        print("COMPLETED!")
        print(f"{'='*60}")
        print(f"\n✅ Prepared {len(audio_files)} utterances in: {self.audio_dir}")
        print(f"✅ CSV saved to: {self.output_dir / 'common_voice_1000_utterances.csv'}")
        
        print(f"\n{'='*60}")
        print("USAGE EXAMPLE:")
        print(f"{'='*60}")
        print("import pandas as pd")
        print(f"df = pd.read_csv('{self.output_dir / 'common_voice_1000_utterances.csv'}')")
        print("\n# Access audio files")
        print("audio_path = BASE_DIR / df.iloc[0]['audio_path']")
        print("\n# Filter by gender")
        print("male_df = df[df['gender'] == 'M']")
        print("\n# Filter by age group")
        print("age_30_49 = df[df['age'].isin(['30-39', '40-49'])]")


def main():
    """Main entry point"""
    
    print(f"\nUsing BASE_DIR: {BASE_DIR}")
    print(f"Target utterances: {NUM_UTTERANCES}")
    
    # Check for Kaggle setup
    print("\n" + "="*60)
    print("KAGGLE SETUP CHECK")
    print("="*60)
    
    if check_kaggle_installed():
        print("✅ Kaggle CLI is installed")
    else:
        print("❌ Kaggle CLI not found")
        print("Install with: pip install kaggle")
    
    if check_kaggle_credentials():
        print("✅ Kaggle credentials found")
    else:
        print("⚠️  Kaggle credentials not found")
        setup_kaggle_instructions()
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    print(f"\n⚠️  Note: This will download ~13.5 GB of data")
    response = input(f"\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("  Exiting...")
        return
    
    # Create downloader and run
    downloader = CommonVoiceKaggleDownloader(
        base_dir=BASE_DIR,
        num_utterances=NUM_UTTERANCES
    )
    
    downloader.run_full_pipeline()


if __name__ == "__main__":
    main()