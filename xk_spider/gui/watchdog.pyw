"""
后台守护进程 - 监控主程序并在闪退时自动重启
使用 .pyw 后缀在 Windows 上无窗口运行

修复版本：支持打包后的 EXE 和开发模式
"""
import os
import sys
import time
import json
import subprocess
import psutil


# 配置
CHECK_INTERVAL = 3  # 检查间隔（秒）
RESTART_DELAY = 2   # 重启延迟（秒）
MAX_RESTART_ATTEMPTS = 5  # 最大重启次数（防止无限循环）
RESTART_COOLDOWN = 60  # 重启冷却时间（秒）


def get_base_dir():
    """获取程序基础目录（支持打包和开发模式）"""
    if getattr(sys, 'frozen', False):
        # 打包后的 EXE
        return os.path.dirname(sys.executable)
    else:
        # 开发模式
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def get_monitor_state_file():
    """获取监控状态文件路径"""
    base_dir = get_base_dir()
    if getattr(sys, 'frozen', False):
        return os.path.join(base_dir, '_internal', 'xk_spider', 'monitor_state.json')
    else:
        return os.path.join(base_dir, 'xk_spider', 'monitor_state.json')


def get_lock_file():
    """获取锁文件路径"""
    base_dir = get_base_dir()
    if getattr(sys, 'frozen', False):
        return os.path.join(base_dir, '_internal', 'xk_spider', 'watchdog.lock')
    else:
        return os.path.join(base_dir, 'xk_spider', 'watchdog.lock')


def get_log_dir():
    """获取日志目录"""
    base_dir = get_base_dir()
    return os.path.join(base_dir, 'logs')


def log(msg):
    """简单日志"""
    try:
        log_dir = get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'watchdog.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def is_another_watchdog_running():
    """检查是否有另一个守护进程在运行"""
    try:
        lock_file = get_lock_file()
        if os.path.exists(lock_file):
            with open(lock_file, 'r') as f:
                old_pid = int(f.read().strip())
            if psutil.pid_exists(old_pid) and old_pid != os.getpid():
                try:
                    proc = psutil.Process(old_pid)
                    if 'python' in proc.name().lower() or 'watchdog' in proc.name().lower():
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return False
    except Exception:
        return False


def write_lock_file():
    """写入锁文件"""
    try:
        lock_file = get_lock_file()
        os.makedirs(os.path.dirname(lock_file), exist_ok=True)
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def remove_lock_file():
    """删除锁文件"""
    try:
        lock_file = get_lock_file()
        if os.path.exists(lock_file):
            os.remove(lock_file)
    except Exception:
        pass


def load_monitor_state():
    """加载监控状态"""
    try:
        state_file = get_monitor_state_file()
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                # 检查时间戳，如果状态文件太旧（超过1小时），认为无效
                timestamp = state.get('timestamp', 0)
                if time.time() - timestamp > 3600:
                    log(f"监控状态文件过期 (超过1小时)，忽略")
                    return None
                return state
    except Exception as e:
        log(f"加载监控状态失败: {e}")
    return None


def find_main_exe():
    """查找主程序 EXE 路径"""
    base_dir = get_base_dir()
    
    if getattr(sys, 'frozen', False):
        # 打包模式：查找同目录下的主 EXE
        exe_name = "YNU选课助手Pro.exe"
        exe_path = os.path.join(base_dir, exe_name)
        if os.path.exists(exe_path):
            return exe_path
    else:
        # 开发模式：返回 run_gui.py 路径
        script_path = os.path.join(base_dir, 'run_gui.py')
        if os.path.exists(script_path):
            return script_path
    
    return None


def start_main_program():
    """启动主程序"""
    try:
        main_exe = find_main_exe()
        if not main_exe:
            log("找不到主程序")
            return False, None
        
        if getattr(sys, 'frozen', False):
            # 打包模式：直接运行 EXE
            proc = subprocess.Popen(
                [main_exe],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                start_new_session=True,
                cwd=get_base_dir()
            )
        else:
            # 开发模式：通过 Python 运行脚本
            python = sys.executable
            proc = subprocess.Popen(
                [python, main_exe],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                start_new_session=True,
                cwd=get_base_dir()
            )
        
        log(f"已启动主程序: {main_exe}, PID: {proc.pid}")
        return True, proc.pid
        
    except Exception as e:
        log(f"启动主程序失败: {e}")
        return False, None


def watchdog_loop(main_pid):
    """守护进程主循环"""
    log(f"守护进程启动，监控 PID: {main_pid}")
    
    restart_count = 0
    last_restart_time = 0
    
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            
            # 检查主程序是否还在运行
            if psutil.pid_exists(main_pid):
                try:
                    proc = psutil.Process(main_pid)
                    if proc.status() != psutil.STATUS_ZOMBIE:
                        continue  # 主程序正常运行
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # 主程序已退出，检查是否需要重启
            log(f"检测到主程序 (PID: {main_pid}) 已退出")
            
            # 重新加载监控状态（每次都重新读取，确保是最新的）
            state = load_monitor_state()
            
            if not state or not state.get('is_monitoring'):
                log("监控状态为非活跃或不存在，守护进程退出")
                break
            
            # 检查重启限制
            current_time = time.time()
            if current_time - last_restart_time < RESTART_COOLDOWN:
                restart_count += 1
            else:
                restart_count = 1  # 重置计数
            
            if restart_count > MAX_RESTART_ATTEMPTS:
                log(f"重启次数过多 ({restart_count}/{MAX_RESTART_ATTEMPTS})，守护进程退出")
                break
            
            log(f"监控状态为活跃，准备重启主程序... (尝试 {restart_count}/{MAX_RESTART_ATTEMPTS})")
            time.sleep(RESTART_DELAY)
            
            success, new_pid = start_main_program()
            if success and new_pid:
                log(f"主程序已重启，新 PID: {new_pid}")
                main_pid = new_pid
                last_restart_time = current_time
            else:
                log("重启主程序失败")
                
        except Exception as e:
            log(f"守护循环异常: {e}")
            time.sleep(CHECK_INTERVAL)
    
    # 清理
    remove_lock_file()
    log("守护进程退出")


def main():
    """守护进程入口"""
    # 检查是否已有守护进程运行
    if is_another_watchdog_running():
        return  # 静默退出，不重复启动
    
    # 写入锁文件
    write_lock_file()
    
    try:
        # 获取主程序 PID
        if len(sys.argv) > 1:
            main_pid = int(sys.argv[1])
        else:
            log("未提供主程序 PID，守护进程退出")
            remove_lock_file()
            return
        
        # 验证 PID 是否有效
        if not psutil.pid_exists(main_pid):
            log(f"PID {main_pid} 不存在，守护进程退出")
            remove_lock_file()
            return
        
        # 进入守护循环
        watchdog_loop(main_pid)
        
    except Exception as e:
        log(f"守护进程异常: {e}")
    finally:
        remove_lock_file()


if __name__ == '__main__':
    main()
