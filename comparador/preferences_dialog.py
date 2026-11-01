from dataclasses import replace
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QSpinBox, QLabel, QDialogButtonBox
from .i18n import tr


class PreferencesDialog(QDialog):
    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.original = preferences
        self.setWindowTitle(tr("Settings"))
        self.resize(560, 560)
        layout = QVBoxLayout(self)
        note = QLabel(tr("Theme and language apply immediately after saving. Scan defaults apply to new comparisons. Folder paths are not saved."))
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
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
        self.gallery = QComboBox()
        self.gallery.addItem("12", 12)
        self.gallery.addItem("24", 24)
        self.gallery.setCurrentIndex(self.gallery.findData(preferences.gallery_frames))
        form.addRow(tr("Frames per gallery"), self.gallery)
        layout.addLayout(form)
        layout.addStretch()
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)

    def preferences(self):
        return replace(self.original, language=self.language.currentData(), theme=self.theme.currentData(),
                       two_folders=self.two_folders.isChecked(), recursive=self.recursive.isChecked(),
                       videos_only=self.videos_only.isChecked(), similar=self.similar.isChecked(),
                       video_profile=self.profile.currentData(), similarity=self.similarity.value(),
                       coverage=self.coverage.value(), gallery_frames=self.gallery.currentData())
