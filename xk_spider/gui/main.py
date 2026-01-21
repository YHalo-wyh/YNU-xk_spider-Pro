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
import threading

from PyQt5.QtWidgets import QApplication, QMessageBox

from .utils import OCR_AVAILABLE
from .ui import MainWindow
from .config import MONITOR_STATE_FILE


def start_watchdog(main_pid):
    """启动后台守护进程"""
    try:
        if getattr(sys, 'frozen', False):
            # 打包模式：调用 Watchdog.exe
            base_dir = os.path.dirname(sys.executable)
            watchdog_exe = os.path.join(base_dir, 'Watchdog.exe')
            
            if not os.path.exists(watchdog_exe):
                return  # 守护进程 EXE 不存在
            
            subprocess.Popen(
                [watchdog_exe, str(main_pid)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                start_new_session=True,
                cwd=base_dir
            )
        else:
            # 开发模式：运行 run_watchdog.py
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            watchdog_script = os.path.join(base_dir, 'run_watchdog.py')
            
            if not os.path.exists(watchdog_script):
                return
            
            subprocess.Popen(
                [sys.executable, watchdog_script, str(main_pid)],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                start_new_session=True,
                cwd=base_dir
            )
    except Exception as e:
        # 记录失败原因
        try:
            log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, 'watchdog_start.log'), 'a', encoding='utf-8') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 启动守护进程失败: {e}\n")
        except Exception:
            pass


def setup_exception_hook():
    """设置全局未捕获异常处理器"""
    def exception_hook(exc_type, exc_value, exc_tb):
        # 记录到崩溃日志
        try:
            log_crash(exc_value)
        except Exception:
            pass
        
        # 如果是 KeyboardInterrupt，正常退出
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        
        # 其他异常，记录后继续（不直接崩溃）
        try:
            error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
            print(f"[未捕获异常] {error_msg}")
        except Exception:
            pass
    
    sys.excepthook = exception_hook
    
    # 同时处理线程中的异常
    def thread_exception_hook(args):
        try:
            log_crash(args.exc_value)
        except Exception:
            pass
    
    if hasattr(threading, 'excepthook'):
        threading.excepthook = thread_exception_hook



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
        # 设置全局异常处理器（在最早时机）
        setup_exception_hook()
        
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
        
        # 启动后台守护进程（窗口显示后）
        start_watchdog(os.getpid())
        
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
    """主入口 - 重启由守护进程接管"""
    run_app()
    # 注意：重启逻辑已由 watchdog.pyw 守护进程接管
    # 主程序正常退出后，守护进程会检测 monitor_state.json
    # 如果监控状态为活跃，守护进程会自动重启主程序


if __name__ == '__main__':
    main()
