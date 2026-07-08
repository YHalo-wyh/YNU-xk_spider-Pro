"""用户运行数据路径与安全写入工具。

程序文件可以被安装器覆盖；账号配置、待选课程和日志统一放在用户
AppData 中，避免升级安装或更换程序目录时丢失。
"""
import json
import os
import shutil
import sys
import threading
from pathlib import Path


APP_NAME = "YNU选课助手Pro"


def _get_data_dir():
    """返回与安装目录无关的用户数据目录。"""
    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / APP_NAME

    root = os.environ.get("XDG_CONFIG_HOME")
    if root:
        return Path(root) / APP_NAME
    return Path.home() / ".config" / APP_NAME


DATA_DIR = _get_data_dir()
CONFIG_FILE = DATA_DIR / "config.json"
MONITOR_STATE_FILE = DATA_DIR / "monitor_state.json"
WATCHDOG_SIGNAL_FILE = DATA_DIR / "watchdog_signal.json"
WATCHDOG_LOCK_FILE = DATA_DIR / "watchdog.lock"
LOG_DIR = DATA_DIR / "logs"
CRASH_LOG_FILE = LOG_DIR / "crash.log"


def ensure_data_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _legacy_data_dirs():
    """旧版本可能写入运行数据的目录，按优先级返回。"""
    candidates = [Path.cwd() / "xk_spider"]

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "xk_spider")
    else:
        candidates.append(Path(__file__).resolve().parent)

    result = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved != DATA_DIR.resolve() and resolved not in result:
            result.append(resolved)
    return result


def migrate_legacy_data():
    """首次运行新版本时复制旧账号配置和待选课程记录。"""
    ensure_data_dirs()
    migrated = []

    for filename, destination in (
        ("config.json", CONFIG_FILE),
        ("monitor_state.json", MONITOR_STATE_FILE),
    ):
        if destination.exists():
            continue
        for legacy_dir in _legacy_data_dirs():
            source = legacy_dir / filename
            if source.is_file():
                shutil.copy2(source, destination)
                migrated.append((source, destination))
                break

    return migrated


def read_json(path, default=None):
    try:
        with Path(path).open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError, TypeError):
        return default


def write_json_atomic(path, data):
    """先写临时文件再原子替换，避免异常退出留下半个 JSON。"""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


ensure_data_dirs()
