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
