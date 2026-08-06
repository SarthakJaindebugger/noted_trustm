from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.admin_audio_analysis as admin_audio_analysis


def test_list_user_audio_files_uses_noted_data_dir_env(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    data_dir = repo_root / "knowledgebase" / "users_admin_data"
    users_root = data_dir / "users"
    audio_path = users_root / "alice" / "recordings" / "demo.wav"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"fake-audio")

    monkeypatch.setenv("NOTED_DATA_DIR", str(data_dir))
    monkeypatch.setattr(admin_audio_analysis, "REPO_ROOT", repo_root)
    monkeypatch.setattr(admin_audio_analysis, "DEFAULT_USERS_ROOT", repo_root / "missing")

    result = admin_audio_analysis.list_user_audio_files()

    assert len(result) == 1
    assert result[0]["path"] == "knowledgebase/users_admin_data/users/alice/recordings/demo.wav"
    assert result[0]["username"] == "alice"


def test_dashboard_audio_files_classify_recordings_by_upload_prefix_and_crm(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    users_root = repo_root / "knowledgebase" / "users_admin_data" / "users"
    alice_root = users_root / "alice"

    analyzed_audio = alice_root / "recordings" / "dia01sce1SA_1fb1239a.WAV"
    pending_audio = alice_root / "recordings" / "dia02sce1SA_abcdef.WAV"
    analyzed_audio.parent.mkdir(parents=True)
    analyzed_audio.write_bytes(b"fake-audio")
    pending_audio.write_bytes(b"fake-audio")

    matching_upload = alice_root / "uploads" / "dia01sce1SA_1fb1239a_03-08-2026_1153"
    matching_upload.mkdir(parents=True)
    (matching_upload / "6_crm_form.html").write_text("<html></html>")
    (matching_upload / "6_crm_form_parsed.json").write_text("{}")

    monkeypatch.setattr(admin_audio_analysis, "REPO_ROOT", repo_root)

    result = admin_audio_analysis.list_dashboard_audio_files_for_username("alice", users_root)

    assert [item["name"] for item in result["analyzed_audio_files"]] == ["dia01sce1SA_1fb1239a.WAV"]
    assert result["analyzed_audio_files"][0]["analysis_key"] == "dia01sce1SA"
    assert result["analyzed_audio_files"][0]["analysis_dir_name"] == "dia01sce1SA_1fb1239a_03-08-2026_1153"
    assert result["analyzed_audio_files"][0]["crm_form_html_path"] == (
        "knowledgebase/users_admin_data/users/alice/uploads/"
        "dia01sce1SA_1fb1239a_03-08-2026_1153/6_crm_form.html"
    )
    assert [item["name"] for item in result["new_audio_files"]] == ["dia02sce1SA_abcdef.WAV"]
    assert result["pending_audio_files"] == result["new_audio_files"]
