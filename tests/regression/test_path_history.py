from pathlib import Path

from astro_stacker.ui.path_history import last_dialog_directory, remember_dialog_path


class FakeSettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default, value_type):
        value = self.values.get(key, default)
        return value_type(value)

    def setValue(self, key, value):
        self.values[key] = value


def test_remembers_parent_directory_for_selected_file(tmp_path: Path):
    settings = FakeSettings()
    selected = tmp_path / "project.astrostacker"

    remember_dialog_path(settings, selected)

    assert last_dialog_directory(settings) == tmp_path


def test_remembers_selected_directory(tmp_path: Path):
    settings = FakeSettings()

    remember_dialog_path(settings, tmp_path, directory=True)

    assert last_dialog_directory(settings) == tmp_path


def test_missing_saved_directory_uses_existing_fallback_parent(tmp_path: Path):
    settings = FakeSettings()
    settings.values["dialogs/last_directory"] = str(tmp_path / "removed")

    assert last_dialog_directory(settings, tmp_path / "new-output") == tmp_path
