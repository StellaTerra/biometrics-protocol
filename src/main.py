import sys
import asyncio
from bleak import BleakScanner, BleakClient
from bleakheart import HeartRate
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heart Rate Monitor")
        self.setGeometry(100, 100, 400, 300)

async def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    await app.exec()

if __name__ == "__main__":
    asyncio.run(main())