"""Minimal theme module."""
from PyQt5.QtGui import QFont

class Theme:
    def __init__(self):
        self.colors = {
            'accent': '#00d4aa', 'accent_hover': '#00b894', 'success': '#34d399',
            'danger': '#f87171', 'warning': '#fbbf24', 'bg_primary': '#0f172a',
            'bg_secondary': '#1e293b', 'bg_tertiary': '#1e293b',  # ← добавлено (можно выбрать другой оттенок)
            'text_primary': '#f1f5f9',
            'text_secondary': '#94a3b8', 'text_muted': '#64748b', 'border': '#334155',
        }
        self.FONTS = {
            'header': QFont("Segoe UI", 14, QFont.Bold),
            'large': QFont("Segoe UI", 18, QFont.Bold),
            'mono': QFont("Consolas", 10),
            'small': QFont("Segoe UI", 9),
        }
        self._dark = True

    def get_stylesheet(self):
        c = self.colors
        return f"""
        QMainWindow {{ background-color: {c['bg_primary']}; color: {c['text_primary']}; }}
        QWidget {{ background-color: {c['bg_primary']}; color: {c['text_primary']}; }}
        QTabWidget::pane {{ border: 1px solid {c['border']}; background: {c['bg_primary']}; }}
        QTabBar::tab {{ background: {c['bg_secondary']}; color: {c['text_secondary']}; padding: 8px 16px; border: 1px solid {c['border']}; }}
        QTabBar::tab:selected {{ background: {c['bg_primary']}; color: {c['text_primary']}; border-bottom: 2px solid {c['accent']}; }}
        QPushButton {{ background-color: {c['bg_secondary']}; color: {c['text_primary']}; border: 1px solid {c['border']}; padding: 6px 12px; border-radius: 4px; }}
        QPushButton:hover {{ background-color: {c['border']}; }}
        QPushButton#success {{ background-color: {c['success']}; color: #000; }}
        QPushButton#danger {{ background-color: {c['danger']}; color: #000; }}
        QPushButton#warning {{ background-color: {c['warning']}; color: #000; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {c['bg_secondary']}; color: {c['text_primary']}; border: 1px solid {c['border']}; padding: 4px; }}
        QTableWidget {{ background: {c['bg_secondary']}; color: {c['text_primary']}; gridline-color: {c['border']}; }}
        QHeaderView::section {{ background: {c['bg_primary']}; color: {c['text_primary']}; padding: 4px; border: 1px solid {c['border']}; }}
        QGroupBox {{ border: 1px solid {c['border']}; margin-top: 10px; padding-top: 10px; }}
        QLabel {{ color: {c['text_primary']}; }}
        QStatusBar {{ background: {c['bg_secondary']}; color: {c['text_secondary']}; }}
        """
    
    def toggle(self):
        self._dark = not self._dark
    def apply_theme(self):
        pass

theme = Theme()
