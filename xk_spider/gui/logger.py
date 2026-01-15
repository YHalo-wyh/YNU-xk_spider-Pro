"""
日志系统模块
支持文件持久化 + UI 显示
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


class AppLogger:
    """应用日志管理器"""
    
    _instance = None
    _initialized = False
    
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
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        
        # 文件 Handler（滚动日志，最大 5MB，保留 3 个备份）
        log_file = os.path.join(log_dir, 'run.log')
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # 格式化器
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
    
    def debug(self, msg):
        self.logger.debug(msg)
    
    def info(self, msg):
        self.logger.info(msg)
    
    def warning(self, msg):
        self.logger.warning(msg)
    
    def error(self, msg):
        self.logger.error(msg)
    
    def critical(self, msg):
        self.logger.critical(msg)


# 全局日志实例
app_logger = AppLogger()


def get_logger():
    """获取全局日志实例"""
    return app_logger
