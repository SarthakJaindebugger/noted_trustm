# CRM Form Submission Debug Summary

## Changes Made

### 1. Enhanced Logging (Tasks 1 & 3)

**Files Modified:**
- `noted-backend/api/crm_routes.py`
- `noted-backend/services/admin_audio_analysis.py`

**Changes:**
- Added `[CRM_ROUTE]` logging tags in PUT `/sessions/{id}/crm-form` endpoint to track:
  - Form status after update
  - When `form.status == "submitted"` condition is checked
  - Success/failure of save operation with full traceback

- Added `[CRM_SAVE]` logging tags in `save_submitted_crm_form()` to track:
  - Username and safe username conversion
  - Target root directory resolution
  - Directory existence before/after mkdir
  - File path (both relative and absolute)
  - Record creation and file write operations
  - File existence and size after write
  - Any exceptions with full traceback

### 2. Path Resolution with Fallback (Task 2)

**File Modified:**
- `noted-backend/services/admin_audio_analysis.py`

**New Function: `get_submitted_crm_root()`**

Resolves the CRM forms directory with multiple fallbacks for HPC cluster compatibility:

**Priority:**
1. `SUBMITTED_CRM_FORMS_DIR` environment variable (if set)
2. Config settings `storage.crm_dir` (if available)
3. Default: `REPO_ROOT / "knowledgebase" / "submitted_crm_forms"`

**Features:**
- Tests write permission on each candidate before selecting
- Logs `[CRM_PATH]` tags for debugging path resolution
- Handles absolute/relative paths correctly
- Creates directories with `mkdir(parents=True, exist_ok=True)`

**Updated Functions to Use Fallback:**
- `save_submitted_crm_form()` - Main save function
- `check_crm_form_exists()` - Check if user has any submitted forms
- `aggregate_all_crm_forms()` - Aggregate data from all forms
- `list_submitted_crm_forms()` - List all submitted forms with metadata

## How to Debug on HPC Cluster

### Step 1: Check Logs for [CRM_ROUTE] Tag

When form is submitted, you should see in backend logs:

```
[CRM_ROUTE] Form updated for session <session_id>, status=<status>
[CRM_ROUTE] Form status is '<status>', <calling save or skipping>
```

**What to look for:**
- If status is NOT "submitted", form won't be saved (check frontend form submission)
- If status IS "submitted", should see next log line about calling save function

### Step 2: Check Logs for [CRM_SAVE] Tag

After form submission, you should see:

```
[CRM_SAVE] Starting CRM form save for username=<username>, safe_username=<safe_username>
[CRM_SAVE] Target root directory: <path_to_crm_root>
[CRM_SAVE] Root exists before mkdir: <True/False>
[CRM_SAVE] Root directory after mkdir: <True/False>
[CRM_SAVE] File path: <absolute_path_to_file>
[CRM_SAVE] File written successfully: <file_path>
[CRM_SAVE] File exists after write: True
[CRM_SAVE] File size: <size_in_bytes> bytes
```

**If you see an error:**

```
[CRM_SAVE] EXCEPTION during save: <error_message>
```

Full Python traceback will follow. Common issues:
- Permission denied: Backend doesn't have write access to directory
- No space left on device: Shared filesystem full
- Path doesn't exist and can't be created: Parent directory permissions

### Step 3: Check Logs for [CRM_PATH] Tag

Before save, `get_submitted_crm_root()` will log path resolution:

```
[CRM_PATH] Using SUBMITTED_CRM_FORMS_DIR from environment: <env_value>
[CRM_PATH] Checking candidate: <candidate_path>
[CRM_PATH] Selected CRM directory: <final_path>
```

Or if no env variable:

```
[CRM_PATH] Using crm_dir from config: <config_value>
[CRM_PATH] Checking candidate: <candidate_path>
[CRM_PATH] Using fallback CRM directory: <final_path>
```

**What to look for:**
- Verify the final directory path is correct on HPC
- If "Checking candidate" shows rejected paths, see why (usually permissions)

### Step 4: Set Environment Variable if Needed

If the default path isn't working on HPC, set the environment variable before starting backend:

```bash
# On HPC, before starting backend
export SUBMITTED_CRM_FORMS_DIR=/path/to/shared/knowledgebase/submitted_crm_forms

# Create the directory if it doesn't exist
mkdir -p $SUBMITTED_CRM_FORMS_DIR
chmod 755 $SUBMITTED_CRM_FORMS_DIR

# Start backend
python noted_backend_start_script.py
```

### Step 5: Verify File Creation

After submission, check if file was created:

```bash
# List all submitted CRM forms
ls -lh knowledgebase/submitted_crm_forms/

# Or if using env variable
ls -lh $SUBMITTED_CRM_FORMS_DIR/

# View specific file
cat knowledgebase/submitted_crm_forms/username_DD.MM.YYYY_HH_MM_SS.json | python -m json.tool
```

Expected file structure:
```json
{
  "questionnaire": {
    "What is the contact method used by Advisee(s)?": "...",
    "Heard from the guidance/advice position (if other where?)": "...",
    ...
  },
  "metadata": {
    "date_time": "DD/MM/YYYY HH:MM",
    "audio_file": "...",
    ...
  },
  "form": {
    "encounter_type": "...",
    "heardFrom": "...",
    ...
  },
  "username": "...",
  "submitted_at": "YYYY-MM-DDTHH:MM:SS.######"
}
```

## Testing Script

A comprehensive test script is available: `noted-backend/test_crm_form_save.py`

To run (requires Python environment with all dependencies):

```bash
cd noted-backend
python test_crm_form_save.py
```

This will:
1. Test path resolution with fallbacks
2. Create a test CRM form file
3. Verify file structure
4. Test listing forms
5. Test aggregation
6. Clean up test files

## Expected Behavior After Fixes

### Scenario 1: User submits form locally
- File appears in `knowledgebase/submitted_crm_forms/username_*.json` ✓
- Admin dashboard can read and aggregate data on page load ✓
- Logs show all [CRM_SAVE] and [CRM_ROUTE] tags ✓

### Scenario 2: Frontend and backend on different HPC nodes
- Set `SUBMITTED_CRM_FORMS_DIR` to shared filesystem path on both nodes
- File appears in shared CRM directory
- Admin dashboard (on frontend node) can read files from shared location ✓

### Scenario 3: Multiple form submissions
- Each file named with unique timestamp: `username_DD.MM.YYYY_HH_MM_SS.json`
- Admin aggregation reads all files and merges data
- Dashboard shows aggregated data from all forms ✓

## Key Files Modified

1. **noted-backend/services/admin_audio_analysis.py**
   - Added `get_submitted_crm_root()` function
   - Updated `save_submitted_crm_form()` with logging
   - Updated `check_crm_form_exists()` to use fallback
   - Updated `aggregate_all_crm_forms()` to use fallback
   - Updated `list_submitted_crm_forms()` to use fallback

2. **noted-backend/api/crm_routes.py**
   - Added logging to PUT `/sessions/{id}/crm-form` endpoint
   - Added detailed logging before/after save operation

## Next Steps if Issue Persists

1. **Collect Full Logs**
   - Enable DEBUG level logging
   - Reproduce the issue (submit a form)
   - Collect all [CRM_ROUTE], [CRM_SAVE], and [CRM_PATH] log lines
   - Share complete traceback if error occurs

2. **Check Filesystem**
   - Verify shared filesystem is mounted on both frontend and backend nodes
   - Check permissions: `ls -ld knowledgebase/submitted_crm_forms/`
   - Try creating test file manually: `touch knowledgebase/submitted_crm_forms/test.txt`

3. **Verify Form Status**
   - Add logging to frontend form submission to confirm `status: "submitted"` is sent
   - Use browser dev tools to inspect network request to backend

4. **Test Endpoint Directly**
   - Use curl to submit form directly (see CRM_FORM_TEST_GUIDE.md)
   - Bypass any frontend logic

## Environment Variable Reference

Set on backend before starting:

```bash
# Explicitly set CRM forms directory for HPC
export SUBMITTED_CRM_FORMS_DIR=/shared/storage/noted/submitted_crm_forms

# Optional: Set data directory (used by get_default_users_root and fallback config)
export NOTED_DATA_DIR=/shared/storage/noted/data
```

These variables have priority in `get_submitted_crm_root()` and `get_default_users_root()`.
