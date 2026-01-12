# Core modules for YNU-xk_spider
from .config_manager import ConfigManager
from .http_login import HttpLogin, ManualCredentials, test_credentials

# 可选导入 Selenium 相关模块
try:
    from .auto_login import AutoLoginWorker
except ImportError:
    AutoLoginWorker = None

try:
    from .course_grabber import CourseGrabberWorker
except ImportError:
    CourseGrabberWorker = None

__all__ = ['ConfigManager', 'HttpLogin', 'ManualCredentials', 'test_credentials', 
           'AutoLoginWorker', 'CourseGrabberWorker']
