"""
日志系统模块
支持按日期轮转 + 保留策略 + 崩溃/重启可追溯
"""
import os
import sys
import glob
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta


class AppLogger:
    """
    应用日志管理器
    
    日志特性：
    - 按日期轮转：每天一个日志文件
    - 文件名格式：run_YYYY-MM-DD.log
    - 保留策略：保留最近 7 天的日志
    - 崩溃可追溯：每次启动记录启动信息
    """
    
    _instance = None
    _initialized = False
    
    # 配置
    LOG_DIR = 'logs'
    LOG_FILE_PREFIX = 'run'
    RETENTION_DAYS = 7  # 保留最近7天的日志
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if AppLogger._initialized:
            return
        
        AppLogger._initialized = True
        self.logger = logging.getLogger('xk_spider')
        self.logger.setLevel(logging.DEBUG)
        
        # 防止重复添加 handler
        if self.logger.handlers:
            return
        
        # 确保日志目录存在
        self._ensure_log_dir()
        
        # 设置按日期轮转的文件 Handler
        self._setup_file_handler()
        
        # 清理过期日志
        self._cleanup_old_logs()
        
        # 记录启动信息（便于追溯重启）
        self._log_startup()
    
    def _ensure_log_dir(self):
        """确保日志目录存在"""
        try:
            os.makedirs(self.LOG_DIR, exist_ok=True)
        except Exception:
            pass
    
    def _get_log_file_path(self):
        """获取当前日志文件路径"""
        today = datetime.now().strftime('%Y-%m-%d')
        return os.path.join(self.LOG_DIR, f'{self.LOG_FILE_PREFIX}_{today}.log')
    
    def _setup_file_handler(self):
        """设置按日期轮转的文件 Handler"""
        try:
            log_file = self._get_log_file_path()
            
            # 使用 TimedRotatingFileHandler 实现按日期轮转
            # 但由于我们使用自定义文件名（包含日期），这里用普通 FileHandler
            # 并在每天第一次写入时自动切换文件
            file_handler = logging.FileHandler(
                log_file,
                mode='a',  # 追加模式
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            
            # 格式化器：包含时间、级别、消息
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] %(message)s',
                datefmt='%H:%M:%S'  # 只显示时间，因为日期已在文件名中
            )
            file_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            self._current_date = datetime.now().date()
            self._file_handler = file_handler
        except Exception as e:
            # 日志系统初始化失败不应影响程序运行
            print(f"日志系统初始化失败: {e}")
    
    def _check_date_rotation(self):
        """检查是否需要切换到新日期的日志文件"""
        try:
            today = datetime.now().date()
            if hasattr(self, '_current_date') and today != self._current_date:
                # 日期变更，切换日志文件
                self._current_date = today
                
                # 移除旧 handler
                if hasattr(self, '_file_handler') and self._file_handler:
                    self.logger.removeHandler(self._file_handler)
                    self._file_handler.close()
                
                # 添加新 handler
                self._setup_file_handler()
                self._log_startup()
                
                # 清理过期日志
                self._cleanup_old_logs()
        except Exception:
            pass
    
    def _cleanup_old_logs(self):
        """清理过期日志文件"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.RETENTION_DAYS)
            pattern = os.path.join(self.LOG_DIR, f'{self.LOG_FILE_PREFIX}_*.log')
            
            for log_file in glob.glob(pattern):
                try:
                    # 从文件名解析日期
                    filename = os.path.basename(log_file)
                    # 格式: run_YYYY-MM-DD.log
                    date_str = filename.replace(f'{self.LOG_FILE_PREFIX}_', '').replace('.log', '')
                    file_date = datetime.strptime(date_str, '%Y-%m-%d')
                    
                    if file_date < cutoff_date:
                        os.remove(log_file)
                except (ValueError, OSError):
                    # 无法解析日期或删除失败，跳过
                    pass
        except Exception:
            pass
    
    def _log_startup(self):
        """记录启动信息（便于追溯重启和崩溃）"""
        try:
            separator = "=" * 60
            self.logger.info(separator)
            self.logger.info(f"程序启动 | PID: {os.getpid()}")
            self.logger.info(f"Python: {sys.version.split()[0]} | 平台: {sys.platform}")
            if getattr(sys, 'frozen', False):
                self.logger.info(f"运行模式: 打包版 | 路径: {sys.executable}")
            else:
                self.logger.info(f"运行模式: 开发版 | 路径: {os.getcwd()}")
            self.logger.info(separator)
        except Exception:
            pass
    
    def _log(self, level, msg):
        """内部日志方法，自动检查日期轮转"""
        self._check_date_rotation()
        getattr(self.logger, level)(msg)
    
    def debug(self, msg):
        self._log('debug', msg)
    
    def info(self, msg):
        self._log('info', msg)
    
    def warning(self, msg):
        self._log('warning', msg)
    
    def error(self, msg):
        self._log('error', msg)
    
    def critical(self, msg):
        self._log('critical', msg)


# 全局日志实例
app_logger = AppLogger()


def get_logger():
    """获取全局日志实例"""
    return app_logger
