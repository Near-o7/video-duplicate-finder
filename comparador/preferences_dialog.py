from dataclasses import replace
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QSpinBox, QLabel, QDialogButtonBox, QTabWidget, QWidget, QPushButton, QGridLayout, QScrollArea
from .i18n import tr
from .settings import RESULT_COLUMNS, REQUIRED_COLUMNS


class PreferencesDialog(QDialog):
    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.original = preferences
        self.setWindowTitle(tr("Settings"))
        self.resize(600, 550)
        layout = QVBoxLayout(self)
        note = QLabel(tr("Theme and language apply immediately after saving. Scan defaults apply to new comparisons. Folder paths are not saved."))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        general = QWidget()
        form = QFormLayout()
        general.setLayout(form)
        self.tabs.addTab(general, tr('General'))
        self.language = QComboBox()
        for text, value in [("System", "system"), ("Español", "es"), ("English", "en")]:
            self.language.addItem(tr(text), value)
        self.language.setCurrentIndex(self.language.findData(preferences.language))
        form.addRow(tr("Language"), self.language)
        self.theme = QComboBox()
        for text, value in [("System", "system"), ("Light", "light"), ("Dark", "dark")]:
            self.theme.addItem(tr(text), value)
        self.theme.setCurrentIndex(self.theme.findData(preferences.theme))
        form.addRow(tr("Appearance"), self.theme)
        self.gallery = QComboBox()
        self.gallery.addItem("12", 12)
        self.gallery.addItem("24", 24)
        self.gallery.setCurrentIndex(self.gallery.findData(preferences.gallery_frames))
        form.addRow(tr("Frames per gallery"), self.gallery)
        self.comparison_position = QComboBox()
        self.comparison_position.addItem(tr('To the right of the table'), 'right')
        self.comparison_position.addItem(tr('Below the table'), 'below')
        self.comparison_position.setCurrentIndex(self.comparison_position.findData(preferences.comparison_position))
        form.addRow(tr('Comparison position'), self.comparison_position)
        scan = QWidget()
        form = QFormLayout(scan)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scan)
        self.tabs.addTab(scroll, tr('Scan defaults'))
        self.two_folders = QCheckBox(tr("Compare primary and secondary by default"))
        self.two_folders.setChecked(preferences.two_folders)
        form.addRow(self.two_folders)
        self.recursive = QCheckBox(tr("Include subfolders"))
        self.recursive.setChecked(preferences.recursive)
        form.addRow(self.recursive)
        self.videos_only = QCheckBox(tr("Videos only"))
        self.videos_only.setChecked(preferences.videos_only)
        form.addRow(self.videos_only)
        self.similar = QCheckBox(tr("Find visually similar videos"))
        self.similar.setChecked(preferences.similar)
        form.addRow(self.similar)
        self.profile = QComboBox()
        self.profile.addItem(tr("Quick scan"), "fast")
        self.profile.addItem(tr("Full scan"), "full")
        self.profile.setCurrentIndex(self.profile.findData(preferences.video_profile))
        form.addRow(tr("Default video profile"), self.profile)
        self.similarity = QSpinBox()
        self.similarity.setRange(70, 99)
        self.similarity.setSuffix(" %")
        self.similarity.setValue(preferences.similarity)
        form.addRow(tr("Minimum visual similarity"), self.similarity)
        self.coverage = QSpinBox()
        self.coverage.setRange(50, 100)
        self.coverage.setSuffix(" %")
        self.coverage.setValue(preferences.coverage)
        form.addRow(tr("Minimum content coverage"), self.coverage)
        columns = QWidget()
        column_layout = QVBoxLayout(columns)
        explanation = QLabel(tr('Choose which columns appear in the result list. File and removal selection always remain visible.'))
        explanation.setWordWrap(True)
        column_layout.addWidget(explanation)
        grid = QGridLayout()
        self.column_checks = {}
        for index, (key, title) in enumerate(RESULT_COLUMNS):
            check = QCheckBox(tr(title))
            check.setChecked(key in preferences.visible_columns)
            check.setEnabled(key not in REQUIRED_COLUMNS)
            self.column_checks[key] = check
            grid.addWidget(check, index // 2, index % 2)
        column_layout.addLayout(grid)
        self.restore_columns = QPushButton(tr('Show all columns'))
        self.restore_columns.clicked.connect(self.show_all_columns)
        column_layout.addWidget(self.restore_columns)
        self.reset_widths = QPushButton(tr('Reset column widths'))
        self.reset_widths.clicked.connect(self.reset_column_widths)
        column_layout.addWidget(self.reset_widths)
        self.width_note = QLabel(tr('Default widths will apply after saving.'))
        self.width_note.setWordWrap(True)
        self.width_note.hide()
        column_layout.addWidget(self.width_note)
        self.saved_widths = dict(preferences.column_widths)
        column_layout.addStretch()
        self.tabs.addTab(columns, tr('Result columns'))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)

    def show_all_columns(self):
        for check in self.column_checks.values():
            check.setChecked(True)

    def reset_column_widths(self):
        self.saved_widths = {}
        self.width_note.show()

    def preferences(self):
        return replace(self.original, language=self.language.currentData(), theme=self.theme.currentData(),
                       two_folders=self.two_folders.isChecked(), recursive=self.recursive.isChecked(),
                       videos_only=self.videos_only.isChecked(), similar=self.similar.isChecked(),
                       video_profile=self.profile.currentData(), similarity=self.similarity.value(),
                       coverage=self.coverage.value(), gallery_frames=self.gallery.currentData(),
                       comparison_position=self.comparison_position.currentData(),
                       column_widths=dict(self.saved_widths),
                       visible_columns=[key for key, check in self.column_checks.items() if check.isChecked()])
