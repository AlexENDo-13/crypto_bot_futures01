"""Minimal theme module – dark only."""
from PyQt5.QtGui import QFont

class Theme:
    def __init__(self):
        self._dark = True
        self.colors = {
            'bg_primary': '#0b0f19',
            'bg_secondary': '#131a2b',
            'bg_tertiary': '#1c2541',
            'text_primary': '#e0e6f0',
            'text_secondary': '#8892b0',
            'text_muted': '#5a6785',
            'accent': '#00d4aa',
            'accent_hover': '#00b894',
            'success': '#34d399',
            'warning': '#fbbf24',
            'danger': '#f87171',
            'border': '#2a3650',
            'input_bg': '#0d1424',
        }
        self.FONTS = {
            'header': QFont("Segoe UI", 14, QFont.Bold),
            'large': QFont("Segoe UI", 18, QFont.Bold),
            'mono': QFont("Consolas", 10),
            'small': QFont("Segoe UI", 9),
        }

    def get_stylesheet(self):
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
            padding: 6px 14px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {c['accent']};
            color: #000000;
        }}
        QPushButton#success {{
            background-color: {c['success']};
            color: #000000;
        }}
        QPushButton#warning {{
            background-color: {c['warning']};
            color: #000000;
        }}
        QPushButton#danger {{
            background-color: {c['danger']};
            color: #000000;
        }}
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
            background-color: {c['input_bg']};
            color: {c['text_primary']};
            border: 1px solid {c['border']};
            border-radius: 3px;
            padding: 5px;
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

    def toggle(self):
        pass

theme = Theme()
