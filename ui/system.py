"""
System monitoring tab: CPU, RAM, disk, temperature, ping.
"""
import logging
import psutil
import platform
import os
from datetime import datetime, timezone
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGridLayout, QGroupBox, QFormLayout
)
from PyQt5.QtCore import QTimer
from ui.styles import theme

logger = logging.getLogger(__name__)

class SystemTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()
        self._start_timer()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        header = QLabel("System Monitoring")
        header.setFont(theme.FONTS['header'])
        layout.addWidget(header)

        sys_group = QGroupBox("Hardware")
        sys_layout = QFormLayout(sys_group)
        self.lbl_cpu = QLabel("CPU: --%")
        self.lbl_ram = QLabel("RAM: --")
        self.lbl_disk = QLabel("Disk: --")
        self.lbl_temp = QLabel("Temp: --°C")
        sys_layout.addRow("CPU Load:", self.lbl_cpu)
        sys_layout.addRow("RAM Used:", self.lbl_ram)
        sys_layout.addRow("Disk Free:", self.lbl_disk)
        sys_layout.addRow("Temperature:", self.lbl_temp)
        layout.addWidget(sys_group)

        bot_group = QGroupBox("Bot Status")
        bot_layout = QFormLayout(bot_group)
        self.lbl_uptime = QLabel("Uptime: --")
        self.lbl_ping = QLabel("Ping: -- ms")
        self.lbl_threads = QLabel("Threads: --")
        bot_layout.addRow("Uptime:", self.lbl_uptime)
        bot_layout.addRow("API Ping:", self.lbl_ping)
        bot_layout.addRow("Active Threads:", self.lbl_threads)
        layout.addWidget(bot_group)
        layout.addStretch()

    def _start_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(3000)

    def _get_cpu_temp(self):
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        if entries:
                            return entries[0].current
        except Exception:
            pass
        try:
            import wmi
            w = wmi.WMI(namespace="root\\wmi")
            temperature_info = w.MSAcpi_ThermalZoneTemperature()
            if temperature_info:
                return (temperature_info[0].CurrentTemperature / 10.0) - 273.15
        except Exception:
            pass
        return None

    def _update(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            self.lbl_cpu.setText(f"CPU: {cpu:.1f}%")

            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024**3)
            used_gb = mem.used / (1024**3)
            self.lbl_ram.setText(f"RAM: {used_gb:.1f} / {total_gb:.1f} GB ({mem.percent:.0f}%)")

            disk = psutil.disk_usage(os.getcwd())
            free_gb = disk.free / (1024**3)
            total_disk = disk.total / (1024**3)
            self.lbl_disk.setText(f"Disk: {free_gb:.1f} GB free / {total_disk:.1f} GB")

            temp = self._get_cpu_temp()
            if temp is not None:
                self.lbl_temp.setText(f"Temp: {temp:.0f}°C")
            else:
                self.lbl_temp.setText("Temp: N/A")

            if self.engine._running:
                if not hasattr(self.engine, '_start_time'):
                    self.engine._start_time = datetime.now(timezone.utc)
                uptime = datetime.now(timezone.utc) - self.engine._start_time
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                mins, secs = divmod(remainder, 60)
                self.lbl_uptime.setText(f"Uptime: {hours:02}:{mins:02}:{secs:02}")
            else:
                self.lbl_uptime.setText("Stopped")

            ping_ms = self.engine.api.last_ping_ms
            if ping_ms:
                self.lbl_ping.setText(f"Ping: {ping_ms:.0f} ms")
            else:
                self.lbl_ping.setText("Ping: --")

            import threading
            self.lbl_threads.setText(f"Threads: {threading.active_count()}")
        except Exception as e:
            logger.debug(f"System tab update error: {e}")

    def apply_theme(self):
        pass
