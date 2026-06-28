import sys

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
except ModuleNotFoundError as exc:
    if exc.name == "PySide6":
        print("PySide6 is not installed. Try: python3 -m pip install PySide6")
        raise SystemExit(1)
    raise


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PySide6 Smoke Test")
        self.resize(420, 180)

        label = QLabel("PySide6 is working")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(label)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
