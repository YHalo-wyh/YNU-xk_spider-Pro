"""
程序入口
云南大学选课助手 - 纯API版本
"""
import sys

from PyQt5.QtWidgets import QApplication, QMessageBox

from .utils import OCR_AVAILABLE
from .ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    if not OCR_AVAILABLE:
        QMessageBox.critical(
            None, "错误", 
            "OCR模块(ddddocr)未安装！\n\n纯API版本需要OCR支持。\n请安装: pip install ddddocr"
        )
        sys.exit(1)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
