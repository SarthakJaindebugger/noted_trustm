# CRM Form Submission Testing Guide

This guide helps debug and verify that CRM forms are being saved correctly to `knowledgebase/submitted_crm_forms`.

## Prerequisites

- Backend running and accessible at `http://localhost:5000` (or your backend URL)
- User authentication token ready
- Logs configured to output [CRM_SAVE] and [CRM_ROUTE] tags

## Test Steps

### 1. Prepare Test Data

Create a test CRM form payload:

```json
{
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
```

### 2. Run Backend with Verbose Logging

Start the backend with logging enabled:

```bash
# On HPC or locally
cd noted-backend
export FLASK_ENV=development
export LOG_LEVEL=INFO
python -m noted_backend  # or your start command
```

Watch the logs for [CRM_SAVE] and [CRM_ROUTE] tags.

### 3. Submit CRM Form via cURL

Replace `YOUR_TOKEN` and `SESSION_ID` with real values:

```bash
curl -X PUT http://localhost:5000/sessions/SESSION_ID/crm-form \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "encounter_type": "Phone call",
    "heardFrom": "Friend referral",
    "immigrationReason": "Work opportunity",
    "additionalInfo": ["Recent immigrant"],
    "educationLevel": "University degree",
    "birthCountry": "Nigeria",
    "motherTongue": "Yoruba",
    "domicile": "Helsinki",
    "labourPosition": ["IT specialist"],
    "residenceDuration": ["6 months"],
    "contents": ["Career guidance"],
    "purpose": ["Employment support"],
    "directedTo": "Job center",
    "additionalInfoText": "Test submission",
    "otherFeedback": "Good",
    "visitDuration": "45 min 30 sec",
    "audio_filename": "test_audio_001.wav",
    "status": "submitted"
  }'
```

### 4. Check Response

Expected response should be:
```json
{
  "session_identifier": "...",
  "status": "submitted",
  "encounter_type": "Phone call",
  ...
}
```

And you should see in logs:
```
[CRM_ROUTE] Form updated for session ..., status=submitted
[CRM_ROUTE] Form status is 'submitted', calling save_submitted_crm_form...
[CRM_SAVE] Starting CRM form save for username=..., safe_username=...
[CRM_SAVE] Target root directory: /path/to/knowledgebase/submitted_crm_forms
[CRM_SAVE] Root exists before mkdir: False
[CRM_SAVE] Root directory after mkdir: True
[CRM_SAVE] File path: /path/to/knowledgebase/submitted_crm_forms/username_DD.MM.YYYY_HH_MM_SS.json
[CRM_SAVE] File written successfully: ...
[CRM_SAVE] File exists after write: True
[CRM_SAVE] File size: XXXX bytes
[CRM_ROUTE] CRM form saved successfully: {"filename": "...", "path": "..."}
```

### 5. Verify File Creation

Check if the file exists:

```bash
# Local
ls -lh knowledgebase/submitted_crm_forms/

# On HPC (adjust path as needed)
ls -lh $HOME/noted-main/knowledgebase/submitted_crm_forms/
```

You should see a file named like: `username_14.08.2026_14_00_20.json`

### 6. Verify File Content

```bash
cat knowledgebase/submitted_crm_forms/username_14.08.2026_14_00_20.json
```

Should contain:
```json
{
  "questionnaire": {
    "What is the contact method used by Advisee(s)?": "Phone call",
    ...
  },
  "metadata": {
    "date_time": "14/08/2026 14:00",
    ...
  },
  "form": {
    "encounter_type": "Phone call",
    ...
  },
  "username": "username",
  "submitted_at": "2026-08-14T14:00:20.123456"
}
```

### 7. Verify Admin Dashboard Can Read Forms

Check that the aggregation endpoint works:

```bash
curl -X GET http://localhost:5000/admin/crm-forms/aggregated \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Should return aggregated data from all submitted forms.

### 8. Verify List Endpoint

```bash
curl -X GET http://localhost:5000/admin/crm-forms \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Should list all submitted forms with their metadata.

## Troubleshooting

### Issue: File not created despite success message

**Possible Causes:**
1. `form.status != "submitted"` - Check log for `[CRM_ROUTE] Form status is...` message
2. Path resolution issue on HPC - Check log for `[CRM_SAVE] Target root directory:` and ensure directory exists
3. Permission denied - Check if backend process has write access to knowledgebase/
4. Exception during save - Check log for `[CRM_SAVE] EXCEPTION during save:`

**Solutions:**
1. Verify form payload includes `"status": "submitted"`
2. Set `SUBMITTED_CRM_FORMS_DIR` environment variable on HPC if default path is wrong:
   ```bash
   export SUBMITTED_CRM_FORMS_DIR=/path/to/shared/knowledgebase/submitted_crm_forms
   ```
3. Check directory permissions:
   ```bash
   mkdir -p knowledgebase/submitted_crm_forms
   chmod 755 knowledgebase/submitted_crm_forms
   ```
4. Enable full Python traceback in logs if exception is truncated

### Issue: Form status is not "submitted"

Check the form update logic in `noted-backend/api/crm_routes.py`. The status should be set to "submitted" before the save function is called.

### Issue: Path resolution on HPC not working

The `get_submitted_crm_root()` function tests write permissions. Check logs for `[CRM_PATH]` tags to see which candidate directories were tested and why they were rejected.

## Log Tag Reference

- `[CRM_ROUTE]` - CRM form submission route (PUT /sessions/{id}/crm-form)
- `[CRM_SAVE]` - CRM form save function execution
- `[CRM_PATH]` - Path resolution and candidate testing in get_submitted_crm_root()

## Expected File Structure

After successful submission, you should have:

```
knowledgebase/
├── submitted_crm_forms/
│   ├── username1_14.08.2026_14_00_20.json
│   ├── username1_14.08.2026_14_05_10.json
│   ├── username2_14.08.2026_15_10_30.json
│   └── ...
```

Each file contains the questionnaire, metadata, and form data merged together.

## Next Steps

1. Run the test and monitor the logs for [CRM_SAVE] and [CRM_ROUTE] tags
2. Verify files are created in `knowledgebase/submitted_crm_forms/`
3. Check admin dashboard can read and aggregate the data
4. If issues persist, collect the log output and share it for debugging
