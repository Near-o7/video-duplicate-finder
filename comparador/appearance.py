"""A consistent light palette, including popups when Windows uses dark mode."""
from PySide6.QtCore import Qt, QByteArray, QTranslator, QLibraryInfo
from PySide6.QtGui import QColor, QPalette, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

STYLE = """
QWidget { font-family:'Segoe UI'; font-size:11pt; color:#24343b; }
QMainWindow, #shell { background:#f5f6f3; }
QDialog, QMessageBox, QFileDialog { background:#f5f6f3; color:#24343b; }
QLabel { background:transparent; }
QLabel#brand { font-size:18pt; font-weight:700; color:#173c36; }
QLabel#title { font-size:17pt; font-weight:600; }
QLabel#section { font-weight:600; }
QLabel#muted { color:#4c6069; font-size:10pt; }
QLabel#step { color:#176052; font-size:10pt; font-weight:600; }
QFrame#setup { background:white; border:1px solid #d0dad7; border-radius:8px; }
QFrame#detail { background:white; border:1px solid #d0dad7; border-radius:6px; }
QLabel#notice { background:#e6eee9; color:#234a40; padding:9px 12px; border-radius:4px; }
QLabel#thumb { background:#edf0eb; color:#4f6569; border-radius:3px; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { color:#203238; background:white; border:1px solid #a8bab5; border-radius:4px; padding:7px; min-height:20px; selection-background-color:#c6e5d8; selection-color:#142c25; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border:1px solid #18745e; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color:#66766e; background:#edf0ed; }
QComboBox QAbstractItemView, QAbstractItemView { color:#203238; background:white; selection-background-color:#c6e5d8; selection-color:#142c25; outline:0; }
QComboBox QAbstractItemView::item { min-height:32px; padding:4px 9px; }
QComboBox::drop-down { border:none; width:24px; }
QComboBox { padding-right:28px; }
QComboBox::down-arrow { image:url('__DOWN__'); width:12px; height:12px; }
QSpinBox { padding-right:24px; }
QSpinBox::up-button { subcontrol-origin:border; subcontrol-position:top right; width:20px; border:none; }
QSpinBox::down-button { subcontrol-origin:border; subcontrol-position:bottom right; width:20px; border:none; }
QSpinBox::up-arrow { image:url('__UP__'); width:10px; height:10px; }
QSpinBox::down-arrow { image:url('__DOWN__'); width:10px; height:10px; }
QPushButton { color:#223e35; background:white; border:1px solid #a8bab5; border-radius:4px; padding:7px 12px; min-height:22px; font-weight:600; }
QPushButton:hover { background:#e6f1ea; border-color:#4b8c76; }
QPushButton:pressed { background:#cce1d4; }
QPushButton:disabled { color:#6c7973; background:#ebeeea; border-color:#d5ddd7; }
QPushButton#primary { color:white; background:#176451; border-color:#176451; }
QPushButton#primary:hover { background:#104e3f; }
QPushButton#primary:disabled { color:#566b62; background:#d7e4dc; border-color:#c3d3c8; }
QPushButton#danger { color:#9a2936; background:white; border-color:#b66e78; }
QPushButton#danger:hover { background:#fae8e9; }
QPushButton#danger:disabled { color:#6c7973; background:#ebeeea; border-color:#d5ddd7; }
QCheckBox { spacing:8px; color:#24343b; }
QCheckBox::indicator, QTableWidget::indicator { width:17px; height:17px; border:1px solid #79948a; background:white; border-radius:3px; }
QCheckBox::indicator:checked, QTableWidget::indicator:checked { background:#176451; border:2px solid #176451; image:url('__CHECK__'); }
QTableWidget { background:white; alternate-background-color:#f6f8f5; color:#24343b; border:1px solid #cad6ce; border-radius:4px; selection-background-color:#dfefe5; selection-color:#183d2f; }
QTableWidget::item { padding:7px; border-bottom:1px solid #e6ebe5; }
QHeaderView::section { background:#e9eeea; color:#354e44; padding:9px 6px; border:none; border-bottom:1px solid #bfcfc3; font-weight:600; }
QTabBar::tab { background:transparent; color:#465d51; padding:9px 18px; border-bottom:3px solid transparent; }
QTabBar::tab:selected { color:#144f3e; border-bottom:3px solid #176451; font-weight:600; }
QTabBar::tab:hover { background:#e6eee8; }
QProgressBar { background:#dce5dd; border:none; border-radius:3px; height:7px; }
QProgressBar::chunk { background:#28785e; border-radius:3px; }
QScrollArea { border:none; background:transparent; }
QSplitter::handle { background:#dde6de; }
QToolTip { background:#203e32; color:white; border:0; padding:6px; }
"""

PATHS = {
    "folder": '<path d="M3 7h7l2 2h9v11H3zM3 7V4h7l2 3"/>',
    "scan": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6M10 7v6"/>',
    "export": '<path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/>',
    "trash": '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    "play": '<path d="m8 4 12 8L8 20z"/>',
    "move": '<path d="M3 12h17m-5-5 5 5-5 5M5 5H3v14h2"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "select": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m7 12 3 3 7-7"/>',
    "app": '<rect x="4" y="7" width="12" height="14" rx="2"/><path d="M9 7V3h11v14h-4M7 12h6M7 16h6"/>',
}


def icon(name, color=None):
    if color is None:
        from PySide6.QtWidgets import QApplication
        color = "#a9e0c9" if is_dark(QApplication.instance()) else "#245b47"
    data = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</g></svg>'
    pix = QPixmap(48, 48)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(data.encode())).render(painter)
    painter.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


def is_dark(app):
    return bool(app and app.palette().color(QPalette.ColorRole.Window).lightness() < 100)


def status_color(status):
    from PySide6.QtWidgets import QApplication
    colors = ({"Exact copy":"#7bd7b3", "Possible duplicate":"#ffd38a", "Error or pending":"#ffacb7"}
              if is_dark(QApplication.instance()) else {"Exact copy":"#137366", "Possible duplicate":"#98610a", "Error or pending":"#b13c48"})
    return QColor(colors.get(status, "#bed1c7" if is_dark(QApplication.instance()) else "#53647e"))


DARK = dict(zip(
    "#f5f6f3 #24343b #173c36 #4c6069 #176052 #d0dad7 #e6eee9 #234a40 #edf0eb #4f6569 #203238 #a8bab5 #c6e5d8 #142c25 #18745e #66766e #edf0ed #223e35 #e6f1ea #4b8c76 #cce1d4 #6c7973 #ebeeea #d5ddd7 #176451 #104e3f #566b62 #d7e4dc #c3d3c8 #9a2936 #b66e78 #fae8e9 #79948a #f6f8f5 #cad6ce #dfefe5 #183d2f #e6ebe5 #e9eeea #354e44 #bfcfc3 #465d51 #144f3e #e6eee8 #dce5dd #28785e #dde6de #203e32".split(),
    "#151d20 #dce8e5 #b9e8d7 #b0c4bf #9bd8c2 #4b5f5c #263c35 #c4eadc #202a2e #b2c5bf #e0ebe8 #58716a #32654f #eafff5 #81cdb0 #afbeb7 #242f32 #d8e9e1 #31473c #79c09f #3c5b4a #a4b5ad #253034 #46574f #2f755e #388166 #abbfb4 #294437 #465d50 #ffb5bf #a76974 #523139 #8ab5a2 #202a2d #4b5f54 #345a46 #e1f7eb #34463b #2c3d34 #d6e8de #536f5c #bdd3c4 #b9ead7 #2d4537 #34463b #73b89b #354d3e #2a4b38".split()))


def apply_theme(app, mode="light"):
    from pathlib import Path
    import sys
    app.setStyle("Fusion")
    app._applying_theme = True
    hints = app.styleHints()
    hints.setColorScheme({"light":Qt.ColorScheme.Light, "dark":Qt.ColorScheme.Dark}.get(mode, Qt.ColorScheme.Unknown))
    dark = mode == "dark" or mode == "system" and hints.colorScheme() == Qt.ColorScheme.Dark
    palette = QPalette()
    colors = {QPalette.ColorRole.Window:'#f5f6f3', QPalette.ColorRole.WindowText:'#24343b',
              QPalette.ColorRole.Base:'#ffffff', QPalette.ColorRole.AlternateBase:'#f6f8f5',
              QPalette.ColorRole.Text:'#203238', QPalette.ColorRole.Button:'#ffffff',
              QPalette.ColorRole.ButtonText:'#223e35', QPalette.ColorRole.Highlight:'#c6e5d8',
              QPalette.ColorRole.HighlightedText:'#142c25', QPalette.ColorRole.PlaceholderText:'#536a60',
              QPalette.ColorRole.ToolTipBase:'#203e32', QPalette.ColorRole.ToolTipText:'#ffffff'}
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        for role, color in colors.items():
            palette.setColor(group, role, QColor(("#222d31" if color == "#ffffff" else DARK.get(color,color)) if dark else color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#a4b5ad' if dark else '#6c7973'))
    app.setPalette(palette)
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    from .i18n import language
    previous = getattr(app, '_spanish_translator', None)
    if previous:
        app.removeTranslator(previous)
        app._spanish_translator = None
    if language() == "es":
        translator = QTranslator(app)
        locations = [base / 'translations/qtbase_es.qm', Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)) / 'qtbase_es.qm']
        for location in locations:
            if translator.load(str(location)):
                app.installTranslator(translator)
                app._spanish_translator = translator
                break
    style = STYLE
    if dark:
        import re
        style = re.sub(r'#[0-9a-fA-F]{6}', lambda m: DARK.get(m.group(),m.group()), style)
        style = style.replace('background:white', 'background:#222d31')
        style = style.replace('color:#ffffff', 'color:white')
    for key, name in [('__CHECK__', 'check'), ('__DOWN__', 'chevron-down'), ('__UP__', 'chevron-up')]:
        if dark and name != 'check':
            name += '-dark'
        style = style.replace(key, (base / f'assets/{name}.svg').as_posix())
    app.setStyleSheet(style)
    app._applying_theme = False
