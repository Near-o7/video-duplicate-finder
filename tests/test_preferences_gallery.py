from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QMessageBox

from comparador.settings import Preferences, load_preferences, save_preferences
from comparador.i18n import tr, set_language
from comparador.preferences_dialog import PreferencesDialog
from comparador.models import ScanOptions
from comparador.engine import scan
from comparador.operations import plan_actions
from comparador.ui import MainWindow
from comparador.gallery import FrameViewer
from comparador.reports import export_html


def sample(roots, tmp_path):
    a,b=roots
    (a/'first.bin').write_bytes(b'same')
    (a/'second.bin').write_bytes(b'same')
    (b/'third.bin').write_bytes(b'same')
    return scan(ScanOptions(a,b),cache_path=tmp_path/'cache.db')


def test_preferences_round_trip_has_no_paths(tmp_path):
    path=tmp_path/'settings.json'
    prefs=Preferences(language='en',theme='dark',two_folders=True,similar=True,gallery_frames=24)
    save_preferences(prefs,path)
    assert load_preferences(path)==prefs
    assert set(json.loads(path.read_text()))==set(asdict(prefs))
    path.write_text('{bad json')
    assert load_preferences(path)==Preferences()
    path.write_text('{"theme":"invalid"}')
    assert load_preferences(path)==Preferences()


def test_language_switch_and_dark_light_theme(qtbot, roots, tmp_path):
    w=MainWindow();qtbot.addWidget(w)
    w.scan_done(sample(roots,tmp_path))
    w.apply_preferences(replace(w.preferences,language='en',theme='dark'))
    assert w.scan_button.text()=='Scan'
    assert w.menuBar().actions()[0].text()=='Settings'
    assert w.palette().color(QPalette.ColorRole.Window).lightness()<100
    assert w.search.palette().color(QPalette.ColorRole.Text).lightness()>150
    assert not w.progress.isVisible()
    w.apply_preferences(replace(w.preferences,language='es',theme='light'))
    assert w.scan_button.text()=='Analizar'
    assert w.palette().color(QPalette.ColorRole.Window).lightness()>200
    qtbot.waitUntil(lambda:not w.jobs,timeout=5000)


def test_preferences_dialog_defaults(qtbot):
    dialog=PreferencesDialog(Preferences(language='es',theme='light'))
    qtbot.addWidget(dialog)
    dialog.language.setCurrentIndex(dialog.language.findData('en'))
    dialog.profile.setCurrentIndex(dialog.profile.findData('full'))
    dialog.similarity.setValue(95)
    assert dialog.preferences().language=='en'
    assert dialog.preferences().video_profile=='full'
    assert dialog.preferences().similarity==95


def test_keep_choice_respects_primary_protection_and_reference(qtbot,roots,tmp_path,monkeypatch):
    w=MainWindow();qtbot.addWidget(w)
    result=sample(roots,tmp_path);w.scan_done(result)
    primary=next(f for f in result.files.values() if f.root=='primary')
    secondary=next(f for f in result.files.values() if f.root=='secondary')
    w.left_preview.set_record(primary);w.right_preview.set_record(secondary)
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.No)
    w.choose_preview(False)
    assert not w.selected_keys()
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
    w.choose_preview(False)
    assert w.selected_keys()==[primary.key]
    assert w.unlock.isChecked()
    actions=plan_actions(result,w.selected_keys(),'trash',unlocked=True,keepers=w.choose_keepers(w.selected_keys()))
    assert actions[0].keeper==secondary.key
    assert secondary.key not in w.selected_keys()
    qtbot.waitUntil(lambda:not w.jobs,timeout=5000)


def test_lazy_gallery_keeps_three_initial_frames(qtbot,roots,tmp_path,media):
    import shutil
    a,_=roots;shutil.copy2(media['original'],a/'sample.mp4')
    w=MainWindow();qtbot.addWidget(w)
    w.scan_done(scan(ScanOptions(a,similar=True),cache_path=tmp_path/'cache.db'))
    qtbot.waitUntil(lambda:not w.jobs,timeout=10000)
    card=w.left_preview
    assert len(card.thumbs)==3
    assert len(card.times)==12
    w.more_frames(card)
    qtbot.waitUntil(lambda:not w.jobs,timeout=10000)
    assert len(card.thumbs)==6
    assert any(raw for raw,_ in card.images.values())


def test_frame_viewer_navigation(qtbot):
    from types import SimpleNamespace
    v=FrameViewer(SimpleNamespace(path='sample.mp4'),[1,2,3,4],0)
    qtbot.addWidget(v)
    v.show_index(2)
    assert v.index==2
    v.show_index(4)
    assert v.index==0


def test_reports_and_source_strings_are_english_when_selected(roots,tmp_path):
    set_language('en')
    result=sample(roots,tmp_path)
    export_html(result,tmp_path/'report.html')
    data=(tmp_path/'report.html').read_text(encoding='utf-8')
    assert '<html lang="en">' in data
    assert 'Exact copy' in data
    assert 'Ruta' not in data


def test_visible_translation_prose_has_no_unwanted_punctuation():
    catalog=json.loads((Path(__file__).parents[1]/'comparador/locales/es.json').read_text(encoding='utf-8'))
    for text in list(catalog)+list(catalog.values()):
        assert '·' not in text and '\u2014' not in text
        assert ';' not in text.replace(';;','')


def test_public_allowlist_excludes_local_data(tmp_path):
    from tools.audit_public import public_files, audit
    package=tmp_path/'comparador'
    package.mkdir()
    source=package/'app.py'
    source.write_text('value = 1')
    (package/'settings.json').write_text('{"language":"en"}')
    (tmp_path/'artifacts').mkdir()
    (tmp_path/'artifacts/report.txt').write_text('local output')
    assert public_files(tmp_path)==[source]
    assert not audit(public_files(tmp_path),tmp_path)
    source.write_text('/'+'home/'+'example/video.mp4')
    assert audit(public_files(tmp_path),tmp_path)
