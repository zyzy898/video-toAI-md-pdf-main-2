from pathlib import Path

from services.file_ops import safe_remove_file


def test_safe_remove_file_removes_existing_file(tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_text("content", encoding="utf-8")

    safe_remove_file(target)

    assert not target.exists()


def test_safe_remove_file_ignores_missing_paths_and_directories(tmp_path):
    missing = tmp_path / "missing.mp4"
    directory = tmp_path / "folder"
    directory.mkdir()

    safe_remove_file(missing)
    safe_remove_file(directory)

    assert directory.is_dir()


def test_safe_remove_file_calls_error_callback_on_unlink_error():
    class FailingPath:
        def exists(self):
            return True

        def is_file(self):
            return True

        def unlink(self):
            raise OSError("locked")

        def __str__(self):
            return "locked-file"

    errors = []

    safe_remove_file(FailingPath(), on_error=lambda path, exc: errors.append((path, exc)))

    assert len(errors) == 1
    assert str(errors[0][0]) == "locked-file"
    assert isinstance(errors[0][1], OSError)
