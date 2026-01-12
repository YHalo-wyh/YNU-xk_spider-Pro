"""
YNU选课助手 - 主程序入口
带有可视化UI界面的云南大学选课工具
"""
import sys
import os
import traceback

# 将项目根目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

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
    
    # 启用高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName('YNU选课助手')
    app.setApplicationVersion('beta')
    
    # 设置默认字体
    font = QFont('Microsoft YaHei', 10)
    app.setFont(font)
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
