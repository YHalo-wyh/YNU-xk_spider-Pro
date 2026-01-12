"""
YNU选课助手 - 主程序入口
带有可视化UI界面的云南大学选课工具
"""
import sys
import os
import traceback

# 高 DPI 适配 - 必须在导入 PyQt5 之前设置
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QFont, QGuiApplication

from xk_spider.gui import MainWindow


def exception_hook(exctype, value, tb):
    """全局异常处理"""
    error_msg = ''.join(traceback.format_exception(exctype, value, tb))
    print(f"[CRITICAL ERROR]\n{error_msg}")
    
    # 显示错误对话框
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setWindowTitle("程序错误")
    msg.setText("程序发生错误，请查看详情")
    msg.setDetailedText(error_msg)
    msg.exec_()


def main():
    """主函数"""
    # 设置全局异常处理
    sys.excepthook = exception_hook
    
    # 启用高DPI支持 - 必须在创建 QApplication 之前
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # 设置缩放因子舍入策略 (Qt 5.14+)
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except AttributeError:
        pass  # Qt 5.14 以下版本没有这个 API
    
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName('YNU选课助手')
    app.setApplicationVersion('beta')
    
    # 设置默认字体 - 不要手动调整大小，让 Qt 自动缩放
    font = QFont('Microsoft YaHei', 9)
    app.setFont(font)
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
