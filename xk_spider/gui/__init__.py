"""
YNU选课助手 GUI 模块
纯API版本 - 模块化架构
"""
# ddddocr/onnxruntime must be loaded before PyQt5 on Windows.  Loading Qt's
# runtime DLLs first can make onnxruntime_pybind11_state fail to initialise,
# which previously disabled captcha OCR and was then misreported as a network
# error by the login retry loop.
from .utils import OCR_AVAILABLE
from .main import main
from .ui import MainWindow
from .workers import LoginWorker, MultiGrabWorker, CourseFetchWorker
from .config import COURSE_TYPES, COURSE_TYPE_MAP

__all__ = [
    'main',
    'MainWindow',
    'LoginWorker',
    'MultiGrabWorker', 
    'CourseFetchWorker',
    'COURSE_TYPES',
    'COURSE_TYPE_MAP',
    'OCR_AVAILABLE',
]
