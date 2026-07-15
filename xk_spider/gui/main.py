"""
程序入口
云南大学选课助手 - 纯API版本
支持自动重启和监控状态恢复
"""
import sys
import os
import time
import subprocess
import traceback
import threading

from PyQt5.QtWidgets import QApplication, QProxyStyle, QStyle
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontDatabase

from .ui import MainWindow
from .config import MONITOR_STATE_FILE
from xk_spider.storage import LOG_DIR, read_json


class AppProxyStyle(QProxyStyle):
    """Fusion style with a normal-size password bullet."""

    def styleHint(self, hint, option=None, widget=None, return_data=None):
        if hint == QStyle.SH_LineEdit_PasswordCharacter:
            return ord('\u2022')
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return 2000
        fall_asleep_hint = getattr(QStyle, 'SH_ToolTip_FallAsleepDelay', None)
        if fall_asleep_hint is not None and hint == fall_asleep_hint:
            # Require the full wake-up delay again after leaving a control,
            # instead of making the next control's tip appear immediately.
            return 0
        return super().styleHint(hint, option, widget, return_data)


def load_application_fonts():
    """Load the bundled HarmonyOS Sans SC faces in source and frozen modes."""
    if getattr(sys, 'frozen', False):
        resource_root = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        resource_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    font_dir = os.path.join(resource_root, 'assets', 'fonts', 'HarmonyOS_Sans_SC')
    loaded_families = []
    for filename in (
        'HarmonyOS_Sans_SC_Regular.ttf',
        'HarmonyOS_Sans_SC_Medium.ttf',
        'HarmonyOS_Sans_SC_Bold.ttf',
    ):
        font_id = QFontDatabase.addApplicationFont(os.path.join(font_dir, filename))
        if font_id >= 0:
            loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return loaded_families


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
    return read_json(MONITOR_STATE_FILE)


def log_crash(error):
    """记录崩溃日志"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        crash_log_file = os.path.join(
            LOG_DIR, f"crash_{time.strftime('%Y-%m-%d')}.log"
        )
        with open(crash_log_file, 'a', encoding='utf-8') as f:
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
        
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        rounding_policy = getattr(Qt, 'HighDpiScaleFactorRoundingPolicy', None)
        if rounding_policy and hasattr(QApplication, 'setHighDpiScaleFactorRoundingPolicy'):
            QApplication.setHighDpiScaleFactorRoundingPolicy(rounding_policy.PassThrough)

        app = QApplication(sys.argv)
        app.setStyle(AppProxyStyle('Fusion'))
        loaded_fonts = load_application_fonts()
        app_font = QFont(
            'HarmonyOS Sans SC' if loaded_fonts else 'Microsoft YaHei UI'
        )
        app_font.setPixelSize(14)
        app_font.setWeight(QFont.Medium)
        # Keep glyph stems aligned to physical pixels at 125%/150% scaling.
        app_font.setHintingPreference(QFont.PreferFullHinting)
        app.setFont(app_font)
        
        # 设置应用级别图标（任务栏图标）
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icon.ico'))
        if os.path.exists(icon_path):
            from PyQt5.QtGui import QIcon
            app.setWindowIcon(QIcon(icon_path))
        
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
    """主入口 - 重启由守护进程接管"""
    run_app()
    # 注意：重启逻辑已由 watchdog.pyw 守护进程接管
    # 主程序正常退出后，守护进程会检测 monitor_state.json
    # 如果监控状态为活跃，守护进程会自动重启主程序


if __name__ == '__main__':
    main()
