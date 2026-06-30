import asyncio
import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from polar import HeartbeatEvent, PolarH10Stream
from protocol import YMCA_STEP_TEST_V1
from session_store import (
    DEFAULT_SESSION_DIR,
    SessionRecorder,
    derive_bpm_from_heartbeats,
    list_sessions,
)


class SensorWorker(QObject):
    heartbeat = Signal(object)
    status = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, name="Polar", address=None, scan_timeout=10.0):
        super().__init__()
        self.name = name
        self.address = address
        self.scan_timeout = scan_timeout
        self._stream: PolarH10Stream | None = None

    @Slot()
    def run(self):
        try:
            asyncio.run(self._run_async())
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    async def _run_async(self):
        self._stream = PolarH10Stream(
            name=self.name,
            address=self.address,
            scan_timeout=self.scan_timeout,
        )
        await self._stream.connect(
            on_heartbeat=self.heartbeat.emit,
            on_status=self.status.emit,
        )
        await self._stream.wait_until_stopped()


class MainWindow(QMainWindow):
    tick_ms = 250

    def __init__(self):
        super().__init__()
        self.protocol = YMCA_STEP_TEST_V1
        self.recorder: SessionRecorder | None = None
        self.phase_index = 0
        self.phase_elapsed_s = 0.0
        self.total_elapsed_s = 0.0
        self.running = False
        self.paused = False
        self.recent_heartbeats = deque(maxlen=64)
        self.sensor_thread: QThread | None = None
        self.sensor_worker: SensorWorker | None = None

        self.setWindowTitle("YMCA Step Test")
        self.resize(980, 620)
        self._build_ui()
        self._load_sessions()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(self.tick_ms)

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("YMCA Step Test")
        title.setObjectName("title")
        layout.addWidget(title)

        status_grid = QGridLayout()
        self.phase_label = QLabel("Ready")
        self.phase_label.setObjectName("phase")
        self.time_label = QLabel("00:00")
        self.bpm_label = QLabel("-- bpm")
        self.sensor_label = QLabel("sensor: disconnected")
        self.session_label = QLabel(f"sessions: {Path(DEFAULT_SESSION_DIR)}")

        status_grid.addWidget(QLabel("Phase"), 0, 0)
        status_grid.addWidget(self.phase_label, 0, 1)
        status_grid.addWidget(QLabel("Time"), 1, 0)
        status_grid.addWidget(self.time_label, 1, 1)
        status_grid.addWidget(QLabel("Heart rate"), 0, 2)
        status_grid.addWidget(self.bpm_label, 0, 3)
        status_grid.addWidget(QLabel("Sensor"), 1, 2)
        status_grid.addWidget(self.sensor_label, 1, 3)
        status_grid.addWidget(self.session_label, 2, 0, 1, 4)
        status_grid.setColumnStretch(1, 1)
        status_grid.setColumnStretch(3, 1)
        layout.addLayout(status_grid)

        self.progress = QProgressBar()
        self.progress.setRange(0, self.protocol.total_duration_s)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        controls = QHBoxLayout()
        self.connect_button = QPushButton("Connect Sensor")
        self.start_button = QPushButton("Start Protocol")
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.stop_button = QPushButton("Stop")
        for button in (
            self.connect_button,
            self.start_button,
            self.pause_button,
            self.resume_button,
            self.stop_button,
        ):
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.connect_button.clicked.connect(self.connect_sensor)
        self.start_button.clicked.connect(self.start_protocol)
        self.pause_button.clicked.connect(self.pause_protocol)
        self.resume_button.clicked.connect(self.resume_protocol)
        self.stop_button.clicked.connect(self.stop_protocol)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.event_log = QPlainTextEdit()
        self.event_log.setReadOnly(True)
        self.event_log.setPlaceholderText("Event log")
        self.session_list = QListWidget()
        splitter.addWidget(self.event_log)
        splitter.addWidget(self.session_list)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(
            """
            QMainWindow { background: #f6f7f8; }
            QLabel#title { font-size: 26px; font-weight: 700; color: #202427; }
            QLabel#phase { font-size: 22px; font-weight: 700; color: #202427; }
            QLabel { color: #2f363a; }
            QPushButton { padding: 8px 12px; border: 1px solid #aeb6bd; border-radius: 4px; background: #ffffff; }
            QPushButton:disabled { color: #8a9298; background: #eceff1; }
            QPlainTextEdit, QListWidget { background: #ffffff; border: 1px solid #cbd1d6; border-radius: 4px; }
            QProgressBar { border: 1px solid #aeb6bd; border-radius: 4px; height: 18px; text-align: center; background: #ffffff; }
            QProgressBar::chunk { background: #2d7d73; }
            """
        )
        self._update_controls()

    def connect_sensor(self):
        if self.sensor_thread is not None:
            return
        self.sensor_thread = QThread()
        self.sensor_worker = SensorWorker()
        self.sensor_worker.moveToThread(self.sensor_thread)
        self.sensor_thread.started.connect(self.sensor_worker.run)
        self.sensor_worker.heartbeat.connect(self._handle_heartbeat)
        self.sensor_worker.status.connect(self._handle_sensor_status)
        self.sensor_worker.error.connect(self._handle_sensor_error)
        self.sensor_worker.finished.connect(self.sensor_thread.quit)
        self.sensor_worker.finished.connect(self.sensor_worker.deleteLater)
        self.sensor_thread.finished.connect(self._sensor_thread_finished)
        self.sensor_label.setText("sensor: scanning")
        self.connect_button.setEnabled(False)
        self.sensor_thread.start()

    def start_protocol(self):
        self.recorder = SessionRecorder(self.protocol)
        self.phase_index = 0
        self.phase_elapsed_s = 0.0
        self.total_elapsed_s = 0.0
        self.running = True
        self.paused = False
        self.recent_heartbeats.clear()
        self._start_phase()
        self._append_log(f"session started: {self.recorder.path}")
        self._update_controls()

    def pause_protocol(self):
        if self.running and not self.paused:
            self.paused = True
            if self.recorder is not None:
                self.recorder.record_event("note", message="protocol paused")
            self._append_log("protocol paused")
            self._update_controls()

    def resume_protocol(self):
        if self.running and self.paused:
            self.paused = False
            if self.recorder is not None:
                self.recorder.record_event("note", message="protocol resumed")
            self._append_log("protocol resumed")
            self._update_controls()

    def stop_protocol(self):
        if not self.running:
            return
        self._complete_current_phase()
        self.running = False
        self.paused = False
        if self.recorder is not None:
            path = self.recorder.complete(status="stopped")
            self._append_log(f"session stopped: {path}")
            self.recorder = None
        self._load_sessions()
        self._update_controls()

    def _tick(self):
        if not self.running or self.paused:
            return
        delta_s = self.tick_ms / 1000.0
        self.phase_elapsed_s += delta_s
        self.total_elapsed_s += delta_s
        phase = self.protocol.phases[self.phase_index]
        if self.phase_elapsed_s >= phase.duration_s:
            self._complete_current_phase()
            self.phase_index += 1
            if self.phase_index >= len(self.protocol.phases):
                self._finish_protocol()
            else:
                self.phase_elapsed_s = 0.0
                self._start_phase()
        self._update_status()

    def _start_phase(self):
        phase = self.protocol.phases[self.phase_index]
        if self.recorder is not None:
            self.recorder.record_event(
                "phase_started",
                phase=phase.name,
                duration_s=phase.duration_s,
                measurement_point=phase.measurement_point,
            )
        self._append_log(f"phase started: {phase.name}")
        self._update_status()

    def _complete_current_phase(self):
        if self.phase_index >= len(self.protocol.phases):
            return
        phase = self.protocol.phases[self.phase_index]
        if self.recorder is not None:
            self.recorder.record_event("phase_completed", phase=phase.name)
        self._append_log(f"phase completed: {phase.name}")

    def _finish_protocol(self):
        self.running = False
        self.paused = False
        if self.recorder is not None:
            path = self.recorder.complete(status="completed")
            self._append_log(f"session completed: {path}")
            self.recorder = None
        self._load_sessions()
        self._update_controls()

    @Slot(object)
    def _handle_heartbeat(self, heartbeat: HeartbeatEvent):
        self.recent_heartbeats.append(
            {
                "type": "heartbeat",
                "t_monotonic_s": self.total_elapsed_s,
            }
        )
        bpm = heartbeat.derived_bpm or derive_bpm_from_heartbeats(
            list(self.recent_heartbeats),
            window_s=15.0,
        )
        self.bpm_label.setText(f"{bpm:.0f} bpm" if bpm is not None else "-- bpm")

        if self.recorder is not None:
            self.recorder.record_heartbeat(
                rr_ms=heartbeat.rr_ms,
                sensor_time_s=heartbeat.sensor_time_s,
                source=heartbeat.source,
            )
        rr = f", rr={heartbeat.rr_ms} ms" if heartbeat.rr_ms is not None else ""
        self._append_log(f"heartbeat: {self.bpm_label.text()}{rr}")

    @Slot(str)
    def _handle_sensor_status(self, status):
        self.sensor_label.setText(f"sensor: {status}")
        if self.recorder is not None and status in {
            "connected",
            "streaming",
            "disconnected",
            "no_device",
        }:
            event_type = "sensor_connected" if status in {"connected", "streaming"} else "sensor_disconnected"
            self.recorder.record_event(event_type, status=status)
        self._append_log(f"sensor: {status}")

    @Slot(str)
    def _handle_sensor_error(self, message):
        self.sensor_label.setText("sensor: error")
        self._append_log(f"sensor error: {message}")
        QMessageBox.warning(self, "Sensor connection failed", message)

    @Slot()
    def _sensor_thread_finished(self):
        if self.sensor_thread is not None:
            self.sensor_thread.deleteLater()
        self.sensor_thread = None
        self.sensor_worker = None
        self.connect_button.setEnabled(True)

    def _update_status(self):
        if not self.running:
            self.phase_label.setText("Ready")
            self.time_label.setText("00:00")
            self.progress.setValue(0)
            return
        phase = self.protocol.phases[self.phase_index]
        remaining_s = max(0, int(round(phase.duration_s - self.phase_elapsed_s)))
        self.phase_label.setText(phase.name.replace("_", " "))
        self.time_label.setText(self._format_seconds(remaining_s))
        self.progress.setValue(min(int(round(self.total_elapsed_s)), self.protocol.total_duration_s))

    def _update_controls(self):
        self.start_button.setEnabled(not self.running)
        self.pause_button.setEnabled(self.running and not self.paused)
        self.resume_button.setEnabled(self.running and self.paused)
        self.stop_button.setEnabled(self.running)
        self._update_status()

    def _append_log(self, message):
        self.event_log.appendPlainText(message)

    def _load_sessions(self):
        self.session_list.clear()
        for summary in list_sessions():
            recovery = (
                f", recovery {summary.average_recovery_bpm:.0f} bpm"
                if summary.average_recovery_bpm is not None
                else ""
            )
            complete = "complete" if summary.completed else "open"
            self.session_list.addItem(
                f"{summary.started_at_wall} | {complete} | {summary.heartbeat_count} beats{recovery}"
            )

    @staticmethod
    def _format_seconds(seconds):
        minutes, remainder = divmod(max(0, int(seconds)), 60)
        return f"{minutes:02}:{remainder:02}"


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
