# Test CRM Form Submit — Simple File Copy

## What it does

When the user opens a CRM form from the dashboard:
1. Frontend calls `POST /audio/crm-form/submit` with `{"audio_filename": "dia03sce1SA.wav"}`
2. Backend finds the most recent `uploads/dia03sce1SA*/6_crm_form_parsed.json`
3. Copies it to `knowledgebase/submitted_crm_forms/username_DD.MM.YYYY_HH_MM_SS.json`
4. Returns success

## Test it with curl

```bash
# Replace YOUR_TOKEN with actual token from sessionStorage
curl -X POST http://localhost:5000/api/v1/audio/crm-form/submit \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"audio_filename": "dia03sce1SA.wav"}'
```

Expected response:
```json
{
  "success": true,
  "filename": "demo_04.08.2026_12_30_45.json",
  "source": "knowledgebase/users_admin_data/users/demo/uploads/dia03sce1SA/6_crm_form_parsed.json",
  "dest": "knowledgebase/submitted_crm_forms/demo_04.08.2026_12_30_45.json"
}
```

## Check the logs

You should see:
```
[CRM_SUBMIT] user=demo audio_stem=dia03sce1SA user_uploads=/path/to/users/demo/uploads
[CRM_SUBMIT] matching dirs: ['dia03sce1SA']
[CRM_SUBMIT] Found source JSON: /path/to/users/demo/uploads/dia03sce1SA/6_crm_form_parsed.json
[CRM_SUBMIT] Copying /path/.../6_crm_form_parsed.json → /path/.../submitted_crm_forms/demo_04.08.2026_12_30_45.json
[CRM_SUBMIT] SUCCESS — saved demo_04.08.2026_12_30_45.json (12345 bytes)
```

## Check the file was created

```bash
ls -lh knowledgebase/submitted_crm_forms/
```

You should see: `demo_04.08.2026_12_30_45.json`

## How it's triggered from the dashboard

When user clicks "Open CRM" button:
1. `openCrmForm(audioFile)` in `dashboard.js` calls:
   ```javascript
   await apiClient.post('/audio/crm-form/submit', { audio_filename: audioFile.name });
   ```
2. This copies the JSON immediately
3. Then the popup opens normally

So every time the user opens the form, a timestamped copy is saved.
