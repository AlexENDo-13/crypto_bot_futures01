"""
Theme management: dark and light themes with high contrast.
"""
from PyQt5.QtGui import QFont

class Theme:
    def __init__(self):
        self._dark = True
        self.colors = {}
        self.FONTS = {
            'default': QFont('Segoe UI', 9),
            'header': QFont('Segoe UI', 11, QFont.Bold),
            'large': QFont('Segoe UI', 16, QFont.Bold),
            'mono': QFont('Consolas', 9),
            'small': QFont('Segoe UI', 8),        # ← возвращён
        }
        self._set_dark_theme()

    def _set_dark_theme(self):
        self.colors.update({
            'bg_primary': '#1e1e2e',
            'bg_secondary': '#2a2a3e',
            'bg_tertiary': '#333350',
            'text_primary': '#e0e0f0',
            'text_secondary': '#a0a0c0',
            'text_muted': '#707090',
            'accent': '#7c3aed',
            'accent_hover': '#9d6ff5',
            'success': '#34d399',
            'warning': '#fbbf24',
            'danger': '#f87171',
            'border': '#404060',
            'input_bg': '#252540',
        })

    def _set_light_theme(self):
        self.colors.update({
            'bg_primary': '#ffffff',
            'bg_secondary': '#f3f4f6',
            'bg_tertiary': '#e5e7eb',
            'text_primary': '#111827',
            'text_secondary': '#4b5563',
            'text_muted': '#9ca3af',
            'accent': '#7c3aed',
            'accent_hover': '#9d6ff5',
            'success': '#059669',
            'warning': '#d97706',
            'danger': '#dc2626',
            'border': '#d1d5db',
            'input_bg': '#ffffff',
        })

    def toggle(self):
        if self._dark:
            self._set_light_theme()
        else:
            self._set_dark_theme()
        self._dark = not self._dark

    def get_stylesheet(self) -> str:
        c = self.colors
        return f"""
        QMainWindow {{
            background-color: {c['bg_primary']};
        }}
        QWidget {{
            background-color: {c['bg_primary']};
            color: {c['text_primary']};
            font-family: 'Segoe UI';
            font-size: 9pt;
        }}
        QLabel {{
            background: transparent;
            color: {c['text_primary']};
        }}
        QPushButton {{
            background-color: {c['bg_tertiary']};
            color: {c['text_primary']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 6px 12px;
        }}
        QPushButton:hover {{
            background-color: {c['accent']};
            color: white;
        }}
        QPushButton#success {{
            background-color: {c['success']};
            color: white;
        }}
        QPushButton#warning {{
            background-color: {c['warning']};
            color: black;
        }}
        QPushButton#danger {{
            background-color: {c['danger']};
            color: white;
        }}
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
            background-color: {c['input_bg']};
            color: {c['text_primary']};
            border: 1px solid {c['border']};
            border-radius: 3px;
            padding: 4px;
        }}
        QTableWidget {{
            background-color: {c['bg_secondary']};
            color: {c['text_primary']};
            gridline-color: {c['border']};
            border: 1px solid {c['border']};
        }}
        QHeaderView::section {{
            background-color: {c['bg_tertiary']};
            color: {c['text_primary']};
            padding: 4px;
            border: 1px solid {c['border']};
        }}
        QTabWidget::pane {{
            border: 1px solid {c['border']};
            background-color: {c['bg_primary']};
        }}
        QTabBar::tab {{
            background-color: {c['bg_secondary']};
            color: {c['text_secondary']};
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:selected {{
            background-color: {c['bg_primary']};
            color: {c['accent']};
        }}
        QStatusBar {{
            background-color: {c['bg_tertiary']};
            color: {c['text_secondary']};
        }}
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QGroupBox {{
            border: 1px solid {c['border']};
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 16px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }}
        QCheckBox {{
            spacing: 6px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
        }}
        """

theme = Theme()
