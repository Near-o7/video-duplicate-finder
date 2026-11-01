from __future__ import annotations
from .i18n import tr
from pathlib import Path
import os
import subprocess
import threading
import time
import traceback
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFontDatabase, QIcon, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QSpinBox, QFrame, QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QProgressBar, QDialog, QDialogButtonBox, QPlainTextEdit, QAbstractItemView, QStyle, QScrollArea
from . import __version__
from .cache import data_dir
from .engine import scan
from .models import ScanOptions, Cancelled, duration_text, human_size
from .operations import plan_actions, execute_actions
from .reports import export_csv, export_html
from .video import find_similar, thumbnail
from .appearance import apply_theme, icon, status_color
from .settings import load_preferences, save_preferences, RESULT_COLUMNS
from .i18n import set_language
from .layout import build_window
from .selection import redundant_keys

def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget

def button(text, icon=None, name=None):
    widget = QPushButton(text)
    if icon is not None:
        from .appearance import icon as line_icon
        names = {QStyle.StandardPixmap.SP_MediaPlay: 'play', QStyle.StandardPixmap.SP_DirIcon: 'folder', QStyle.StandardPixmap.SP_DirOpenIcon: 'folder', QStyle.StandardPixmap.SP_DialogSaveButton: 'export', QStyle.StandardPixmap.SP_TrashIcon: 'trash', QStyle.StandardPixmap.SP_DirLinkIcon: 'move'}
        if icon in names:
            widget.setIcon(line_icon(names[icon]))
    if name:
        widget.setObjectName(name)
    return widget

class Worker(QThread):
    progress = Signal(str, int, int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancel = threading.Event()

    def run(self):
        try:
            self.completed.emit(self.fn(self.cancel, self.progress.emit))
        except Cancelled:
            self.failed.emit(tr('Operation canceled. Completed file actions are kept.'))
        except Exception as exc:
            try:
                with (data_dir() / 'errores.log').open('a', encoding='utf-8') as stream:
                    traceback.print_exc(file=stream)
            except OSError:
                pass
            self.failed.emit(str(exc))

class SortItem(QTableWidgetItem):

    def __lt__(self, other):
        left = self.data(Qt.ItemDataRole.UserRole + 1)
        right = other.data(Qt.ItemDataRole.UserRole + 1)
        if left is not None and right is not None:
            return left < right
        return self.text().casefold() < other.text().casefold()

from .gallery import PreviewCard, FrameViewer

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.preferences = load_preferences()
        self.column_width_timer = QTimer(self)
        self.column_width_timer.setSingleShot(True)
        self.column_width_timer.setInterval(400)
        self.column_width_timer.timeout.connect(self.persist_column_widths)
        set_language(self.preferences.language)
        for filename in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
            font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / filename
            if font.exists():
                QFontDatabase.addApplicationFont(str(font))
        self.result = None
        self.worker = None
        self.jobs = []
        self.thumb_worker = None
        self.preview_generation = 0
        self.peer_entries = []
        self.current_key = None
        self.checked_keys = set()
        self.preferred_keepers = {}
        self.lightbox = None
        self.lightbox_worker = None
        self.new_scan = False
        self.last_progress = 0.0
        self.close_pending = False
        self.comparison_sized = False
        self.setWindowTitle(tr('Video Duplicate Finder {p0}', p0=f'{__version__}'))
        self.setWindowIcon(icon('app'))
        self.resize(1440, 960)
        self.setMinimumSize(1000, 640)
        screen = QApplication.primaryScreen()
        if screen and QApplication.platformName() != 'offscreen':
            available = screen.availableGeometry()
            self.resize(min(1440, available.width() - 40), min(960, available.height() - 50))
        apply_theme(QApplication.instance(), self.preferences.theme)
        self._build()
        self.apply_defaults()
        self._set_busy(False)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self.system_theme_changed)

    def _build(self):
        self.comparison_sized = False
        build_window(self)
        self.apply_result_columns()
        self.last_result_sort = (1, Qt.SortOrder.AscendingOrder)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self.remember_result_sort)
        self.table.horizontalHeader().sectionResized.connect(
            lambda index, previous, width, table=self.table: self.column_width_changed(table, index, width))
        self.menuBar().clear()
        menu = self.menuBar().addMenu(tr('Settings'))
        self.settings_action = menu.addAction(tr('Preferences...'))
        self.settings_action.triggered.connect(self.show_settings)
        for card, is_left in [(self.left_preview, True), (self.right_preview, False)]:
            card.keep_requested.connect(lambda left=is_left: self.choose_preview(left))
            card.remove_requested.connect(lambda left=is_left: self.choose_preview(not left))
            card.more_requested.connect(lambda c=card: self.more_frames(c))
            card.frame_requested.connect(lambda index, c=card: self.expand_frame(c, index))
        shortcut = QShortcut(QKeySequence.StandardKey.SelectAll, self.table)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(self.select_all_visible)
        self.select_all_shortcut = shortcut

    def apply_result_columns(self):
        for index, (key, _) in enumerate(RESULT_COLUMNS):
            self.table.setColumnHidden(index, key not in self.preferences.visible_columns)

    def remember_result_sort(self, column, order):
        # The first header selects files. Sorting by its changing decision text
        # would move the current review row as soon as a copy is marked.
        if column == 0:
            self.table.sortItems(*self.last_result_sort)
        else:
            self.last_result_sort = (column, order)

    def column_width_changed(self, table, index, width):
        if table is not self.table or table.isColumnHidden(index) or not 48 <= width <= 2400:
            return
        self.preferences.column_widths[RESULT_COLUMNS[index][0]] = width
        self.column_width_timer.start()

    def persist_column_widths(self):
        self.column_width_timer.stop()
        try:
            save_preferences(self.preferences)
        except (OSError, ValueError) as exc:
            self.notice.setText(tr('Column widths could not be saved: {error}', error=str(exc)))
            self.notice.show()

    def apply_defaults(self):
        p = self.preferences
        self.folder_mode.setCurrentIndex(int(p.two_folders))
        self.recursive.setChecked(p.recursive)
        self.file_filter.setCurrentIndex(int(p.videos_only))
        self.analysis_mode.setCurrentIndex(int(p.similar))
        self.video_profile.setCurrentIndex(self.video_profile.findData(p.video_profile))
        self.similarity.setValue(p.similarity)
        self.coverage.setValue(p.coverage)

    def configure_result_filters(self, *_):
        two = bool(self.result.options.secondary) if self.result else self.folder_mode.currentIndex() == 1
        scope = self.scope_filter.currentData()
        view = self.view_filter.currentData()
        if two != getattr(self, '_filter_two', two):
            scope = 0 if two else 1
        self._filter_two = two
        for combo in (self.scope_filter, self.view_filter):
            combo.blockSignals(True)
            combo.clear()
        scopes = [('Both folders', 0), ('Primary', 1), ('Secondary', 2)] if two else [('This folder', 1)]
        views = [('All results', 0), ('Exact copies', 1), ('Possible video duplicates', 2)]
        if two:
            views += [('Secondary files without an exact primary copy', 3), ('Secondary files without matches', 4),
                      ('Duplicates within primary', 5), ('Duplicates within secondary', 6)]
        views += [('Errors or pending files', 7), ('All matches', 8)]
        for title, value in scopes:
            self.scope_filter.addItem(tr(title), value)
        for title, value in views:
            self.view_filter.addItem(tr(title), value)
        for combo, value in [(self.scope_filter, scope), (self.view_filter, view)]:
            index = combo.findData(value)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        self.scope_label.setVisible(two)
        self.scope_filter.setVisible(two)
        self.unlock.setVisible(two)
        self.metrics[3].setVisible(two)
        self.metric_labels[3].setVisible(two)
        self.primary_label.setText(tr('Primary folder for reference copies') if self.folder_mode.currentIndex() else tr('Folder to review'))

    def file_location(self, record):
        if not self.result.options.secondary:
            return tr('This folder')
        return tr('Primary') if record.root == 'primary' else tr('Secondary')

    def system_theme_changed(self, *_):
        app = QApplication.instance()
        if self.preferences.theme == 'system' and not getattr(app, '_applying_theme', False):
            apply_theme(app, 'system')

    def show_settings(self):
        if self.worker:
            return
        from .preferences_dialog import PreferencesDialog
        dialog = PreferencesDialog(self.preferences, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.preferences()
        try:
            save_preferences(updated)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr('Settings'), str(exc))
            return
        self.apply_preferences(updated)

    def apply_preferences(self, preferences):
        sort_column = self.table.horizontalHeader().sortIndicatorSection()
        sort_order = self.table.horizontalHeader().sortIndicatorOrder()
        active_key = self.current_key
        peer_key = self.right_preview.record.key if self.right_preview.record else None
        comparison_hidden = self.preview_scroll.isHidden()
        setup_hidden = self.setup_panel.isHidden()
        notice_hidden = self.notice.isHidden()
        split_sizes = self.results_split.sizes()
        old_position = self.preferences.comparison_position
        paths = (self.primary_path.text(), self.secondary_path.text())
        controls = [self.folder_mode, self.file_filter, self.analysis_mode, self.video_profile]
        indices = [c.currentIndex() for c in controls]
        recursive, unlocked = self.recursive.isChecked(), self.unlock.isChecked()
        thresholds = self.similarity.value(), self.coverage.value()
        selection = set(self.checked_keys)
        preferred_keepers = dict(self.preferred_keepers)
        result = self.result
        scope, view, query = self.scope_filter.currentData(), self.view_filter.currentData(), self.search.text()
        if self.thumb_worker:
            self.thumb_worker.cancel.set()
        self.preview_generation += 1
        self.preferences = preferences
        set_language(preferences.language)
        apply_theme(QApplication.instance(), preferences.theme)
        old = self.takeCentralWidget()
        self._build()
        old.deleteLater()
        self.setWindowTitle(tr('Video Duplicate Finder {p0}', p0=__version__))
        if result:
            self.table.sortItems(sort_column, sort_order)
            for control, value in [(self.scope_filter,scope),(self.view_filter,view)]:
                control.blockSignals(True)
                control.setCurrentIndex(max(0, control.findData(value)))
                control.blockSignals(False)
            self.search.blockSignals(True)
            self.search.setText(query)
            self.search.blockSignals(False)
            for c, index in zip([self.folder_mode,self.file_filter,self.analysis_mode,self.video_profile],indices):
                c.setCurrentIndex(index)
            self.recursive.setChecked(recursive)
            self.similarity.setValue(thresholds[0])
            self.coverage.setValue(thresholds[1])
            self.unlock.setChecked(unlocked)
            self.scan_done(result)
            self.preferred_keepers = preferred_keepers
            self.set_checked(selection)
            if active_key in self.visible_keys():
                self.table.selectRow(self.visible_keys().index(active_key))
                for index, (peer, _) in enumerate(self.peer_entries):
                    if peer.key == peer_key:
                        self.peer_combo.setCurrentIndex(index)
                        break
            self.setup_panel.setVisible(not setup_hidden)
            self.setup_toggle.setText(tr('Edit folders and scan options') if setup_hidden else tr('Hide scan options'))
            self.notice.setVisible(not notice_hidden)
            if comparison_hidden:
                self.preview_scroll.hide()
                self.comparison_toggle.setText(tr('Show comparison'))
            elif old_position == preferences.comparison_position:
                self.results_split.setSizes(split_sizes)
                self.comparison_sized = True
        else:
            self.apply_defaults()
        self.primary_path.setText(paths[0])
        self.secondary_path.setText(paths[1])
        self._set_busy(False)

    def _folder_row(self, placeholder):
        row = QHBoxLayout()
        row.setSpacing(5)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setMinimumWidth(0)
        choose = button('', QStyle.StandardPixmap.SP_DirOpenIcon)
        choose.setToolTip(tr('Choose folder'))
        choose.setFixedWidth(38)
        choose.clicked.connect(lambda: self.choose_folder(edit))
        row.addWidget(edit, 1)
        row.addWidget(choose)
        edit._picker = choose
        return (edit, row)

    def choose_folder(self, edit):
        path = QFileDialog.getExistingDirectory(self, tr('Choose a folder'), edit.text() or str(Path.home()))
        if path:
            edit.setText(path)
            edit.setToolTip(path)

    def options(self):
        if not self.primary_path.text().strip():
            raise ValueError(tr('Choose a primary folder.'))
        if self.folder_mode.currentIndex() == 1 and (not self.secondary_path.text().strip()):
            raise ValueError(tr('Choose a secondary folder.'))
        options = ScanOptions(Path(self.primary_path.text().strip()), Path(self.secondary_path.text().strip()) if self.folder_mode.currentIndex() else None, self.recursive.isChecked(), bool(self.file_filter.currentIndex()), bool(self.analysis_mode.currentIndex()), self.similarity.value(), self.coverage.value())
        options.video_profile = self.video_profile.currentData()
        options.validate()
        return options

    def start_job(self, fn, completed):
        worker = Worker(fn)
        self.worker = worker
        self.jobs.append(worker)
        worker.progress.connect(self.on_progress)
        worker.completed.connect(completed)
        worker.failed.connect(self.job_failed)
        worker.finished.connect(lambda: self.job_finished(worker))
        self._set_busy(True)
        worker.start()

    def job_finished(self, worker):
        if self.worker is worker:
            self.worker = None
            self._set_busy(False)
        if worker in self.jobs:
            self.jobs.remove(worker)
        worker.deleteLater()

    def _set_busy(self, busy):
        self.settings_action.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.progress_label.setVisible(busy or self.result is None)
        self.scan_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        for widget in self.config_widgets:
            widget.setEnabled(not busy)
            if hasattr(widget, '_picker'):
                widget._picker.setEnabled(not busy)
        self.recalculate.setEnabled(not busy and bool(self.result and self.result.options.similar and (not self.result.cancelled)))
        self.export_button.setEnabled(not busy and self.result is not None)
        self.update_actions()

    def start_scan(self):
        try:
            options = self.options()
        except ValueError as exc:
            QMessageBox.warning(self, tr('Check folders'), str(exc))
            return
        self.clear_selection()
        self.new_scan = True
        self.notice.setText(tr('Scanning. File actions will be available when reading finishes.'))
        self.notice.show()
        self.progress.setValue(0)
        self.start_job(lambda cancel, progress: scan(options, cancel, progress), self.scan_done)

    def scan_done(self, result):
        self.result = result
        self.configure_result_filters()
        names = (tr('Primary: ') if result.options.secondary else tr('Folder: ')) + result.options.primary.name
        if result.options.secondary:
            names += tr('. Secondary: ') + result.options.secondary.name
        self.root_summary.setText(names)
        self.root_summary.setToolTip(str(result.options.primary) + ('\n' + str(result.options.secondary) if result.options.secondary else ''))
        self.root_summary.show()
        self.scan_details_button.setEnabled(True)
        self.checked_keys.clear()
        self.preferred_keepers.clear()
        if self.new_scan:
            self.scope_filter.blockSignals(True)
            self.scope_filter.setCurrentIndex(self.scope_filter.findData(2 if result.options.secondary else 1))
            self.scope_filter.blockSignals(False)
            if result.files and (not result.cancelled):
                self.setup_panel.hide()
                self.setup_toggle.setText(tr('Edit folders and scan options'))
            self.new_scan = False
        self.progress.setRange(0, 100)
        self.progress.setValue(0 if result.cancelled else 100)
        count = len(result.files)
        self.metrics[0].setText(f'{count:,}'.replace(',', '.'))
        self.metrics[1].setText(str(len(result.exact_groups)))
        self.metrics[2].setText(str(len(result.similar_matches)))
        missing = sum((1 for k, f in result.files.items() if f.root == 'secondary' and result.classification(k) in ('Possible duplicate', 'No matches detected')))
        self.metrics[3].setText(str(missing) if result.options.secondary else 'N/A')
        errors = len(result.errors) + sum((bool(f.error or f.video_error) for f in result.files.values()))
        self.incidents_button.setText(tr('Issues ({p0})', p0=f'{errors}'))
        self.incidents_button.setEnabled(errors > 0)
        if result.cancelled:
            text = tr('Scan canceled. Partial results cannot be used to move or remove files. Export them or run another scan.')
        elif errors:
            text = tr('Scan finished with {p0} issues. Review Errors or pending files. Uncertain results are not classified as missing.', p0=f'{errors}')
        elif not count:
            text = tr('No files matched the scan options. Check the folders and file filter.')
        else:
            text = tr('Reviewing secondary files. Select extra copies to move or send to Recycle Bin. Primary copies are kept.') if result.options.secondary else tr('Select extra copies to mark duplicates while keeping a reference in each group.')
        if result.options.similar:
            if result.options.video_profile in ('segments', 'segments_fast'):
                text += tr(' Segment matching allows internal cuts and counts shared content against the longer video.')
                if result.options.video_profile == 'segments_fast':
                    text += ' ' + tr('Quick segment coverage and ranges are estimated from at most 160 captures. Unmatched sections may be missed.')
            else:
                text += tr(' Quick scan estimates coverage from samples.') if result.options.video_profile == 'fast' else tr(' Full scan examines the video timeline.')
        self.notice.setText(text)
        self.notice.setVisible(result.cancelled)
        self.scan_details_button.setToolTip(text)
        self.notice.setToolTip('\n'.join(result.errors))
        self.progress_label.setText(tr('{p0} files, {p1} exact groups, {p2} similar pairs, {p3} issues', p0=f'{count}', p1=f'{len(result.exact_groups)}', p2=f'{len(result.similar_matches)}', p3=f'{errors}'))
        self.populate()

    def recalculate_matches(self):
        if not self.result or not self.result.options.similar:
            return
        result = self.result
        similarity, coverage = (self.similarity.value(), self.coverage.value())
        profile = self.video_profile.currentData()
        family = lambda value: 'dense' if value in ('full', 'segments') else value
        source = result.options.video_profile
        if family(profile) != family(source) and not (profile == 'segments_fast' and family(source) == 'dense'):
            self.notice.setText(tr('The sampling profile changed. Start a new scan to apply it. Existing cached frames will be reused when available.'))
            self.notice.show()
            return

        def calculate(cancel, progress):
            matches = find_similar(list(result.files.values()), similarity, coverage, cancel, progress, mode=profile)
            return matches

        def done(matches):
            result.options.similarity = similarity
            result.options.coverage = coverage
            result.options.video_profile = profile
            result.similar_matches = matches
            self.scan_done(result)
        self.notice.setText(tr('Applying thresholds to existing fingerprints without decoding the videos again.'))
        self.notice.show()
        self.start_job(calculate, done)

    def cancel_current(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.progress_label.setText(tr('Canceling. Waiting for the current operation to finish.'))

    def on_progress(self, phase, current, total, path):
        now = time.monotonic()
        if now - self.last_progress < 0.08 and current != total:
            return
        self.last_progress = now
        self.progress.setRange(0, total if total else 0)
        if total:
            self.progress.setValue(current)
        self.progress_label.setText(tr('{p0}, {p1}{p2}, {p3}', p0=f'{phase}', p1=f'{current}', p2=f"{(f' / {total}' if total else '')}", p3=f'{Path(path).name}'))
        self.progress_label.setToolTip(path)

    def job_failed(self, message):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.notice.setText(message)
        self.notice.show()
        if not message.startswith(tr('Operation canceled')):
            QMessageBox.warning(self, tr('Could not complete the operation'), message)
        if self.result:
            self.populate()
            if any((not f.active for f in self.result.files.values())):
                QTimer.singleShot(150, self.refresh_after_actions)

    def selected_keys(self):
        return list(self.checked_keys)

    def populate(self, *_):
        if not self.result:
            return
        result = self.result
        checked = self.checked_keys
        search = self.search.text().casefold()
        filter_index = self.view_filter.currentData()
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        groups = {k: n + 1 for n, g in enumerate(result.exact_groups) for k in g}
        self.visual_pair_ids = {id(match): f'V{n:03d}' for n, match in enumerate(result.similar_matches, 1)}
        for key, f in result.files.items():
            if not f.active or search not in f.path.casefold():
                continue
            scope = self.scope_filter.currentData()
            if scope == 1 and f.root != 'primary' or (scope == 2 and f.root != 'secondary'):
                continue
            peers = result.exact_peers(key)
            visual = result.visual_peers(key)
            classification = result.classification(key)
            if filter_index == 8 and (not peers) and (not visual):
                continue
            cross_exact = [p for p in peers if p.root == 'primary']
            if filter_index == 1 and (not peers):
                continue
            if filter_index == 2 and (not visual):
                continue
            if filter_index == 3 and (not (f.root == 'secondary' and (not cross_exact) and (classification != 'Error or pending'))):
                continue
            if filter_index == 4 and (not (f.root == 'secondary' and classification == 'No matches detected')):
                continue
            if filter_index in (5, 6):
                role = 'primary' if filter_index == 5 else 'secondary'
                if f.root != role or not (any((p.root == role for p in peers)) or any((p.root == role for p, _ in visual))):
                    continue
            if filter_index == 7 and (not (f.error or f.video_error or (classification == 'Error or pending' and result.display_status(key) != 'No matches (partial comparison)'))):
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = SortItem('')
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            check.setCheckState(Qt.CheckState.Checked if key in checked else Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, key)
            self.table.setItem(row, 0, check)
            best = max((m for _, m in visual), key=lambda m: (m.coverage, m.similarity), default=None)
            name = Path(f.path).name
            relations = []
            relation_count = len(peers) + len(visual)
            # Keep row tooltips bounded even for groups with thousands of copies.
            for peer in peers[:20]:
                relations.append((f'G{groups[key]:03d}', peer))
            for peer, match in visual[:20 - len(relations)]:
                relations.append((self.visual_pair_ids[id(match)], peer))
            match_text = f'{relations[0][0]}: {Path(relations[0][1].path).name}' if relations else tr('No matches')
            if relation_count > 1:
                match_text += tr(' (+{count} more)', count=relation_count - 1)
            match_tooltip = '\n\n'.join(f'{pair}: {peer.path}' for pair, peer in relations)
            if relation_count > len(relations):
                match_tooltip += '\n\n' + tr('{count} additional matches. Select this row to review all matching copies.', count=relation_count - len(relations))
            resolution = f"{f.metadata.get('width', 0)} × {f.metadata.get('height', 0)}" if f.metadata else 'N/A'
            status = result.display_status(key)
            display_status = {'No matches detected': tr('No matches'), 'Error or pending': tr('Error or pending')}.get(status, status)
            values = [name, match_text, self.file_location(f), human_size(f.size), duration_text(f.metadata.get('duration')), resolution, display_status, f'{best.similarity:.0f}% / {best.coverage:.0f}%' if best else 'N/A']
            sorts = [name.casefold(), match_text.casefold(), f.root, f.size, f.metadata.get('duration', 0), f.metadata.get('width', 0) * f.metadata.get('height', 0), classification, best.similarity if best else 0]
            for col, (text, sort) in enumerate(zip(values, sorts), 1):
                item = SortItem(text)
                item.setData(Qt.ItemDataRole.UserRole + 1, sort)
                detail = f.error or f.video_error or result.comparison_note(key) or (tr('This file was read, but other errors prevent completing the comparison. Review Issues. No absence is confirmed.') if status == 'Comparison incomplete' else '')
                item.setToolTip(match_tooltip if col == 2 and relations else f.path + '\n' + tr(status) + ('\n' + detail if detail else ''))
                if col == 7:
                    item.setText(tr(text))
                    item.setForeground(status_color(classification))
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self.update_actions()
        self.comparison_toggle.setEnabled(bool(self.table.rowCount()))
        if self.table.rowCount():
            self.table.selectRow(0)
        else:
            self.left_preview.set_record(None)
            self.right_preview.set_record(None)
            self.peer_combo.clear()
            self.peer_entries = []
            self.current_key = None
            self.preview_scroll.hide()
            self.comparison_toggle.setText(tr('Show comparison'))
            if self.thumb_worker:
                self.thumb_worker.cancel.set()

    def update_actions(self, *_):
        if _ and isinstance(_[0], QTableWidgetItem) and (_[0].column() == 0):
            item = _[0]
            key = item.data(Qt.ItemDataRole.UserRole)
            if item.checkState() == Qt.CheckState.Checked:
                self.checked_keys.add(key)
            else:
                self.checked_keys.discard(key)
        count = len(self.selected_keys()) if hasattr(self, 'table') else 0
        records = [self.result.files[k] for k in self.checked_keys] if self.result else []
        primary = sum((f.root == 'primary' for f in records))
        secondary = count - primary
        self.selected_label.setText(tr('{p0} selected', p0=f'{count}') + (tr(', {p0}', p0=f'{human_size(sum((f.size for f in records)))}') if count else ''))
        enabled = bool(count and self.result and self.result.exact_complete and (not self.result.cancelled) and (not self.worker))
        protected = bool(primary and self.result and self.result.options.secondary and (not self.unlock.isChecked()))
        if protected:
            enabled = False
        self.move_button.setEnabled(enabled)
        self.trash_button.setEnabled(enabled)
        self.clear_button.setEnabled(count > 0)
        self.select_all_button.setEnabled(bool(self.result and (not self.worker) and self.table.rowCount()))
        self.select_copies_button.setEnabled(bool(self.result and (not self.worker) and self.table.rowCount()))
        two = bool(self.result and self.result.options.secondary)
        self.transfer_button.setVisible(two)
        self.transfer_button.setText(tr('Move to primary') if secondary or not primary else tr('Move to secondary'))
        self.transfer_button.setEnabled(enabled and bool(primary) != bool(secondary))
        if self.worker:
            hint = tr('A scan or file operation is running. You can cancel pending work.')
        elif protected:
            hint = tr('{p0} selected primary files are protected. Uncheck them or allow primary file removal.', p0=f'{primary}')
        elif count and self.result and (not self.result.exact_complete):
            hint = tr('File actions are blocked because reading is incomplete. Review the issues and scan again.')
        elif count:
            hint = (tr('Selected files: {p0} secondary and {p1} primary.', p0=f'{secondary}', p1=f'{primary}') if two else tr('You are managing {p0} files in this folder.', p0=f'{count}')) + tr(' You will be asked to confirm before files are removed.')
        else:
            hint = tr('Select extra copies keeps references. Select all marks every visible file.')
        hidden = len(self.checked_keys - set(self.visible_keys()))
        if hidden:
            hint += tr(' {p0} selected files are outside the current filter.', p0=f'{hidden}')
        self.selection_hint.setText(hint)
        self.selection_hint.setVisible(bool(protected or hidden or (count and self.result and not self.result.exact_complete)))
        keepers = {keeper for key, keeper in self.preferred_keepers.items() if key in self.checked_keys and keeper not in self.checked_keys}
        self.table.blockSignals(True)
        for item in [self.table.item(row, 0) for row in range(self.table.rowCount())]:
            key = item.data(Qt.ItemDataRole.UserRole)
            item.setText(tr('Remove') if key in self.checked_keys else tr('Keep') if key in keepers else '')
            item.setToolTip(tr('Checked files are selected for removal. A highlighted row only opens the comparison.'))
        self.table.blockSignals(False)
        self.update_preview_decisions()

    def clear_selection(self):
        self.preferred_keepers.clear()
        self.checked_keys.clear()
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.update_actions()

    def visible_keys(self):
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in range(self.table.rowCount())]

    def set_checked(self, keys):
        self.checked_keys = set(keys)
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in self.checked_keys else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.update_actions()

    def select_all_visible(self):
        self.set_checked(self.visible_keys())

    def toggle_all_visible(self):
        visible = set(self.visible_keys())
        self.set_checked(set() if visible and visible.issubset(self.checked_keys) else visible)

    def select_redundant(self):
        if self.result:
            self.set_checked(redundant_keys(self.result, self.visible_keys(), self.unlock.isChecked()))

    def transfer_selected(self):
        if not self.result or not self.checked_keys:
            return
        roles = {self.result.files[k].root for k in self.checked_keys}
        if roles == {'secondary'}:
            self.prepare_action('move', str(self.result.options.primary))
        elif roles == {'primary'} and self.result.options.secondary:
            self.prepare_action('move', str(self.result.options.secondary))

    def show_details(self):
        row = self.table.currentRow()
        if row < 0 or not self.result:
            return
        self.preview_scroll.show()
        self.comparison_toggle.setText(tr('Hide comparison'))
        if not self.comparison_sized:
            QTimer.singleShot(0, self.size_comparison)
        key = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.current_key = key
        self.peer_combo.blockSignals(True)
        self.peer_combo.clear()
        self.peer_entries = []
        for peer in self.result.exact_peers(key):
            self.peer_entries.append((peer, None))
            self.peer_combo.addItem(tr('{p0}, {p1}, exact copy', p0=f'{Path(peer.path).name}', p1=self.file_location(peer)))
            self.peer_combo.setItemData(self.peer_combo.count() - 1, peer.path, Qt.ItemDataRole.ToolTipRole)
        for peer, match in self.result.visual_peers(key):
            self.peer_entries.append((peer, match))
            self.peer_combo.addItem(self.visual_pair_ids[id(match)] + ': ' + tr('{p0}, {p1}, {p2}% visual, {p3}%{p4} coverage', p0=f'{Path(peer.path).name}', p1=self.file_location(peer), p2=f'{match.similarity:.1f}', p3=f'{match.coverage:.1f}', p4=f"{(tr(' estimated') if match.estimated else '')}"))
            self.peer_combo.setItemData(self.peer_combo.count() - 1, peer.path, Qt.ItemDataRole.ToolTipRole)
        if not self.peer_entries:
            self.peer_combo.addItem(tr('No matching copy to compare'))
        self.peer_combo.blockSignals(False)
        preferred = self.preferred_keepers.get(key)
        if preferred:
            self.peer_combo.blockSignals(True)
            self.peer_combo.setCurrentIndex(next((i for i, (peer, _) in enumerate(self.peer_entries) if peer.key == preferred), 0))
            self.peer_combo.blockSignals(False)
        self.show_peer()

    def toggle_comparison(self):
        if self.preview_scroll.isHidden():
            self.show_details()
        else:
            self.preview_scroll.hide()
            self.comparison_toggle.setText(tr('Show comparison'))

    def size_comparison(self):
        if self.comparison_sized or self.preview_scroll.isHidden():
            return
        if self.results_split.orientation() == Qt.Orientation.Horizontal:
            available = self.results_split.width()
            preview = min(660, max(400, int(available * 0.36)))
            self.results_split.setSizes([max(460, available - preview), preview])
        else:
            available = self.results_split.height()
            preview = min(330, int(available * 0.45))
            self.results_split.setSizes([max(160, available - preview), preview])
        self.comparison_sized = True

    def show_peer(self, *_):
        if not self.current_key or not self.result:
            return
        f = self.result.files[self.current_key]
        i = self.peer_combo.currentIndex()
        peer, match = self.peer_entries[i] if 0 <= i < len(self.peer_entries) else (None, None)
        for card in (self.left_preview, self.right_preview):
            card.single_folder = not self.result.options.secondary
        self.left_preview.set_record(f)
        self.right_preview.set_record(peer)
        if match:
            spans = match.spans
            if match.a != f.key:
                spans = [[s[2], s[3], s[0], s[1]] for s in spans]
            self.evidence.setText(tr('Visual similarity {p0}%. {p1}Coverage {p2}% of the longer video. ', p0=f'{match.similarity:.1f}', p1=f"{(tr('estimated ') if match.estimated else '')}", p2=f'{match.coverage:.1f}') + tr('Segments: ') + '. '.join((f'{duration_text(s[0])}–{duration_text(s[1])} ↔ {duration_text(s[2])}–{duration_text(s[3])}' for s in spans[:4])) + tr('. Audio was not compared.'))
            if self.result.options.video_profile in ('segments', 'segments_fast'):
                self.evidence.setText(self.evidence.text() + ' ' + tr('These videos share sections and may contain different content. Review both before selecting a file for removal.'))
            span = max(spans, key=lambda s: s[1] - s[0], default=[0,f.metadata.get('duration',0),0,peer.metadata.get('duration',0)])
            times = [[span[0] + (span[1] - span[0]) * q for q in (0.15, 0.5, 0.85)], [span[2] + (span[3] - span[2]) * q for q in (0.15, 0.5, 0.85)]]
        else:
            self.evidence.setText(tr('Identical copy confirmed with a full SHA-256 hash.') if peer else f.error or f.video_error or self.result.comparison_note(f.key) or (tr('This file was read, but other errors prevent completing the comparison. Review Issues. No absence is confirmed.') if self.result.display_status(f.key) == 'Comparison incomplete' else tr(self.result.display_status(f.key))))
            times = [[record.metadata.get('duration', 0) * q for q in (0.15, 0.5, 0.85)] if record else [] for record in (f, peer)]
        self.load_thumbnails([f, peer], times)
        self.update_preview_decisions()

    def update_preview_decisions(self):
        if not hasattr(self, 'left_preview'):
            return
        left, right = self.left_preview, self.right_preview
        pair = bool(left.record and right.record)
        for card, other in [(left,right),(right,left)]:
            valid = bool(pair and card.record.active and other.record.active and not self.worker)
            card.keep.setEnabled(valid)
            card.remove.setEnabled(valid)
            if card.record:
                if card.record.key in self.checked_keys:
                    card.heading.setText(tr('Copy selected for removal'))
                    card.decision.setText(tr('Selected for removal. Confirmation is still required.'))
                elif any(key in self.checked_keys and keeper == card.record.key for key, keeper in self.preferred_keepers.items()):
                    card.heading.setText(tr('Copy to keep'))
                    card.decision.setText(tr('This copy will be kept.'))
                else:
                    card.heading.setText(tr('File under review') if card is left else tr('Matching copy'))
                    card.decision.clear()

    def choose_preview(self, keep_left):
        active_key = self.current_key
        vertical_position = self.table.verticalScrollBar().value()
        horizontal_position = self.table.horizontalScrollBar().value()
        keep = self.left_preview.record if keep_left else self.right_preview.record
        remove = self.right_preview.record if keep_left else self.left_preview.record
        if not keep or not remove or self.worker:
            return
        if self.result.options.secondary and remove.root == 'primary' and not self.unlock.isChecked():
            answer = QMessageBox.question(self, tr('Unlock primary folder'),
                tr('You chose to keep the other copy and remove a primary file. Unlock primary for this session?'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.unlock.setChecked(True)
        keys = set(self.checked_keys)
        keys.discard(keep.key)
        keys.add(remove.key)
        # A visual match is not transitive. Keep previous dependents instead of
        # silently replacing their reference with a video they were not paired with.
        restored = {key for key in keys if self.preferred_keepers.get(key) == remove.key}
        keys.difference_update(restored)
        for group in self.result.exact_groups:
            active = {key for key in group if self.result.files[key].active}
            if active and active <= keys:
                reference = min(active - {remove.key}, default=remove.key)
                keys.discard(reference)
                restored.add(reference)
        # Bulk/manual checkbox selections may not have a reviewed keeper yet.
        # Do not leave those files selected if this choice removes their only match.
        for key in sorted(keys - {remove.key}):
            matches = {peer.key for peer in self.result.exact_peers(key)}
            matches.update(peer.key for peer, _ in self.result.visual_peers(key))
            if matches and not matches - keys:
                keys.discard(key)
                restored.add(key)
        for key in restored | {keep.key}:
            self.preferred_keepers.pop(key, None)
        if remove.key in keys:
            self.preferred_keepers[remove.key] = keep.key
        self.set_checked(keys)
        if active_key in self.visible_keys():
            self.table.setCurrentCell(self.visible_keys().index(active_key), 1)
        self.table.setFocus(Qt.FocusReason.OtherFocusReason)
        self.table.verticalScrollBar().setValue(vertical_position)
        self.table.horizontalScrollBar().setValue(horizontal_position)
        if restored:
            self.notice.setText(tr('{count} earlier selections were kept because their reference is now selected for removal. Review them before choosing another reference.', count=len(restored)))
            self.notice.show()

    def load_thumbnails(self, records, times):
        if self.thumb_worker:
            self.thumb_worker.cancel.set()
        self.preview_generation += 1
        generation = self.preview_generation
        for side, card in enumerate([self.left_preview, self.right_preview]):
            overview = list(times[side])
            if overview and records[side] and records[side].is_video:
                span = (overview[-1] - overview[0]) / 0.7 if len(overview) >= 3 else records[side].metadata.get('duration',0)
                start = overview[0] - span * 0.15
                extra = [start + span * q / (self.preferences.gallery_frames*2) for q in range(1,self.preferences.gallery_frames*2)]
                for at in extra:
                    if len(overview) >= self.preferences.gallery_frames:
                        break
                    if all(abs(at-existing) > span*0.02 for existing in overview):
                        overview.append(max(0,at))
            card.prepare(overview)
            card.loading = True

        def get(cancel, _):
            images = []
            for side, record in enumerate(records):
                if record and record.is_video and record.active:
                    for i, at in enumerate(times[side]):
                        try:
                            images.append((side, i, thumbnail(record.path, at, cancel), at))
                        except (OSError, RuntimeError):
                            images.append((side, i, b'', at))
            return images
        worker = Worker(get)
        self.thumb_worker = worker
        self.jobs.append(worker)

        def done(images):
            if generation == self.preview_generation:
                for side, i, raw, at in images:
                    (self.left_preview if side == 0 else self.right_preview).set_image(i, raw, at)
                self.left_preview.loading = self.right_preview.loading = False
        worker.completed.connect(done)
        worker.finished.connect(lambda: self.thumbnail_finished(worker))
        worker.start()

    def more_frames(self, card):
        if card.loading or not card.record or not card.record.is_video or len(card.thumbs) >= len(card.times):
            return
        generation = self.preview_generation
        start = len(card.thumbs)
        targets = list(enumerate(card.times[start:start+3], start))
        card.loading = True
        card.add_slots(len(targets))
        card.more.setVisible(len(card.thumbs) < len(card.times))
        record = card.record
        def get(cancel, _):
            frames = []
            for index, at in targets:
                try:
                    frames.append((index, thumbnail(record.path, at, cancel), at))
                except (OSError, RuntimeError):
                    frames.append((index,b'',at))
            return frames
        worker = Worker(get)
        self.jobs.append(worker)
        def done(frames):
            if generation == self.preview_generation:
                for index, raw, at in frames:
                    card.set_image(index,raw,at)
                card.loading = False
        worker.completed.connect(done)
        worker.finished.connect(lambda: self.thumbnail_finished(worker))
        worker.start()

    def expand_frame(self, card, index):
        if not card.record or not card.record.is_video or not card.times:
            return
        dialog = FrameViewer(card.record, card.times, index, self)
        self.lightbox = dialog
        def load(index):
            if self.lightbox_worker:
                self.lightbox_worker.cancel.set()
            worker = Worker(lambda cancel,_: thumbnail(card.record.path,card.times[index],cancel,width=1280,height=720))
            self.lightbox_worker = worker
            self.jobs.append(worker)
            worker.completed.connect(lambda raw: dialog.set_image(raw) if self.lightbox is dialog and dialog.isVisible() and dialog.index == index else None)
            worker.finished.connect(lambda: self.thumbnail_finished(worker))
            worker.start()
        dialog.frame_changed.connect(load)
        dialog.closing.connect(lambda: self.lightbox_worker.cancel.set() if self.lightbox_worker else None)
        dialog.exec()
        self.lightbox = None

    def thumbnail_finished(self, worker):
        if self.thumb_worker is worker:
            self.thumb_worker = None
        if worker in self.jobs:
            self.jobs.remove(worker)
        worker.deleteLater()

    def unlock_primary(self, checked):
        if checked and QMessageBox.question(self, tr('Unlock primary folder'), tr('You will be able to move primary files and send them to Recycle Bin for this session. Unlock primary?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.unlock.setChecked(False)

    def move_selected(self):
        if not self.result:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Choose destination'))
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(tr('Move selected files to:'), 'section'))
        choices = QComboBox()
        choices.addItem(tr('Review folder or another folder'), 'custom')
        choices.addItem(tr('Primary folder'), str(self.result.options.primary))
        if self.result.options.secondary:
            choices.addItem(tr('Secondary folder'), str(self.result.options.secondary))
        layout.addWidget(choices)
        layout.addWidget(label(tr('Relative subfolders are preserved. A suffix is added when names conflict.'), 'muted', True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        destination = choices.currentData()
        if destination == 'custom':
            destination = QFileDialog.getExistingDirectory(self, tr('Choose a review or destination folder'))
        if destination:
            self.prepare_action('move', destination)

    def trash_selected(self):
        self.prepare_action('trash')

    def keeper_dialog(self, keys):
        selected = set(keys)
        entries = []
        for key in keys:
            if self.result.exact_peers(key):
                continue
            matches = self.result.visual_peers(key)
            peers = [(p, m) for p, m in matches if p.key not in selected and not p.error and p.unchanged()]
            if not peers:
                record = self.result.files[key]
                if matches and all(p.key in selected for p, _ in matches):
                    raise ValueError(tr('All matches for "{name}" are selected for removal. Keep one of these files first:\n{paths}', name=Path(record.path).name, paths='\n'.join(p.path for p, _ in matches)))
                raise ValueError(tr('No available matching copy remains for "{name}". Scan again if a file changed. Files without matches can be moved to another folder.', name=Path(record.path).name))
            if self.preferred_keepers.get(key) in {p.key for p, _ in peers}:
                continue
            peers.sort(key=lambda item: (item[0].key != self.preferred_keepers.get(key), item[0].root != 'primary', item[0].path.lower()))
            entries.append((key, peers))
        if not entries:
            return (None, {})
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Review copies to keep'))
        dialog.resize(1000, 460)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(tr('Choose which copy to keep for each similar video'), 'section'))
        layout.addWidget(label(tr('Primary references appear first. These are visual matches. Audio and editing may differ.') if self.result.options.secondary else tr('These are visual matches. Audio and editing may differ.'), 'muted', True))
        table = QTableWidget(len(entries), 2)
        table.setHorizontalHeaderLabels([tr('Video to remove'), tr('Video to keep')])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(48)
        combos = {}
        for row, (key, peers) in enumerate(entries):
            record = self.result.files[key]
            role = self.file_location(record)
            item = QTableWidgetItem(f'{Path(record.path).name}\n{role}, {Path(record.path).parent}')
            item.setToolTip(record.path)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            table.setItem(row, 0, item)
            combo = QComboBox()
            for peer, match in peers:
                combo.addItem(tr('{p0}, {p1}, {p2}', p0=f'{Path(peer.path).name}', p1=self.file_location(peer), p2=f'{Path(peer.path).parent}'), peer.key)
                combo.setItemData(combo.count() - 1, peer.path, Qt.ItemDataRole.ToolTipRole)
            combo.setToolTip(peers[0][0].path)
            table.setCellWidget(row, 1, combo)
            combos[key] = combo
        layout.addWidget(table)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        controls.addButton(tr('Keep these reference copies'), QDialogButtonBox.ButtonRole.AcceptRole)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        return (dialog, combos)

    def choose_keepers(self, keys):
        dialog, combos = self.keeper_dialog(keys)
        if dialog is None:
            return dict(self.preferred_keepers)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return {**self.preferred_keepers, **{key: combo.currentData() for key, combo in combos.items()}}

    def prepare_action(self, kind, destination=None):
        if not self.result or self.worker:
            return
        keys = self.selected_keys()
        try:
            keepers = self.choose_keepers(keys) if kind == 'trash' else dict(self.preferred_keepers)
            if keepers is None:
                return
            actions = plan_actions(self.result, keys, kind, destination, self.unlock.isChecked(), keepers)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, tr('Review selection'), str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Confirm move') if kind == 'move' else tr('Confirm sending to Recycle Bin'))
        dialog.resize(820, 460)
        layout = QVBoxLayout(dialog)
        total_size = sum((self.result.files[a.key].size for a in actions))
        layout.addWidget(label(tr('{p0} files, {p1}', p0=f'{len(actions)}', p1=f'{human_size(total_size)}'), 'section'))
        layout.addWidget(label(tr('Review the files and the copies that will be kept before confirming.'), 'muted', True))
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        lines = []
        for action in actions:
            lines.append(self.result.files[action.key].path)
            lines.append(f'  → {action.destination}' if kind == 'move' else tr('  To Recycle Bin'))
            if action.collision:
                lines.append(tr('  Name changed to avoid a conflict. No file is overwritten.'))
            if action.keeper:
                lines.append(tr('  Kept copy: {p0}', p0=f'{self.result.files[action.keeper].path}'))
            lines.append('')
        preview.setPlainText('\n'.join(lines))
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        confirm = buttons.addButton(tr('Confirm move') if kind == 'move' else tr('Send to Recycle Bin'), QDialogButtonBox.ButtonRole.AcceptRole)
        confirm.setObjectName('primary' if kind == 'move' else 'danger')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.result
        self.clear_selection()
        if self.thumb_worker:
            self.thumb_worker.cancel.set()
        self.start_job(lambda cancel, progress: execute_actions(result, actions, kind, cancel, progress), self.actions_done)

    def actions_done(self, outcomes):
        success = sum((o['ok'] for o in outcomes))
        failed = len(outcomes) - success
        self.populate()
        message = tr('Processed {p0} files. {p1} errors.', p0=f'{success}', p1=f'{failed}')
        if failed:
            message += '\n\n' + '\n'.join((f"{o['source']}: {o.get('error', '')}" for o in outcomes if not o['ok']))
        if any((o.get('log_error') for o in outcomes)):
            message += '\nNo se pudo escribir parte del registro de operaciones.'
        message += '\n\n' + tr('The folders will be scanned again to refresh the results.')
        QMessageBox.information(self, tr('Operation finished'), message)
        QTimer.singleShot(150, self.refresh_after_actions)

    def refresh_after_actions(self):
        if self.worker:
            QTimer.singleShot(100, self.refresh_after_actions)
            return
        if self.result and (not self.close_pending):
            options = self.result.options
            self.start_job(lambda cancel, progress: scan(options, cancel, progress), self.scan_done)

    def export_report(self):
        if not self.result:
            return
        path, chosen = QFileDialog.getSaveFileName(self, tr('Export report'), 'comparacion.html', tr('HTML report (*.html);;CSV for Excel (*.csv)'))
        if not path:
            return
        if not Path(path).suffix:
            path += '.csv' if 'CSV' in chosen else '.html'
        try:
            if Path(path).suffix.lower() == '.csv':
                export_csv(self.result, path)
            else:
                export_html(self.result, path)
            self.notice.setText(tr('Report saved to {p0}', p0=f'{path}'))
            self.notice.show()
        except OSError as exc:
            QMessageBox.warning(self, tr('Export report'), str(exc))

    def show_incidents(self):
        if not self.result:
            return
        lines = list(self.result.errors)
        for record in self.result.files.values():
            if record.error or record.video_error:
                lines.append(record.path + '\n' + '\n'.join((x for x in (record.error, record.video_error) if x)))
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Scan issues'))
        dialog.resize(800, 460)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(tr('These files or folders need review before they can be classified as missing.'), 'muted', True))
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText('\n\n'.join(lines) or tr('No issues found.'))
        layout.addWidget(details)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        dialog.exec()

    def closeEvent(self, event):
        running = [job for job in self.jobs if job.isRunning()]
        if running:
            if not self.close_pending and self.worker and (QMessageBox.question(self, tr('Close application'), tr('An operation is running. Cancel pending work and close? Completed actions will be kept.'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes):
                event.ignore()
                return
            self.close_pending = True
            for job in running:
                job.cancel.set()
            event.ignore()
            QTimer.singleShot(200, self.close)
        else:
            if self.column_width_timer.isActive():
                self.persist_column_widths()
            event.accept()

def run():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(tr('Video Duplicate Finder'))
    app.setOrganizationName('ComparadorLocal')
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    return app.exec()
