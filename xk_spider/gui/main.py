"""
程序入口
云南大学选课助手 - 纯API版本
支持自动重启和监控状态恢复
"""
import sys
import os
import time
import json
import subprocess
import traceback

from PyQt5.QtWidgets import QApplication, QMessageBox

from .utils import OCR_AVAILABLE
from .ui import MainWindow
from .config import MONITOR_STATE_FILE


def load_monitor_state_simple():
    """简单加载监控状态文件（不依赖 MainWindow）"""
    try:
        if os.path.exists(MONITOR_STATE_FILE):
            with open(MONITOR_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return None


def log_crash(error):
    """记录崩溃日志"""
    try:
        os.makedirs('xk_spider', exist_ok=True)
        with open('xk_spider/crash.log', 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 程序崩溃\n")
            f.write(f"错误: {error}\n")
            f.write(traceback.format_exc())
    except Exception:
        pass


def run_app():
    """运行主程序，返回是否需要重启"""
    try:
        # Windows 任务栏图标需要设置 AppUserModelID
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('YNU.XKHelper.Pro')
        
        app = QApplication(sys.argv)
        app.setStyle('Fusion')
        
        # 设置应用级别图标（任务栏图标）
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icon.ico'))
        if os.path.exists(icon_path):
            from PyQt5.QtGui import QIcon
            app.setWindowIcon(QIcon(icon_path))
        
        if not OCR_AVAILABLE:
            QMessageBox.critical(
                None, "错误", 
                "OCR模块(ddddocr)未安装！\n\n纯API版本需要OCR支持。\n请安装: pip install ddddocr"
            )
            return False  # 无法修复的错误，不重启
        
        window = MainWindow()
        window.show()
        app.exec_()
        
        # 程序退出后，检查是否需要重启
        state = load_monitor_state_simple()
        if state and state.get('is_monitoring'):
            return True  # 需要重启
        return False  # 不需要重启
        
    except Exception as e:
        log_crash(e)
        print(f"[{time.strftime('%H:%M:%S')}] 程序崩溃: {e}")
        # 检查是否在监控中
        state = load_monitor_state_simple()
        if state and state.get('is_monitoring'):
            return True  # 监控中崩溃，需要重启
        return False  # 非监控状态崩溃，不重启


def main():
    """主入口 - 自动重启支持"""
    need_restart = run_app()
    
    if need_restart:
        print(f"[{time.strftime('%H:%M:%S')}] 检测到监控状态，2秒后自动重启...")
        time.sleep(2)
        
        # 使用子进程重新启动程序
        python = sys.executable
        script = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'run_gui.py'))
        
        # 启动新进程
        subprocess.Popen(
            [python, script],
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
        )


if __name__ == '__main__':
    main()
