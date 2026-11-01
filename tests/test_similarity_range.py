from unittest.mock import patch
import threading

import pytest

from comparador.models import ScanOptions, FileRecord
from comparador.settings import Preferences, save_preferences, load_preferences
from comparador.preferences_dialog import PreferencesDialog
from comparador.ui import MainWindow
from comparador.video import find_similar


@pytest.mark.parametrize('value', [50, 55, 65])
def test_lower_thresholds_are_valid_and_persist(value, tmp_path):
    ScanOptions(tmp_path, similar=True, similarity=value).validate()
    preferences = Preferences(similarity=value)
    target = tmp_path / 'preferences.json'
    save_preferences(preferences, target)
    assert load_preferences(target).similarity == value


def test_values_below_new_minimum_remain_invalid(tmp_path):
    with pytest.raises(ValueError):
        ScanOptions(tmp_path, similarity=49).validate()
    with pytest.raises(ValueError):
        Preferences(similarity=49).validate()


def test_main_and_settings_controls_allow_fifty_percent(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    dialog = PreferencesDialog(window.preferences)
    qtbot.addWidget(dialog)
    window.similarity.setValue(50)
    dialog.similarity.setValue(50)
    assert window.similarity.value() == 50
    assert dialog.preferences().similarity == 50


def test_lowering_threshold_finds_candidate_without_decoding(tmp_path):
    hashes = [int('10' * 31 + '0', 2), int('10' * 31 + '0', 2) ^ ((1 << 20) - 1)]
    records = [FileRecord(str(tmp_path / name), 'primary', name, 100, 0, 0, 0,
                          metadata={'duration': 6}, fingerprint={'step': 1, 'hashes': [value] * 6})
               for name, value in zip(('first.mp4', 'second.mp4'), hashes)]
    with patch('comparador.video.run_media', side_effect=AssertionError('Must not decode existing fingerprints')):
        assert not find_similar(records, 70, 80, threading.Event())
        matches = find_similar(records, 65, 80, threading.Event())
    assert len(matches) == 1
    assert 65 <= matches[0].similarity < 70
