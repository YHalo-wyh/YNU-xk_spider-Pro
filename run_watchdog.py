"""
守护进程启动器 - 用于打包成独立 EXE
主程序会调用这个 EXE 来启动守护进程

更新日志：
- 支持图标
- 改进日志系统：按日期轮转 + 7天保留 + 重启可追溯
"""
import os
import sys
import time
import json
import glob
import subprocess
import psutil
from datetime import datetime, timedelta


# 配置
CHECK_INTERVAL = 5  # 检查间隔（秒）
RESTART_DELAY = 3   # 重启延迟（秒）
MAX_RESTART_ATTEMPTS = 3  # 短时间内最大重启次数
RESTART_COOLDOWN = 120  # 重启冷却时间（秒内超过最大次数则停止重启）

# 日志配置
RETENTION_DAYS = 7


def get_base_dir():
    """获取程序基础目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def get_paths():
    """获取各种文件路径"""
    base = get_base_dir()
    if getattr(sys, 'frozen', False):
        # 打包模式：使用相对路径（与主程序一致）
        return {
            'state': os.path.join(base, 'xk_spider', 'monitor_state.json'),
            'lock': os.path.join(base, 'xk_spider', 'watchdog.lock'),
            'log_dir': os.path.join(base, 'logs'),
            'main_exe': os.path.join(base, 'YNU选课助手Pro.exe'),
        }
    else:
        return {
            'state': os.path.join(base, 'xk_spider', 'monitor_state.json'),
            'lock': os.path.join(base, 'xk_spider', 'watchdog.lock'),
            'log_dir': os.path.join(base, 'logs'),
            'main_exe': os.path.join(base, 'run_gui.py'),
        }


def get_log_file():
    """获取当前日期的日志文件路径"""
    paths = get_paths()
    log_dir = paths['log_dir']
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(log_dir, f'watchdog_{today}.log')


def cleanup_old_logs():
    """清理过期日志"""
    try:
        paths = get_paths()
        log_dir = paths['log_dir']
        cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
        pattern = os.path.join(log_dir, 'watchdog_*.log')
        
        for log_file in glob.glob(pattern):
            try:
                filename = os.path.basename(log_file)
                # 格式: watchdog_YYYY-MM-DD.log
                date_str = filename.replace('watchdog_', '').replace('.log', '')
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                
                if file_date < cutoff_date:
                    os.remove(log_file)
            except (ValueError, OSError):
                pass
    except Exception:
        pass


def log(msg):
    """写入日志（按日期轮转）"""
    try:
        log_file = get_log_file()
        timestamp = datetime.now().strftime('%H:%M:%S')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass


def log_startup(main_pid):
    """记录启动信息"""
    cleanup_old_logs()
    
    separator = "=" * 50
    log(separator)
    log(f"守护进程启动 | Watchdog PID: {os.getpid()}")
    log(f"监控目标 PID: {main_pid}")
    log(separator)


def is_another_running():
    """检查是否有另一个守护进程"""
    try:
        paths = get_paths()
        if os.path.exists(paths['lock']):
            with open(paths['lock'], 'r') as f:
                old_pid = int(f.read().strip())
            if psutil.pid_exists(old_pid) and old_pid != os.getpid():
                # 检查进程名确认是否是 Watchdog
                try:
                    proc = psutil.Process(old_pid)
                    name = proc.name().lower()
                    if 'python' in name or 'watchdog' in name:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    except Exception:
        pass
    return False


def write_lock():
    """写入锁文件"""
    try:
        paths = get_paths()
        os.makedirs(os.path.dirname(paths['lock']), exist_ok=True)
        with open(paths['lock'], 'w') as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def remove_lock():
    """删除锁文件"""
    try:
        paths = get_paths()
        if os.path.exists(paths['lock']):
            os.remove(paths['lock'])
    except Exception:
        pass


def load_state():
    """加载监控状态"""
    try:
        paths = get_paths()
        if os.path.exists(paths['state']):
            with open(paths['state'], 'r', encoding='utf-8') as f:
                state = json.load(f)
            # 状态超过2小时视为无效
            if time.time() - state.get('timestamp', 0) > 7200:
                return None
            return state
    except Exception:
        pass
    return None


def start_main():
    """启动主程序"""
    try:
        paths = get_paths()
        main_exe = paths['main_exe']
        
        if not os.path.exists(main_exe):
            log(f"主程序不存在: {main_exe}")
            return None
        
        if getattr(sys, 'frozen', False):
            # 打包模式：直接运行 EXE
            proc = subprocess.Popen(
                [main_exe],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                start_new_session=True,
                cwd=get_base_dir()
            )
        else:
            # 开发模式
            proc = subprocess.Popen(
                [sys.executable, main_exe],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
                start_new_session=True,
                cwd=get_base_dir()
            )
        
        log(f"重启主程序成功，新 PID: {proc.pid}")
        return proc.pid
    except Exception as e:
        log(f"启动主程序失败: {e}")
        return None


def main_loop(main_pid):
    """守护循环"""
    restart_times = []  # 记录重启时间
    
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            
            # 检查主程序是否存活
            if psutil.pid_exists(main_pid):
                try:
                    proc = psutil.Process(main_pid)
                    if proc.status() != psutil.STATUS_ZOMBIE:
                        continue  # 运行正常
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # 主程序已退出
            log(f"检测到主程序 (PID: {main_pid}) 已退出")
            
            # 检查是否需要重启
            state = load_state()
            if not state or not state.get('is_monitoring'):
                log("监控状态为非活跃，守护进程退出")
                break
            
            # 检查重启频率（防止无限重启）
            now = time.time()
            restart_times = [t for t in restart_times if now - t < RESTART_COOLDOWN]
            
            if len(restart_times) >= MAX_RESTART_ATTEMPTS:
                log(f"重启过于频繁 ({len(restart_times)} 次/{RESTART_COOLDOWN}秒)，停止重启")
                # 记录详细错误以便用户反馈
                log("请检查主程序 logs 目录下的崩溃日志")
                break
            
            # 执行重启
            log(f"准备重启主程序 ({len(restart_times)+1}/{MAX_RESTART_ATTEMPTS})...")
            time.sleep(RESTART_DELAY)
            
            new_pid = start_main()
            if new_pid:
                main_pid = new_pid
                restart_times.append(now)
            else:
                log("重启失败，退出守护")
                break
                
        except Exception as e:
            log(f"守护循环异常: {e}")
            time.sleep(CHECK_INTERVAL)
    
    remove_lock()
    log("守护进程结束")


def main():
    """入口"""
    if is_another_running():
        return
    
    write_lock()
    
    try:
        if len(sys.argv) > 1:
            main_pid = int(sys.argv[1])
            if not psutil.pid_exists(main_pid):
                # 记录一下，虽然这时候日志系统可能还没怎么初始化，但 get_log_file 会处理
                log(f"启动参数错误：PID {main_pid} 不存在")
                remove_lock()
                return
        else:
            log("未提供主程序 PID")
            remove_lock()
            return
        
        # 记录启动信息
        log_startup(main_pid)
        
        main_loop(main_pid)
    except Exception as e:
        log(f"未捕获异常: {e}")
    finally:
        remove_lock()


if __name__ == '__main__':
    main()
