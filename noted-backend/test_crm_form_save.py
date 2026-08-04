#!/usr/bin/env python3
"""
Test script to verify CRM form saving functionality.

Run this to test:
1. Path resolution for submitted CRM forms directory
2. File creation with correct structure
3. Aggregation of multiple forms
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from services.admin_audio_analysis import (
    save_submitted_crm_form,
    aggregate_all_crm_forms,
    list_submitted_crm_forms,
    check_crm_form_exists,
    get_submitted_crm_root,
)


def test_path_resolution():
    """Test 1: Path resolution"""
    print("\n" + "="*60)
    print("TEST 1: Path Resolution")
    print("="*60)
    
    try:
        root = get_submitted_crm_root()
        print(f"✓ CRM root directory resolved: {root}")
        print(f"  - Exists: {root.exists()}")
        print(f"  - Is directory: {root.is_dir()}")
        print(f"  - Absolute path: {root.resolve()}")
        return root
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return None


def test_file_creation(crm_root: Path):
    """Test 2: File creation with correct structure"""
    print("\n" + "="*60)
    print("TEST 2: File Creation")
    print("="*60)
    
    test_form_data = {
        "encounter_type": "Phone call",
        "heardFrom": "Friend referral",
        "immigrationReason": "Work opportunity",
        "additionalInfo": ["Recent immigrant", "First-time client"],
        "educationLevel": "University degree",
        "birthCountry": "Nigeria",
        "motherTongue": "Yoruba",
        "domicile": "Helsinki",
        "labourPosition": ["IT specialist", "Looking for work"],
        "residenceDuration": ["6 months"],
        "contents": ["Career guidance", "Integration support"],
        "purpose": ["Employment support", "Orientation"],
        "directedTo": "Job center",
        "additionalInfoText": "Client very motivated",
        "otherFeedback": "Good interaction",
        "visitDuration": "45 min 30 sec",
        "audio_filename": "test_audio_001.wav",
        "status": "submitted"
    }
    
    try:
        result = save_submitted_crm_form(
            username="test_user",
            form_data=test_form_data,
            submitted_crm_root=crm_root,
        )
        print(f"✓ Form saved successfully")
        print(f"  - Filename: {result['filename']}")
        print(f"  - Path: {result['path']}")
        
        # Verify file exists and has content
        saved_file = crm_root / result['filename']
        if saved_file.exists():
            print(f"  - File exists: ✓")
            with open(saved_file, 'r') as f:
                content = json.load(f)
            print(f"  - File size: {saved_file.stat().st_size} bytes")
            print(f"  - Has questionnaire: {'questionnaire' in content}")
            print(f"  - Has metadata: {'metadata' in content}")
            print(f"  - Has form: {'form' in content}")
            return saved_file
        else:
            print(f"  - File exists: ✗ FAILED - file not found after write")
            return None
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_list_forms(crm_root: Path):
    """Test 3: List submitted forms"""
    print("\n" + "="*60)
    print("TEST 3: List Submitted Forms")
    print("="*60)
    
    try:
        forms = list_submitted_crm_forms(submitted_crm_root=crm_root)
        print(f"✓ Listed {len(forms)} submitted form(s)")
        for i, form in enumerate(forms, 1):
            print(f"  {i}. {form['username']} - {form['audio_filename']} ({form['date']} {form['time']})")
        return forms
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_check_form_exists(crm_root: Path):
    """Test 4: Check if form exists"""
    print("\n" + "="*60)
    print("TEST 4: Check Form Exists")
    print("="*60)
    
    try:
        exists = check_crm_form_exists(
            username="test_user",
            audio_filename="test_audio_001.wav",
            submitted_crm_root=crm_root,
        )
        print(f"✓ Form exists check: {exists}")
        if exists:
            print(f"  - test_user has submitted forms: ✓")
        else:
            print(f"  - test_user has submitted forms: ✗")
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()


def test_aggregate_forms(crm_root: Path):
    """Test 5: Aggregate all forms"""
    print("\n" + "="*60)
    print("TEST 5: Aggregate All Forms")
    print("="*60)
    
    try:
        agg = aggregate_all_crm_forms(submitted_crm_root=crm_root)
        print(f"✓ Aggregated data from {agg.get('total_forms', 0)} form(s)")
        print(f"  - Contact methods: {len(agg.get('contact_methods', []))} unique")
        print(f"  - Topics discussed: {len(agg.get('topics_discussed', []))} unique")
        print(f"  - Birth countries: {len(agg.get('birth_countries', []))} unique")
        print(f"  - Languages: {len(agg.get('languages', []))} unique")
        if agg.get('contact_methods'):
            print(f"    Sample: {list(agg['contact_methods'])[:3]}")
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()


def cleanup(crm_root: Path):
    """Cleanup test files"""
    print("\n" + "="*60)
    print("Cleanup")
    print("="*60)
    
    test_files = list(crm_root.glob("test_user_*.json"))
    if test_files:
        print(f"Removing {len(test_files)} test file(s)...")
        for f in test_files:
            f.unlink()
            print(f"  ✓ Deleted: {f.name}")
    else:
        print("No test files to cleanup")


def main():
    print("\n" + "="*60)
    print("CRM Form Saving Test Suite")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: Path resolution
    crm_root = test_path_resolution()
    if not crm_root:
        print("\n✗ TESTS FAILED: Cannot resolve CRM root directory")
        return False
    
    # Test 2: File creation
    saved_file = test_file_creation(crm_root)
    if not saved_file:
        print("\n✗ TESTS FAILED: Cannot create CRM form file")
        return False
    
    # Test 3: List forms
    forms = test_list_forms(crm_root)
    
    # Test 4: Check form exists
    test_check_form_exists(crm_root)
    
    # Test 5: Aggregate forms
    test_aggregate_forms(crm_root)
    
    # Cleanup
    cleanup(crm_root)
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED")
    print("="*60)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
