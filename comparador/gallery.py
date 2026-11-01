from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget, QDialog, QSizePolicy
from .i18n import tr
from .models import human_size, duration_text
from .appearance import icon


class FrameLabel(QLabel):
    activated = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mousePressEvent(event)


class PreviewCard(QFrame):
    keep_requested = Signal()
    remove_requested = Signal()
    more_requested = Signal()
    frame_requested = Signal(int)

    def __init__(self, heading):
        super().__init__()
        self.setObjectName("detail")
        self.record = None
        self.times = []
        self.images = {}
        self.loading = False
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 10, 12, 10)
        self.header = QHBoxLayout()
        self.heading = QLabel(heading)
        self.heading.setObjectName("step")
        self.name = QLabel()
        self.name.setObjectName("section")
        self.name.setMinimumWidth(0)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.name.setWordWrap(True)
        self.header.addWidget(self.name, 1)
        self.header.addWidget(self.heading)
        layout.addLayout(self.header)
        self.path = QLabel()
        self.path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.path.setWordWrap(True)
        self.path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path.setMaximumHeight(44)
        layout.addWidget(self.path)
        self.meta = QLabel()
        self.meta.setObjectName("muted")
        layout.addWidget(self.meta)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFixedHeight(128)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.film = QWidget()
        self.strip = QHBoxLayout(self.film)
        self.strip.setContentsMargins(0, 0, 0, 0)
        self.strip.setSpacing(8)
        self.scroll.setWidget(self.film)
        layout.addWidget(self.scroll)
        self.thumbs = []
        self.cells = []
        self.more = QPushButton(tr("More frames"))
        self.more.clicked.connect(self.more_requested.emit)
        self.strip.addWidget(self.more)
        self.scroll.horizontalScrollBar().valueChanged.connect(self._scrolled)
        controls = QHBoxLayout()
        self.open = QPushButton(icon("play"), tr("Open"))
        self.folder = QPushButton(icon("folder"), tr("Show folder"))
        controls.addWidget(self.open)
        controls.addWidget(self.folder)
        controls.addStretch()
        layout.addLayout(controls)
        decisions = QHBoxLayout()
        self.keep = QPushButton(tr("Keep this copy"))
        self.keep.setIcon(icon("select"))
        self.remove = QPushButton(tr("Select for removal"))
        decisions.addWidget(self.keep, 1)
        decisions.addWidget(self.remove, 1)
        layout.addLayout(decisions)
        self.decision = QLabel()
        self.decision.setWordWrap(True)
        self.decision.setObjectName("step")
        layout.addWidget(self.decision)
        self.keep.clicked.connect(self.keep_requested.emit)
        self.remove.clicked.connect(self.remove_requested.emit)
        self.open.clicked.connect(self.open_file)
        self.folder.clicked.connect(self.open_folder)
        self.set_record(None)

    def set_compact(self, compact):
        self.compact = compact
        self.name.setWordWrap(not compact)
        self.scroll.setFixedHeight(94 if compact else 128)
        self.path.setMaximumHeight(22 if compact else 44)
        self.decision.setVisible(not compact)
        self.layout().setContentsMargins(10, 6, 10, 6)
        for thumb in self.thumbs:
            thumb.setFixedHeight(60 if compact else 85)

    def add_slots(self, count):
        for _ in range(count):
            index = len(self.thumbs)
            cell = QWidget()
            column = QVBoxLayout(cell)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            thumb = FrameLabel(tr("Loading..."))
            thumb.setObjectName("thumb")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setFixedHeight(60 if getattr(self, 'compact', False) else 85)
            thumb.setCursor(Qt.CursorShape.PointingHandCursor)
            thumb.activated.connect(lambda i=index: self.frame_requested.emit(i))
            column.addWidget(thumb)
            time_label = QLabel(duration_text(self.times[index]) if index < len(self.times) else "")
            time_label.setObjectName("muted")
            column.addWidget(time_label)
            self.strip.insertWidget(self.strip.count() - 1, cell)
            self.thumbs.append(thumb)
            self.cells.append(cell)
        self._size_cells()

    def prepare(self, times):
        self.times = times
        for index, cell in enumerate(self.cells):
            cell.layout().itemAt(1).widget().setText(duration_text(times[index]) if index < len(times) else "")
        self.more.setVisible(bool(self.record and self.record.is_video and len(self.thumbs) < len(times)))

    def _size_cells(self):
        width = max(110, (self.scroll.viewport().width() - 18) // 3)
        for cell in self.cells:
            cell.setFixedWidth(width)
        for index, (raw, at) in list(self.images.items()):
            self.set_image(index, raw, at)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._size_cells()
        self._elide_labels()

    def _elide_labels(self):
        if getattr(self, 'compact', False) and self.record:
            for widget, text in [(self.path, self._path_text), (self.name, self._name_text)]:
                widget.setText(widget.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, max(1,widget.width())))

    def _scrolled(self, value):
        bar = self.scroll.horizontalScrollBar()
        if bar.maximum() > 0 and value >= bar.maximum() - 12 and not self.loading and self.more.isVisible():
            self.more_requested.emit()

    def set_record(self, record):
        from pathlib import Path
        self.record = record
        self.images.clear()
        self.times = []
        self.loading = False
        for cell in self.cells:
            self.strip.removeWidget(cell)
            cell.deleteLater()
        self.cells, self.thumbs = [], []
        self.add_slots(3)
        self.open.setEnabled(bool(record and record.active))
        self.folder.setEnabled(bool(record))
        self.keep.setEnabled(False)
        self.remove.setEnabled(False)
        self.decision.clear()
        self.more.hide()
        if record:
            self._name_text = Path(record.path).name
            self.name.setText(self._name_text)
            self.name.setToolTip(record.path)
            role = tr("This folder") if getattr(self, "single_folder", False) else tr("Primary") if record.root == "primary" else tr("Secondary")
            self._path_text = role + ": " + str(Path(record.path).parent)
            self.path.setText(self._path_text)
            self.path.setToolTip(record.path)
            data = record.metadata
            self.meta.setText(", ".join([human_size(record.size), duration_text(data.get("duration")),
                f"{data.get('width',0)} x {data.get('height',0)}" if data else tr("No video metadata")]))
            self._elide_labels()
        else:
            self.name.setText(tr("No file selected"))
            self.path.clear()
            self.meta.clear()
        for thumb in self.thumbs:
            thumb.setText(tr("Loading...") if record and record.is_video else tr("No preview"))

    def set_image(self, index, raw, timestamp):
        if index >= len(self.thumbs):
            return
        self.images[index] = (raw, timestamp)
        pix = QPixmap()
        if pix.loadFromData(raw):
            self.thumbs[index].setPixmap(pix.scaled(self.cells[index].width(), 85, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.thumbs[index].setToolTip(tr("Click to expand frame at {time}", time=duration_text(timestamp)))
        else:
            self.thumbs[index].setText(tr("Not available"))

    def open_file(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        if self.record:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.record.path))

    def open_folder(self):
        import os
        import subprocess
        from pathlib import Path
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        if not self.record:
            return
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(self.record.path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.record.path).parent)))


class FrameViewer(QDialog):
    frame_changed = Signal(int)
    closing = Signal()

    def __init__(self, record, times, index, parent=None):
        super().__init__(parent)
        from pathlib import Path
        self.setWindowTitle(Path(record.path).name)
        self.resize(1100, 760)
        self.times, self.index = times, index
        self.original = QPixmap()
        layout = QVBoxLayout(self)
        self.image = QLabel(tr("Loading..."))
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(200, 200)
        layout.addWidget(self.image, 1)
        controls = QHBoxLayout()
        previous = QPushButton(tr("Previous frame"))
        following = QPushButton(tr("Next frame"))
        self.caption = QLabel()
        controls.addWidget(previous)
        controls.addWidget(self.caption, 1)
        controls.addWidget(following)
        layout.addLayout(controls)
        previous.clicked.connect(lambda: self.show_index(self.index - 1))
        following.clicked.connect(lambda: self.show_index(self.index + 1))
        for key, delta in [(Qt.Key.Key_Left,-1),(Qt.Key.Key_Right,1)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda d=delta: self.show_index(self.index + d))
        QTimer.singleShot(0, lambda: self.show_index(index))

    def show_index(self, index):
        if not self.times:
            return
        self.index = index % len(self.times)
        self.caption.setText(tr("Frame {number} of {total} at {time}", number=self.index+1, total=len(self.times), time=duration_text(self.times[self.index])))
        self.original = QPixmap()
        self.image.clear()
        self.image.setText(tr("Loading..."))
        self.frame_changed.emit(self.index)

    def set_image(self, data):
        if self.original.loadFromData(data):
            self._fit()
        else:
            self.image.setText(tr("Not available"))

    def _fit(self):
        if not self.original.isNull():
            self.image.setPixmap(self.original.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def closeEvent(self, event):
        self.closing.emit()
        event.accept()
