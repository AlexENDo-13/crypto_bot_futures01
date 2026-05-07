"""
PDF Report Generator – creates a professional report with metrics and charts.
Requires: pip install fpdf2 matplotlib
"""
import logging, io, os, tempfile
from datetime import datetime, timezone
from fpdf import FPDF
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

logger = logging.getLogger(__name__)

class PDFReporter:
    def __init__(self, engine):
        self.engine = engine

    def generate_report(self, days: int = 7) -> str:
        """Генерирует PDF и возвращает путь к файлу."""
        status = self.engine.get_status()
        equity_curve = self.engine.portfolio.get_equity_curve(days)
        trades = self.engine.portfolio.trades[-50:]  # последние 50 сделок

        pdf = FPDF()
        pdf.add_page()
        # Заголовок
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"BingX Trading Bot Report {datetime.now(timezone.utc).strftime('%Y-%m-%d')}", ln=True, align='C')
        pdf.ln(5)

        # Основные метрики
        pdf.set_font("Arial", size=12)
        metrics = [
            ("Balance", f"{status['balance']:.2f} USDT"),
            ("Equity", f"{status['equity']:.2f} USDT"),
            ("Daily PnL", f"{status['daily_pnl']:.2f} USDT"),
            ("Open Positions", str(status['open_positions'])),
            ("Win Rate", f"{status['win_rate']:.1f}%"),
            ("Total Trades", str(len(trades)))
        ]
        for label, value in metrics:
            pdf.cell(40, 8, label + ":", 0, 0)
            pdf.cell(0, 8, value, 0, 1)

        pdf.ln(5)

        # График эквити
        if equity_curve:
            try:
                times = [datetime.fromisoformat(e['time']) for e in equity_curve]
                values = [e['equity'] for e in equity_curve]
                plt.figure(figsize=(8, 3))
                plt.plot(times, values, color='green')
                plt.fill_between(times, values, alpha=0.2, color='green')
                plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
                plt.title("Equity Curve")
                plt.tight_layout()
                img_bytes = io.BytesIO()
                plt.savefig(img_bytes, format='PNG')
                plt.close()
                img_bytes.seek(0)
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    tmp.write(img_bytes.read())
                    img_path = tmp.name
                pdf.image(img_path, x=10, w=190)
                os.unlink(img_path)
            except Exception as e:
                logger.error(f"Error creating equity chart: {e}")

        pdf.ln(5)
        # Таблица последних сделок
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 8, "Last trades", ln=True)
        pdf.set_font("Arial", size=8)
        if trades:
            # Шапка
            col_widths = [30, 18, 22, 22, 22, 20, 20, 30]
            headers = ["Time", "Symbol", "Side", "Entry", "Exit", "Qty", "PnL", "Reason"]
            for i, h in enumerate(headers):
                pdf.cell(col_widths[i], 6, h, border=1)
            pdf.ln()
            for t in trades[-15:]:
                pdf.cell(col_widths[0], 6, t.close_time[:10], border=1)
                pdf.cell(col_widths[1], 6, t.symbol[:8], border=1)
                pdf.cell(col_widths[2], 6, t.side[:4], border=1)
                pdf.cell(col_widths[3], 6, f"{t.entry_price:.4f}", border=1)
                pdf.cell(col_widths[4], 6, f"{t.exit_price:.4f}", border=1)
                pdf.cell(col_widths[5], 6, f"{t.quantity:.4f}", border=1)
                pdf.cell(col_widths[6], 6, f"{t.pnl:+.2f}", border=1)
                pdf.cell(col_widths[7], 6, t.close_reason[:10], border=1)
                pdf.ln()

        # Сохранение во временный файл
        tmp_path = os.path.join(tempfile.gettempdir(), "bot_report.pdf")
        pdf.output(tmp_path)
        return tmp_path

    def send_to_telegram(self, filepath: str):
        """Отправляет PDF через Telegram бота."""
        if not hasattr(self.engine, 'telegram') or not self.engine.telegram.enabled:
            logger.warning("Telegram not available for PDF report")
            return
        try:
            with open(filepath, 'rb') as f:
                self.engine.telegram.send_document(f, "bot_report.pdf", caption="Daily Report")
        except Exception as e:
            logger.error(f"Failed to send PDF: {e}")
