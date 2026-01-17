"""
用户界面模块 - View
Modern Dark Dashboard 风格 (Catppuccin Mocha 配色)
"""
import os
import json
import time

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QTextEdit, QProgressBar, QMessageBox, QFrame, QGridLayout, QSizePolicy,
    QSpinBox, QScrollArea, QCheckBox, QSplitter, QApplication, QMenu,
    QGraphicsDropShadowEffect, QMenuBar, QAction, QDialog, QDialogButtonBox,
    QProgressDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtProperty, QUrl
from PyQt5.QtGui import QFont, QPainter, QColor, QTextCursor, QDesktopServices

from .config import COURSE_TYPES, COURSE_NAME_TO_TYPE, parse_int
from .utils import OCR_AVAILABLE
from .workers import LoginWorker, MultiGrabWorker, CourseFetchWorker, UpdateCheckWorker
from .logger import get_logger


# ========== Catppuccin Mocha 配色方案 ==========
class Colors:
    # 背景色
    BASE = "#1e1e2e"        # 主背景
    MANTLE = "#181825"      # 更深背景
    CRUST = "#11111b"       # 最深背景
    SURFACE0 = "#313244"    # 卡片背景
    SURFACE1 = "#45475a"    # 悬浮背景
    SURFACE2 = "#585b70"    # 边框
    
    # 文字色
    TEXT = "#cdd6f4"        # 主文字
    SUBTEXT1 = "#bac2de"    # 次要文字
    SUBTEXT0 = "#a6adc8"    # 更次要
    OVERLAY0 = "#6c7086"    # 占位符
    
    # 主色调
    BLUE = "#89b4fa"        # 主色
    LAVENDER = "#b4befe"    # 淡紫
    SAPPHIRE = "#74c7ec"    # 蓝绿
    
    # 状态色
    GREEN = "#a6e3a1"       # 成功/已选
    RED = "#f38ba8"         # 错误/已满
    YELLOW = "#f9e2af"      # 警告/冲突
    PEACH = "#fab387"       # 橙色强调
    MAUVE = "#cba6f7"       # 紫色强调


# ========== 全局样式表 ==========
GLOBAL_STYLESHEET = f"""
/* ===== 基础样式 ===== */
QMainWindow, QWidget {{
    background-color: {Colors.BASE};
    color: {Colors.TEXT};
    font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 14px;
}}

/* ===== 输入框 ===== */
QLineEdit, QComboBox, QSpinBox {{
    background-color: {Colors.MANTLE};
    border: 2px solid {Colors.SURFACE2};
    border-radius: 8px;
    padding: 10px 14px;
    color: {Colors.TEXT};
    font-size: 14px;
    selection-background-color: {Colors.BLUE};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {Colors.BLUE};
    background-color: {Colors.BASE};
    border-width: 2px;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
    border-color: {Colors.SURFACE1};
    background-color: #1a1a2e;
}}
QLineEdit::placeholder {{
    color: {Colors.OVERLAY0};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 10px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {Colors.SUBTEXT0};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {Colors.SURFACE0};
    border: 1px solid {Colors.SURFACE2};
    border-radius: 8px;
    selection-background-color: {Colors.SURFACE1};
    outline: none;
}}

/* ===== 按钮 ===== */
QPushButton {{
    background-color: {Colors.BLUE};
    color: {Colors.CRUST};
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: bold;
    font-size: 14px;
}}
QPushButton:hover {{
    background-color: {Colors.LAVENDER};
    margin-top: -1px;
    margin-bottom: 1px;
}}
QPushButton:pressed {{
    background-color: {Colors.SAPPHIRE};
    margin-top: 1px;
    margin-bottom: -1px;
}}
QPushButton:disabled {{
    background-color: {Colors.SURFACE2};
    color: {Colors.OVERLAY0};
}}

/* ===== 列表 ===== */
QListWidget {{
    background-color: {Colors.MANTLE};
    border: 2px solid {Colors.SURFACE2};
    border-radius: 10px;
    padding: 6px;
    outline: none;
}}
QListWidget::item {{
    background-color: transparent;
    border-radius: 8px;
    padding: 12px 14px;
    margin: 3px 0;
    color: {Colors.TEXT};
    font-size: 14px;
}}
QListWidget::item:hover {{
    background-color: {Colors.SURFACE0};
}}
QListWidget::item:selected {{
    background-color: {Colors.SURFACE1};
    border-left: 4px solid {Colors.BLUE};
    padding-left: 10px;
}}

/* ===== 文本框 (终端风格) ===== */
QTextEdit {{
    background-color: {Colors.CRUST};
    color: {Colors.GREEN};
    border: 2px solid {Colors.SURFACE2};
    border-radius: 10px;
    padding: 12px;
    font-family: "Consolas", "JetBrains Mono", "Cascadia Code", monospace;
    font-size: 12px;
    line-height: 1.4;
    selection-background-color: {Colors.SURFACE1};
}}

/* ===== 进度条 ===== */
QProgressBar {{
    background-color: {Colors.SURFACE0};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {Colors.BLUE};
    border-radius: 4px;
}}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{
    background-color: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background-color: {Colors.SURFACE2};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {Colors.OVERLAY0};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background-color: transparent;
    height: 10px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background-color: {Colors.SURFACE2};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {Colors.OVERLAY0};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ===== 滚动区域 ===== */
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

/* ===== 框架 ===== */
QFrame {{
    background-color: {Colors.SURFACE0};
    border: none;
    border-radius: 12px;
}}

/* ===== 标签 ===== */
QLabel {{
    background-color: transparent;
    color: {Colors.TEXT};
}}

/* ===== 分割器 ===== */
QSplitter::handle {{
    background-color: {Colors.SURFACE2};
    margin: 0 4px;
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}

/* ===== 状态栏 ===== */
QStatusBar {{
    background-color: {Colors.MANTLE};
    color: {Colors.SUBTEXT0};
    border-top: 1px solid {Colors.SURFACE2};
}}

/* ===== 菜单 ===== */
QMenu {{
    background-color: {Colors.SURFACE0};
    border: 1px solid {Colors.SURFACE2};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {Colors.SURFACE1};
}}

/* ===== 消息框 ===== */
QMessageBox {{
    background-color: {Colors.BASE};
}}
QMessageBox QLabel {{
    color: {Colors.TEXT};
    font-size: 14px;
}}
"""


class AnimatedToggle(QCheckBox):
    """动画切换开关 - 现代风格"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 28)
        self.setCursor(Qt.PointingHandCursor)
        self._circle_position = 4
        from PyQt5.QtCore import QPropertyAnimation, QEasingCurve
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.setDuration(200)
        self.stateChanged.connect(self.start_transition)
    
    def get_circle_position(self):
        return self._circle_position
    
    def set_circle_position(self, pos):
        self._circle_position = pos
        self.update()
    
    circle_position = pyqtProperty(float, fget=get_circle_position, fset=set_circle_position)
    
    def start_transition(self, state):
        self.animation.stop()
        if state:
            self.animation.setEndValue(self.width() - 24)
        else:
            self.animation.setEndValue(4)
        self.animation.start()
    
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        # 背景
        bg_color = QColor(Colors.BLUE) if self.isChecked() else QColor(Colors.SURFACE2)
        p.setBrush(bg_color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        
        # 圆形滑块
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(int(self._circle_position), 4, 20, 20)
    
    def hitButton(self, pos):
        return self.rect().contains(pos)


class CourseCard(QFrame):
    """课程卡片 - 现代宽卡片设计"""
    grab_clicked = pyqtSignal(dict)
    
    def __init__(self, course_data, parent=None):
        super().__init__(parent)
        self.course_data = course_data
        self.init_ui()
        
    def init_ui(self):
        self.setMinimumWidth(280)
        self.setMaximumWidth(450)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # 添加卡片阴影效果
        card_shadow = QGraphicsDropShadowEffect()
        card_shadow.setBlurRadius(15)
        card_shadow.setColor(QColor(0, 0, 0, 80))
        card_shadow.setOffset(0, 3)
        self.setGraphicsEffect(card_shadow)
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)
        
        is_conflict = self.course_data.get('isConflict', False)
        is_chosen = self.course_data.get('isChosen', False)
        is_full = self.course_data.get('isFull', False)
        
        # 状态标签
        if is_chosen or is_full:
            status_layout = QHBoxLayout()
            if is_chosen:
                status_label = QLabel("✓ 已选")
                status_label.setStyleSheet(f"""
                    font-size: 13px; font-weight: bold; 
                    color: {Colors.CRUST}; 
                    background-color: {Colors.GREEN}; 
                    padding: 4px 12px; border-radius: 12px;
                """)
            else:
                status_label = QLabel("已满")
                status_label.setStyleSheet(f"""
                    font-size: 13px; font-weight: bold; 
                    color: {Colors.CRUST}; 
                    background-color: {Colors.RED}; 
                    padding: 4px 12px; border-radius: 12px;
                """)
            status_layout.addWidget(status_label)
            status_layout.addStretch()
            layout.addLayout(status_layout)
        
        # 教师名称 - 大号加粗
        teacher = self.course_data.get('SKJS', '未知')
        teacher_label = QLabel(f"👨‍🏫 {teacher}")
        teacher_label.setStyleSheet(f"""
            font-size: 18px; font-weight: bold; 
            color: {Colors.TEXT};
            padding: 4px 0;
        """)
        layout.addWidget(teacher_label)
        
        # 上课时间
        time_str = self.course_data.get('SKSJ', '')
        if time_str:
            time_label = QLabel(f"🕐 {time_str}")
            time_label.setStyleSheet(f"""
                font-size: 13px; 
                color: {Colors.SAPPHIRE};
                padding: 2px 0;
            """)
            time_label.setWordWrap(True)
            layout.addWidget(time_label)
        
        # 容量信息
        selected = parse_int(self.course_data.get('YXRS', 0))
        capacity = parse_int(self.course_data.get('KRL', 0))
        remain = capacity - selected
        
        # 容量标签
        cap_layout = QHBoxLayout()
        cap_layout.setSpacing(16)
        
        selected_label = QLabel(f"已选 {selected}")
        selected_label.setStyleSheet(f"font-size: 14px; color: {Colors.SUBTEXT1};")
        cap_layout.addWidget(selected_label)
        
        capacity_label = QLabel(f"容量 {capacity}")
        capacity_label.setStyleSheet(f"font-size: 14px; color: {Colors.SUBTEXT1};")
        cap_layout.addWidget(capacity_label)
        
        status_color = Colors.GREEN if remain > 0 else Colors.RED
        remain_label = QLabel(f"余量 {remain}")
        remain_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {status_color};")
        cap_layout.addWidget(remain_label)
        
        cap_layout.addStretch()
        layout.addLayout(cap_layout)
        
        # 进度条
        progress = QProgressBar()
        progress.setMaximum(capacity if capacity > 0 else 1)
        progress.setValue(selected)
        progress.setTextVisible(False)
        progress.setFixedHeight(6)
        progress.setStyleSheet(f"""
            QProgressBar {{ 
                background-color: {Colors.SURFACE2}; 
                border: none;
                border-radius: 3px; 
            }} 
            QProgressBar::chunk {{ 
                background-color: {status_color}; 
                border-radius: 3px; 
            }}
        """)
        layout.addWidget(progress)
        
        layout.addStretch()
        
        # 操作按钮
        grab_btn = QPushButton("🎯 加入待抢")
        grab_btn.setFixedHeight(40)
        grab_btn.setCursor(Qt.PointingHandCursor)
        
        if is_chosen:
            grab_btn.setEnabled(False)
            grab_btn.setText("✓ 已选中")
            grab_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.GREEN}; 
                    color: {Colors.CRUST}; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 10px;
                    font-size: 14px;
                }}
            """)
        elif is_full:
            grab_btn.setText("🎯 加入待抢 (满员)")
            grab_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.RED}; 
                    color: {Colors.CRUST}; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 10px;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background-color: #f5a0b4;
                }}
            """)
            grab_btn.clicked.connect(lambda: self.grab_clicked.emit(self.course_data))
        elif is_conflict:
            grab_btn.setText("⚠️ 加入待抢 (冲突)")
            grab_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.YELLOW}; 
                    color: {Colors.CRUST}; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 10px;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background-color: #fae8bc;
                }}
            """)
            grab_btn.clicked.connect(lambda: self.grab_clicked.emit(self.course_data))
        else:
            grab_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.BLUE}; 
                    color: {Colors.CRUST}; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 10px;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background-color: {Colors.LAVENDER};
                }}
            """)
            grab_btn.clicked.connect(lambda: self.grab_clicked.emit(self.course_data))
        
        layout.addWidget(grab_btn)
        
        # 卡片样式
        if is_chosen:
            border_color = Colors.GREEN
        elif is_full:
            border_color = Colors.RED
        elif is_conflict:
            border_color = Colors.YELLOW
        else:
            border_color = Colors.SURFACE2
        
        self.setStyleSheet(f"""
            CourseCard {{ 
                background-color: {Colors.SURFACE0}; 
                border: 2px solid {border_color}; 
                border-radius: 16px; 
            }}
            CourseCard:hover {{
                border-color: {Colors.BLUE};
                background-color: {Colors.SURFACE1};
            }}
        """)


class MainWindow(QMainWindow):
    """主窗口 - Modern Dark Dashboard"""
    
    # 版本信息
    VERSION = "1.5.0"
    GITHUB_URL = "https://github.com/YHalo-wyh/YNU-xk_spider-Pro"
    
    def __init__(self):
        super().__init__()
        self.is_logged_in = False
        self.token = ''
        self.batch_code = ''
        self.student_code = ''
        self.cookies = ''
        self.multi_grab_worker = None
        self._api_courses_grouped = {}
        self._pending_monitor_courses = []
        self._is_searching = False
        
        # Server酱配置
        self.serverchan_enabled = False
        self.serverchan_key = ''
        
        # 日志系统
        self._logger = get_logger()
        self._heartbeat_count = 0
        
        # 自动轮询 Timer
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._on_poll_timer)
        self._poll_interval = 4000
        
        # 课程获取 Worker
        self._course_fetch_worker = None
        self._fetch_silent = False
        
        self.init_ui()
        self.init_menu()
        self.load_config()
        self.adjust_for_screen()
    
    def adjust_for_screen(self):
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        width = int(screen_geo.width() * 0.88)
        height = int(screen_geo.height() * 0.88)
        width = max(width, 1100)
        height = max(height, 700)
        self.resize(width, height)
        x = screen_geo.x() + (screen_geo.width() - width) // 2
        y = screen_geo.y() + (screen_geo.height() - height) // 2
        self.move(x, y)
    
    def init_ui(self):
        self.setWindowTitle('YNU选课助手 Pro')
        self.setMinimumSize(1000, 650)
        self.setStyleSheet(GLOBAL_STYLESHEET)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # ===== 左侧面板：登录 + 课程列表 =====
        left_panel = QWidget()
        left_panel.setStyleSheet(f"background-color: {Colors.BASE};")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(0, 0, 8, 0)
        
        # 登录区域
        login_title = QLabel("🔐 登录")
        login_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Colors.BLUE}; padding: 4px 0;")
        left_layout.addWidget(login_title)
        
        self.login_frame = QFrame()
        self.login_frame.setStyleSheet(f"""
            QFrame {{ 
                background-color: {Colors.SURFACE0}; 
                border-radius: 12px; 
                border: none;
            }}
        """)
        login_layout = QVBoxLayout(self.login_frame)
        login_layout.setSpacing(10)
        login_layout.setContentsMargins(16, 16, 16, 16)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("学号")
        self.username_input.setFixedHeight(42)
        login_layout.addWidget(self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFixedHeight(42)
        login_layout.addWidget(self.password_input)
        
        batch_label = QLabel("📅 选课批次: 第二轮")
        batch_label.setStyleSheet(f"color: {Colors.SUBTEXT0}; font-size: 13px; padding: 4px 0;")
        login_layout.addWidget(batch_label)
        
        self.login_btn = QPushButton("🚀 一键登录")
        self.login_btn.setFixedHeight(44)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Colors.BLUE}, stop:1 {Colors.LAVENDER});
                color: {Colors.CRUST};
                border: none;
                border-radius: 10px;
                font-weight: bold;
                font-size: 15px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Colors.LAVENDER}, stop:1 {Colors.MAUVE});
                margin-top: -2px;
                margin-bottom: 2px;
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Colors.SAPPHIRE}, stop:1 {Colors.BLUE});
                margin-top: 1px;
                margin-bottom: -1px;
            }}
            QPushButton:disabled {{
                background: {Colors.SURFACE2};
                color: {Colors.OVERLAY0};
            }}
        """)
        # 添加发光效果
        login_glow = QGraphicsDropShadowEffect()
        login_glow.setBlurRadius(20)
        login_glow.setColor(QColor(Colors.BLUE))
        login_glow.setOffset(0, 0)
        self.login_btn.setGraphicsEffect(login_glow)
        self.login_btn.clicked.connect(self.login)
        login_layout.addWidget(self.login_btn)
        
        self.logout_btn = QPushButton("退出登录")
        self.logout_btn.setFixedHeight(38)
        self.logout_btn.setCursor(Qt.PointingHandCursor)
        self.logout_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.RED};
                border: 2px solid {Colors.RED};
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.RED};
                color: {Colors.CRUST};
                margin-top: -1px;
            }}
            QPushButton:disabled {{
                border-color: {Colors.SURFACE2};
                color: {Colors.OVERLAY0};
            }}
        """)
        self.logout_btn.clicked.connect(self.logout)
        self.logout_btn.setEnabled(False)
        login_layout.addWidget(self.logout_btn)
        
        self.status_label = QLabel("● 未登录")
        self.status_label.setStyleSheet(f"color: {Colors.RED}; font-weight: bold; font-size: 13px; padding: 4px 0;")
        login_layout.addWidget(self.status_label)
        
        left_layout.addWidget(self.login_frame)
        
        # ===== Server酱微信通知配置 =====
        notify_frame = QFrame()
        notify_frame.setStyleSheet(f"""
            QFrame {{ 
                background-color: {Colors.SURFACE0}; 
                border-radius: 10px; 
                border: none;
            }}
        """)
        notify_layout = QVBoxLayout(notify_frame)
        notify_layout.setSpacing(8)
        notify_layout.setContentsMargins(14, 12, 14, 12)
        
        # 复选框
        self.serverchan_checkbox = QCheckBox("📱 微信通知 (Server酱)")
        self.serverchan_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {Colors.SUBTEXT1};
                font-size: 13px;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid {Colors.SURFACE2};
                background-color: {Colors.MANTLE};
            }}
            QCheckBox::indicator:checked {{
                background-color: {Colors.BLUE};
                border-color: {Colors.BLUE};
            }}
            QCheckBox::indicator:hover {{
                border-color: {Colors.BLUE};
            }}
        """)
        self.serverchan_checkbox.stateChanged.connect(self._on_serverchan_toggled)
        notify_layout.addWidget(self.serverchan_checkbox)
        
        # SendKey 输入框（默认隐藏）
        self.serverchan_key_input = QLineEdit()
        self.serverchan_key_input.setPlaceholderText("输入 SendKey")
        self.serverchan_key_input.setEchoMode(QLineEdit.Password)
        self.serverchan_key_input.setFixedHeight(38)
        self.serverchan_key_input.setVisible(False)
        self.serverchan_key_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Colors.MANTLE};
                border: 2px solid {Colors.SURFACE2};
                border-radius: 6px;
                padding: 6px 10px;
                color: {Colors.TEXT};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {Colors.BLUE};
            }}
        """)
        notify_layout.addWidget(self.serverchan_key_input)
        
        left_layout.addWidget(notify_frame)
        
        # 课程类型选择
        type_label = QLabel("📂 课程类型")
        type_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.SUBTEXT1}; padding-top: 8px;")
        left_layout.addWidget(type_label)
        
        self.course_type_combo = QComboBox()
        self.course_type_combo.setFixedHeight(42)
        self.course_type_combo.addItems(list(COURSE_TYPES.keys()))
        self.course_type_combo.currentTextChanged.connect(self.on_course_type_changed)
        left_layout.addWidget(self.course_type_combo)
        
        # 搜索框
        search_label = QLabel("🔍 搜索")
        search_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.SUBTEXT1}; padding-top: 8px;")
        left_layout.addWidget(search_label)
        
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("课程名 / 教师名")
        self.search_input.setFixedHeight(42)
        self.search_input.returnPressed.connect(self.on_search)
        search_layout.addWidget(self.search_input)
        
        self.search_btn = QPushButton("搜索")
        self.search_btn.setFixedSize(70, 42)
        self.search_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BLUE};
                color: {Colors.CRUST};
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {Colors.LAVENDER};
            }}
            QPushButton:pressed {{
                background-color: {Colors.SAPPHIRE};
            }}
        """)
        self.search_btn.clicked.connect(self.on_search)
        search_layout.addWidget(self.search_btn)
        left_layout.addLayout(search_layout)
        
        # 课程列表
        list_label = QLabel("📚 课程列表")
        list_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.SUBTEXT1}; padding-top: 8px;")
        left_layout.addWidget(list_label)
        
        self.course_list = QListWidget()
        self.course_list.itemClicked.connect(self.on_course_selected)
        left_layout.addWidget(self.course_list, 1)
        
        self.course_count_label = QLabel("共 0 门课程")
        self.course_count_label.setStyleSheet(f"color: {Colors.OVERLAY0}; font-size: 13px;")
        left_layout.addWidget(self.course_count_label)
        
        splitter.addWidget(left_panel)
        
        # ===== 中间面板：课程卡片 =====
        middle_panel = QWidget()
        middle_panel.setStyleSheet(f"background-color: {Colors.BASE};")
        middle_layout = QVBoxLayout(middle_panel)
        middle_layout.setContentsMargins(8, 0, 8, 0)
        middle_layout.setSpacing(12)
        
        self.schedule_title = QLabel("📅 选择课程查看教学班")
        self.schedule_title.setStyleSheet(f"""
            font-size: 18px; font-weight: bold; 
            color: {Colors.LAVENDER}; 
            padding: 8px 0;
        """)
        middle_layout.addWidget(self.schedule_title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        cards_widget = QWidget()
        cards_widget.setStyleSheet("background-color: transparent;")
        self.cards_layout = QGridLayout(cards_widget)
        self.cards_layout.setSpacing(16)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(cards_widget)
        middle_layout.addWidget(scroll)
        
        splitter.addWidget(middle_panel)
        
        # ===== 右侧面板：待抢列表 + 日志 =====
        right_panel = QWidget()
        right_panel.setStyleSheet(f"background-color: {Colors.BASE};")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)
        
        grab_title = QLabel("🎯 待抢列表")
        grab_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Colors.PEACH}; padding: 4px 0;")
        right_layout.addWidget(grab_title)
        
        self.grab_list = QListWidget()
        self.grab_list.setMaximumHeight(200)
        self.grab_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grab_list.customContextMenuRequested.connect(self.show_grab_context_menu)
        right_layout.addWidget(self.grab_list)
        
        self.grab_count_label = QLabel("待抢: 0 门")
        self.grab_count_label.setStyleSheet(f"color: {Colors.PEACH}; font-weight: bold; font-size: 13px;")
        right_layout.addWidget(self.grab_count_label)
        
        # 并发数设置
        concurrency_frame = QFrame()
        concurrency_frame.setStyleSheet(f"background-color: {Colors.SURFACE0}; border-radius: 10px;")
        concurrency_layout = QHBoxLayout(concurrency_frame)
        concurrency_layout.setContentsMargins(14, 10, 14, 10)
        
        conc_label = QLabel("⚡ 并发数")
        conc_label.setStyleSheet(f"color: {Colors.SUBTEXT1}; font-size: 14px;")
        concurrency_layout.addWidget(conc_label)
        
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 20)
        self.concurrency_spin.setValue(5)
        self.concurrency_spin.setFixedWidth(70)
        self.concurrency_spin.setToolTip("同时监控的线程数量（建议 3-10）")
        concurrency_layout.addWidget(self.concurrency_spin)
        concurrency_layout.addStretch()
        right_layout.addWidget(concurrency_frame)
        
        # 控制按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.start_grab_btn = QPushButton("▶ 开始监控")
        self.start_grab_btn.setFixedHeight(44)
        self.start_grab_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.GREEN};
                color: {Colors.CRUST};
                font-weight: bold;
                border-radius: 10px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: #b5e8b0;
            }}
            QPushButton:disabled {{
                background-color: {Colors.SURFACE2};
                color: {Colors.OVERLAY0};
            }}
        """)
        self.start_grab_btn.clicked.connect(self.start_monitoring)
        btn_layout.addWidget(self.start_grab_btn)
        
        self.stop_grab_btn = QPushButton("⏹ 停止")
        self.stop_grab_btn.setFixedHeight(44)
        self.stop_grab_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.RED};
                color: {Colors.CRUST};
                font-weight: bold;
                border-radius: 10px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: #f5a0b4;
            }}
            QPushButton:disabled {{
                background-color: {Colors.SURFACE2};
                color: {Colors.OVERLAY0};
            }}
        """)
        self.stop_grab_btn.clicked.connect(self.stop_monitoring)
        self.stop_grab_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_grab_btn)
        right_layout.addLayout(btn_layout)
        
        # 日志区域
        log_title = QLabel("📋 运行日志")
        log_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.SUBTEXT1}; padding-top: 12px;")
        right_layout.addWidget(log_title)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        right_layout.addWidget(self.log_text, 1)
        
        splitter.addWidget(right_panel)
        
        # 设置分割比例：左 1.5 : 中 4 : 右 1.8
        splitter.setStretchFactor(0, 15)
        splitter.setStretchFactor(1, 40)
        splitter.setStretchFactor(2, 18)
        splitter.setSizes([220, 550, 230])
        
        main_layout.addWidget(splitter)
        
        # 状态栏进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        
        # 心跳指示器 (胶囊状)
        self.run_indicator = QLabel("● 待机")
        self.run_indicator.setStyleSheet(f"""
            QLabel {{
                color: {Colors.OVERLAY0};
                background-color: {Colors.SURFACE0};
                font-size: 13px;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 14px;
                margin: 2px 8px;
            }}
        """)
        self.statusBar().addPermanentWidget(self.run_indicator)
    
    def init_menu(self):
        """初始化菜单栏"""
        menubar = self.menuBar()
        menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {Colors.MANTLE};
                color: {Colors.TEXT};
                padding: 4px 8px;
                border-bottom: 1px solid {Colors.SURFACE2};
            }}
            QMenuBar::item {{
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QMenuBar::item:selected {{
                background-color: {Colors.SURFACE1};
            }}
        """)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        # 检查更新
        update_action = QAction("🔄 检查更新", self)
        update_action.triggered.connect(self._check_update)
        help_menu.addAction(update_action)
        
        help_menu.addSeparator()
        
        # 关于
        about_action = QAction("ℹ️ 关于", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
    
    def _open_github(self):
        """打开 GitHub 仓库"""
        QDesktopServices.openUrl(QUrl(self.GITHUB_URL))
    
    def _check_update(self):
        """检查更新 - 使用 UpdateCheckWorker"""
        # 显示检查中的提示
        self._update_check_dialog = QProgressDialog("正在检查更新，请稍候...", "取消", 0, 0, self)
        self._update_check_dialog.setWindowTitle("检查更新")
        self._update_check_dialog.setWindowModality(Qt.WindowModal)
        self._update_check_dialog.setMinimumWidth(350)
        self._update_check_dialog.setMinimumHeight(100)
        self._update_check_dialog.setMinimumDuration(0)
        self._update_check_dialog.setAutoClose(False)
        self._update_check_dialog.setStyleSheet(f"""
            QProgressDialog {{
                background-color: {Colors.BASE};
            }}
            QLabel {{
                color: {Colors.TEXT};
                font-size: 14px;
            }}
            QPushButton {{
                background-color: {Colors.SURFACE0};
                color: {Colors.TEXT};
                border: 1px solid {Colors.SURFACE2};
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE1};
            }}
        """)
        self._update_check_dialog.canceled.connect(self._on_update_check_canceled)
        self._update_check_dialog.show()
        
        self.statusBar().showMessage("正在检查更新...")
        
        # 启动后台 Worker
        self._update_check_worker = UpdateCheckWorker(self.VERSION)
        self._update_check_worker.finished.connect(self._on_update_checked)
        self._update_check_worker.start()
    
    def _on_update_check_canceled(self):
        """用户取消检查更新"""
        if hasattr(self, '_update_check_worker') and self._update_check_worker:
            try:
                self._update_check_worker.finished.disconnect()
            except TypeError:
                pass
        self.statusBar().showMessage("", 0)
    
    def _on_update_checked(self, has_update, latest_version, download_url, error):
        """更新检查完成回调"""
        # 关闭进度对话框
        if hasattr(self, '_update_check_dialog') and self._update_check_dialog:
            self._update_check_dialog.close()
        self.statusBar().showMessage("", 0)
        
        if error:
            QMessageBox.warning(self, "检查更新", f"检查更新失败\n\n{error}")
            return
        
        if not latest_version:
            QMessageBox.information(self, "检查更新", "暂无发布版本信息")
            return
        
        if has_update:
            msg = f"发现新版本！\n\n当前版本: v{self.VERSION}\n最新版本: v{latest_version}"
            reply = QMessageBox.question(
                self, "发现新版本", 
                msg + "\n\n是否前往下载？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(download_url))
        else:
            QMessageBox.information(self, "检查更新", f"当前已是最新版本 v{self.VERSION}")
    
    def _show_about_dialog(self):
        """显示关于对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("关于 YNU选课助手 Pro")
        dialog.setFixedSize(500, 550)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BASE};
            }}
            QLabel {{
                color: {Colors.TEXT};
            }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(30, 25, 30, 20)
        
        # Logo/标题
        title_label = QLabel("🎓 YNU选课助手 Pro")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {Colors.BLUE};
            padding: 6px 0;
        """)
        layout.addWidget(title_label)
        
        # 版本
        version_label = QLabel(f"版本 {self.VERSION}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet(f"""
            font-size: 14px;
            color: {Colors.SUBTEXT0};
            margin-bottom: 6px;
        """)
        layout.addWidget(version_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {Colors.SURFACE2}; max-height: 1px;")
        layout.addWidget(line)
        
        # 简介
        intro_label = QLabel("☁️ 云南大学教务系统选课辅助工具")
        intro_label.setAlignment(Qt.AlignCenter)
        intro_label.setStyleSheet(f"""
            font-size: 13px;
            color: {Colors.SUBTEXT1};
            padding: 4px 0;
        """)
        layout.addWidget(intro_label)
        
        # 功能描述（使用滚动区域）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)
        
        features_widget = QWidget()
        features_layout = QVBoxLayout(features_widget)
        features_layout.setSpacing(8)
        features_layout.setContentsMargins(4, 4, 4, 4)
        
        # 主要功能
        features_text = QLabel(
            "✨ <b>主要功能</b><br>"
            "　• 纯 API 模式，无需浏览器<br>"
            "　• 自动 OCR 验证码识别<br>"
            "　• 多课程并发监控抢课<br>"
            "　• 智能换课（自动退旧选新）<br>"
            "　• Server酱微信通知推送<br>"
            "　• Session 过期自动重登<br><br>"
            
            "📖 <b>使用方法</b><br>"
            "1. 输入学号密码，点击「一键登录」<br>"
            "2. 选择课程类型，浏览或搜索课程<br>"
            "3. 点击「加入待抢」添加到列表<br>"
            "4. 设置并发数，点击「开始监控」<br><br>"
            
            "📱 <b>Server酱配置</b><br>"
            "1. 访问 <a href='https://sct.ftqq.com/' style='color: #89b4fa;'>https://sct.ftqq.com/</a><br>"
            "2. 微信扫码登录获取 SendKey<br>"
            "3. 勾选「微信通知」并填入 SendKey<br>"
            "4. 发现余量和抢课成功时自动推送"
        )
        features_text.setWordWrap(True)
        features_text.setOpenExternalLinks(True)
        features_text.setTextFormat(Qt.RichText)
        features_text.setStyleSheet(f"""
            font-size: 12px;
            color: {Colors.SUBTEXT1};
            line-height: 1.5;
            padding: 6px;
        """)
        features_layout.addWidget(features_text)
        
        scroll.setWidget(features_widget)
        scroll.setFixedHeight(260)
        layout.addWidget(scroll)
        
        layout.addStretch()
        
        # 作者信息框
        author_frame = QFrame()
        author_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.SURFACE0};
                border-radius: 10px;
            }}
        """)
        author_layout = QVBoxLayout(author_frame)
        author_layout.setSpacing(4)
        author_layout.setContentsMargins(16, 10, 16, 10)
        
        original_label = QLabel("🔗 原项目: starwingChen/YNU-xk_spider")
        original_label.setStyleSheet(f"font-size: 11px; color: {Colors.OVERLAY0};")
        author_layout.addWidget(original_label)
        
        dev_label = QLabel("👨‍💻 作者: YHalo-wyh")
        dev_label.setStyleSheet(f"font-size: 12px; color: {Colors.LAVENDER}; font-weight: bold;")
        author_layout.addWidget(dev_label)
        
        layout.addWidget(author_frame)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        github_btn = QPushButton("⭐ GitHub 仓库")
        github_btn.setCursor(Qt.PointingHandCursor)
        github_btn.setFixedHeight(36)
        github_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.SURFACE1};
                color: {Colors.TEXT};
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BLUE};
                color: {Colors.CRUST};
            }}
        """)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.GITHUB_URL)))
        btn_layout.addWidget(github_btn)
        
        close_btn = QPushButton("关闭")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.SURFACE2};
                color: {Colors.TEXT};
                border: none;
                border-radius: 8px;
                font-size: 13px;
                padding: 0 24px;
            }}
            QPushButton:hover {{
                background-color: {Colors.OVERLAY0};
            }}
        """)
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def _on_serverchan_toggled(self, state):
        """Server酱复选框状态变化"""
        self.serverchan_enabled = bool(state)
        self.serverchan_key_input.setVisible(self.serverchan_enabled)
        if not self.serverchan_enabled:
            self.serverchan_key = ''
    
    def log(self, msg):
        """
        日志方法：UI 滚动清理 + 文件持久化
        优化：减少 UI 操作频率，避免长时间运行后卡顿
        """
        try:
            # 写入文件日志
            self._logger.info(msg)
            
            # 计数器：每 50 条日志才检查一次是否需要清理
            if not hasattr(self, '_log_count'):
                self._log_count = 0
            self._log_count += 1
            
            # 每 50 条检查一次，超过 500 行时清空到 200 行
            if self._log_count % 50 == 0:
                try:
                    doc = self.log_text.document()
                    block_count = doc.blockCount()
                    if block_count > 500:
                        # 直接截取最后 200 行，比逐行删除快得多
                        text = self.log_text.toPlainText()
                        lines = text.split('\n')
                        if len(lines) > 200:
                            self.log_text.setPlainText('\n'.join(lines[-200:]))
                except Exception:
                    # 日志清理失败不应该影响程序运行
                    pass
            
            # 追加新日志
            try:
                self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            except Exception:
                # 日志输出失败，尝试简化输出
                try:
                    self.log_text.append(f"[{time.strftime('%H:%M:%S')}] 日志输出异常")
                except Exception:
                    # 完全失败，忽略
                    pass
            
            # 每 10 条才滚动一次，减少 UI 刷新
            if self._log_count % 10 == 0:
                try:
                    scrollbar = self.log_text.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())
                except Exception:
                    # 滚动失败不影响程序运行
                    pass
        except Exception as e:
            # 整个日志方法失败，写入系统日志
            try:
                self._logger.error(f"日志输出异常: {str(e)[:50]}")
            except Exception:
                # 连系统日志都失败，完全忽略
                pass
    
    def update_heartbeat(self, count):
        """更新心跳指示器 - 只更新文本，避免频繁设置样式"""
        try:
            self._heartbeat_count = count
            # 只更新文本，不频繁切换样式（避免内存泄漏和卡顿）
            self.run_indicator.setText(f"⚡ 监控中 | 已扫描: {count} 次")
        except Exception as e:
            # 心跳更新失败不应该影响程序运行
            try:
                self._logger.warning(f"心跳更新失败: {str(e)[:50]}")
            except Exception:
                pass
    
    def load_config(self):
        try:
            with open('xk_spider/config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.username_input.setText(config.get('username', ''))
                self.password_input.setText(config.get('password', ''))
                
                # Server酱配置
                self.serverchan_enabled = config.get('serverchan_enabled', False)
                self.serverchan_key = config.get('serverchan_key', '')
                self.serverchan_checkbox.setChecked(self.serverchan_enabled)
                self.serverchan_key_input.setText(self.serverchan_key)
                self.serverchan_key_input.setVisible(self.serverchan_enabled)
        except:
            pass
    
    def save_config(self):
        # 更新 Server酱 key
        if self.serverchan_enabled:
            self.serverchan_key = self.serverchan_key_input.text().strip()
        
        config = {
            'username': self.username_input.text(),
            'password': self.password_input.text(),
            'serverchan_enabled': self.serverchan_enabled,
            'serverchan_key': self.serverchan_key if self.serverchan_enabled else '',
        }
        try:
            os.makedirs('xk_spider', exist_ok=True)
            with open('xk_spider/config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass

    def login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, "提示", "请输入学号和密码")
            return
        
        if not OCR_AVAILABLE:
            QMessageBox.warning(self, "错误", "OCR模块(ddddocr)未安装，无法使用纯API模式\n\n请安装: pip install ddddocr")
            return
        
        self.save_config()
        self.login_btn.setEnabled(False)
        self.login_btn.setText("登录中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self.login_worker = LoginWorker(username, password)
        self.login_worker.success.connect(self.on_login_success)
        self.login_worker.failed.connect(self.on_login_failed)
        self.login_worker.status.connect(lambda msg: self.statusBar().showMessage(f"🔐 {msg}"))
        self.login_worker.start()
    
    def on_login_success(self, cookies, token, batch_code, student_code):
        self.cookies = cookies
        self.token = token
        self.batch_code = batch_code
        self.student_code = student_code
        self.is_logged_in = True
        
        self.status_label.setText(f"● 已登录 - {student_code}")
        self.status_label.setStyleSheet(f"color: {Colors.GREEN}; font-weight: bold; font-size: 13px;")
        self.login_btn.setText("已登录")
        self.login_btn.setEnabled(False)
        self.logout_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.log(f"[SUCCESS] ✓ 登录成功！")
        self.log(f"[INFO] Token: {token}")
        self.log(f"[INFO] BatchCode: {batch_code}")
        self.statusBar().showMessage("✓ 纯API模式已就绪，课程列表自动刷新中...")
        
        if self._pending_monitor_courses:
            self.log(f"[INFO] 检测到 {len(self._pending_monitor_courses)} 门待恢复课程")
            QTimer.singleShot(1000, self._resume_monitoring)
        else:
            QTimer.singleShot(300, self._start_polling)
    
    def on_login_failed(self, msg):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("🚀 一键登录")
        self.progress_bar.setVisible(False)
        self.log(f"[ERROR] 登录失败: {msg}")
        QMessageBox.warning(self, "登录失败", msg)
    
    def logout(self):
        self.poll_timer.stop()
        self._is_searching = False
        
        self.stop_monitoring()
        self.is_logged_in = False
        self.token = ''
        self.batch_code = ''
        self.student_code = ''
        self.cookies = ''
        
        self.status_label.setText("● 未登录")
        self.status_label.setStyleSheet(f"color: {Colors.RED}; font-weight: bold; font-size: 13px;")
        self.login_btn.setText("🚀 一键登录")
        self.login_btn.setEnabled(True)
        self.logout_btn.setEnabled(False)
        
        self.course_list.clear()
        self.clear_cards()
        self._api_courses_grouped = {}
        
        self.log("[INFO] 已退出登录")

    def refresh_courses(self, keyword='', silent=False, force=False):
        """
        刷新课程列表（使用后台线程）
        force=True 时断开旧请求信号并启动新请求
        """
        if not self.is_logged_in:
            if not silent:
                QMessageBox.warning(self, "提示", "请先登录")
            return
        
        # 如果有正在运行的请求
        if self._course_fetch_worker and self._course_fetch_worker.isRunning():
            if force:
                # 断开旧请求的信号连接，让它自然结束（不使用 terminate 避免资源泄漏）
                try:
                    self._course_fetch_worker.finished.disconnect()
                except TypeError:
                    pass  # 信号未连接，忽略
                self.log("[API] 后台有未完成请求，已断开信号并重新发起")
                # 不再等待旧线程，让它自然结束
            else:
                # 非强制模式，跳过
                return
        
        course_type_name = self.course_type_combo.currentText()
        course_type_code = COURSE_TYPES.get(course_type_name, 'TJKC')
        internal_type = COURSE_NAME_TO_TYPE.get(course_type_name, 'recommend')
        
        search_keyword = keyword if keyword else self.search_input.text().strip()
        
        # 记录当前请求的课程类型（用于回调时校验）
        self._current_fetch_type = course_type_name
        self._fetch_silent = silent
        
        if not silent:
            self.course_list.clear()
            self.clear_cards()
            self._api_courses_grouped = {}
            self.course_count_label.setText("加载中...")
            self.log(f"[API] 刷新课程列表: {course_type_name}" + (f" (搜索: {search_keyword})" if search_keyword else ""))
        
        self.statusBar().showMessage(f"正在获取 {course_type_name}...")
        
        self._course_fetch_worker = CourseFetchWorker(
            token=self.token,
            cookies=self.cookies,
            student_code=self.student_code,
            batch_code=self.batch_code,
            course_type_code=course_type_code,
            internal_type=internal_type,
            search_keyword=search_keyword
        )
        self._course_fetch_worker.finished.connect(self._on_course_fetch_finished)
        self._course_fetch_worker.start()
    
    def _on_course_fetch_finished(self, courses_grouped, error):
        """CourseFetchWorker 完成回调"""
        silent = self._fetch_silent
        
        # 校验：如果当前下拉框的类型已经变了，说明用户切换了，忽略这个旧回调
        current_type = self.course_type_combo.currentText()
        if hasattr(self, '_current_fetch_type') and self._current_fetch_type != current_type:
            # 旧请求的回调，忽略
            return
        
        if error:
            error_str = str(error).lower()
            
            # 初始化失败计数器
            if not hasattr(self, '_fetch_fail_count'):
                self._fetch_fail_count = 0
            self._fetch_fail_count += 1
            
            # 网络连接错误 - 自动重试
            is_network_error = any(kw in error_str for kw in [
                'connectionpool', 'connection', 'timeout', 'timed out',
                'refused', 'reset', 'network', 'socket', 'ssl', 'eof'
            ])
            
            if is_network_error:
                # 初始化重试计数器
                if not hasattr(self, '_fetch_retry_count'):
                    self._fetch_retry_count = 0
                
                self._fetch_retry_count += 1
                max_retries = 3
                
                if self._fetch_retry_count <= max_retries:
                    # 3次内都显示"加载中"，不显示失败
                    if not silent:
                        self.course_count_label.setText("加载中...")
                    # 延迟重试，间隔递增
                    QTimer.singleShot(self._fetch_retry_count * 1000, lambda: self.refresh_courses(silent=silent, force=True))
                    return
                else:
                    # 超过重试次数才显示失败
                    self._fetch_retry_count = 0
                    if not silent:
                        self.log(f"[API] 获取失败: {error}")
                        self.course_count_label.setText("获取失败 (等待下次轮询)")
                    return
            
            # 非网络错误：也要累计3次才显示失败
            if self._fetch_fail_count < 3:
                if not silent:
                    self.course_count_label.setText("加载中...")
                return
            
            # 重置计数器
            self._fetch_fail_count = 0
            self._fetch_retry_count = 0
            
            if not silent:
                self.log(f"[API] 获取失败: {error}")
                self.course_count_label.setText("获取失败")
            
            # 只有在非监控模式下才处理登录过期（监控时由 worker 自动重登）
            if '登录' in error_str or 'token' in error_str:
                if self.multi_grab_worker and self.multi_grab_worker.isRunning():
                    # 监控中，忽略这个错误，等待 worker 重登
                    self.log("[API] 监控中检测到 session 问题，等待自动重登...")
                else:
                    self.poll_timer.stop()
                    self.logout()
                    QMessageBox.warning(self, "会话过期", "登录已过期，请重新登录")
            return
        
        # 成功获取，重置计数器
        self._fetch_retry_count = 0
        self._fetch_fail_count = 0
        
        if courses_grouped:
            self._api_courses_grouped = courses_grouped
            
            current_names = set(self._api_courses_grouped.keys())
            existing_names = set()
            for i in range(self.course_list.count()):
                existing_names.add(self.course_list.item(i).data(Qt.UserRole))
            
            if current_names != existing_names:
                self.course_list.clear()
                for course_name in self._api_courses_grouped:
                    item = QListWidgetItem(course_name)
                    item.setData(Qt.UserRole, course_name)
                    self.course_list.addItem(item)
            
            self.course_count_label.setText(f"共 {len(self._api_courses_grouped)} 门课程")
            self.statusBar().showMessage(f"✓ 获取到 {len(self._api_courses_grouped)} 门课程")
            if not silent:
                self.log(f"[API] 获取到 {len(self._api_courses_grouped)} 门课程")
        else:
            if not silent:
                self.course_count_label.setText("共 0 门课程")
                self.statusBar().showMessage("未找到匹配的课程")
    
    def on_course_type_changed(self, text):
        """课程类型切换 - 强制刷新"""
        if not self.is_logged_in:
            return
        
        # 停止轮询，防止干扰
        self.poll_timer.stop()
        self._is_searching = False
        self.search_input.clear()
        
        # 立即清空 UI（抢占式）
        self.course_list.clear()
        self.clear_cards()
        self._api_courses_grouped = {}
        self.course_count_label.setText("切换中...")
        
        # 强制刷新（终止旧请求）
        self.refresh_courses(force=True)
        
        # 延迟启动轮询，给新请求一点时间
        QTimer.singleShot(500, lambda: self.poll_timer.start(self._poll_interval))
    
    def on_search(self):
        """搜索功能"""
        if not self.is_logged_in:
            QMessageBox.warning(self, "提示", "请先登录")
            return
        
        search_text = self.search_input.text().strip()
        
        if search_text:
            self.poll_timer.stop()
            self._is_searching = True
            
            self.course_list.clear()
            self.clear_cards()
            self._api_courses_grouped = {}
            
            self.refresh_courses(keyword=search_text)
        else:
            self._is_searching = False
            self.refresh_courses()
            self.poll_timer.start(self._poll_interval)
    
    def on_course_selected(self, item):
        course_name = item.data(Qt.UserRole)
        if course_name and course_name in self._api_courses_grouped:
            self.show_course_cards(course_name, self._api_courses_grouped[course_name])
    
    def clear_cards(self):
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def show_course_cards(self, course_name, tc_list):
        self.clear_cards()
        self.schedule_title.setText(f"📅 {course_name}")
        
        # 每行 2 张卡片（宽卡片设计）
        for i, tc in enumerate(tc_list):
            card = CourseCard(tc)
            card.grab_clicked.connect(self.add_to_grab_list)
            row = i // 2
            col = i % 2
            self.cards_layout.addWidget(card, row, col)
    
    def add_to_grab_list(self, course):
        tc_id = course.get('JXBID', '')
        course_name = course.get('KCM', '')
        teacher = course.get('SKJS', '')
        
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                QMessageBox.information(self, "提示", f"课程已在待抢列表中")
                return
        
        is_conflict = course.get('isConflict', False)
        is_full = course.get('isFull', False)
        display_text = f"{course_name} - {teacher}"
        if is_conflict:
            display_text += " ⚠️"
        if is_full:
            display_text += " 🔴"
        
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, course)
        self.grab_list.addItem(item)
        
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        self.log(f"[INFO] 添加待抢: {course_name} - {teacher}")
        
        if self.multi_grab_worker and self.multi_grab_worker.isRunning():
            self.multi_grab_worker.add_course(course)
    
    def show_grab_context_menu(self, pos):
        item = self.grab_list.itemAt(pos)
        if not item:
            return
        
        menu = QMenu(self)
        remove_action = menu.addAction("🗑 移除")
        action = menu.exec_(self.grab_list.mapToGlobal(pos))
        
        if action == remove_action:
            course = item.data(Qt.UserRole)
            tc_id = course.get('JXBID', '') if course else ''
            
            row = self.grab_list.row(item)
            self.grab_list.takeItem(row)
            self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
            
            if self.multi_grab_worker and self.multi_grab_worker.isRunning() and tc_id:
                self.multi_grab_worker.remove_course(tc_id)
            
            self.log(f"[INFO] 移除待抢: {course.get('KCM', '')}")

    def start_monitoring(self):
        if not self.is_logged_in:
            QMessageBox.warning(self, "提示", "请先登录")
            return
        
        if self.grab_list.count() == 0:
            QMessageBox.warning(self, "提示", "请先添加待抢课程")
            return
        
        courses = []
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            course = item.data(Qt.UserRole)
            if course:
                courses.append(course)
        
        # 获取 Server酱 key
        serverchan_key = ''
        if self.serverchan_enabled:
            serverchan_key = self.serverchan_key_input.text().strip()
            self.serverchan_key = serverchan_key
        
        self.log(f"[INFO] 开始监控 {len(courses)} 门课程 (并发: {self.concurrency_spin.value()})")
        if serverchan_key:
            self.log(f"[INFO] Server酱通知已启用")
        
        self.multi_grab_worker = MultiGrabWorker(
            courses=courses,
            student_code=self.student_code,
            batch_code=self.batch_code,
            token=self.token,
            cookies=self.cookies,
            username=self.username_input.text(),
            password=self.password_input.text(),
            max_workers=self.concurrency_spin.value(),
            serverchan_key=serverchan_key
        )
        
        self.multi_grab_worker.success.connect(self.on_grab_success)
        self.multi_grab_worker.failed.connect(self.on_grab_failed)
        self.multi_grab_worker.status.connect(self.on_grab_status)
        self.multi_grab_worker.need_relogin.connect(self.on_need_relogin)
        self.multi_grab_worker.course_available.connect(self.on_course_available)
        self.multi_grab_worker.session_updated.connect(self.on_session_updated)
        self.multi_grab_worker.finished.connect(self.on_worker_finished)
        self.multi_grab_worker.heartbeat.connect(self.update_heartbeat)
        
        self.multi_grab_worker.start()
        
        self.start_grab_btn.setEnabled(False)
        self.stop_grab_btn.setEnabled(True)
        self.run_indicator.setText("⚡ 监控中 | 已扫描: 0 次")
        self.run_indicator.setStyleSheet(f"""
            QLabel {{
                color: {Colors.GREEN};
                background-color: {Colors.SURFACE0};
                font-size: 13px;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 14px;
                margin: 2px 8px;
            }}
        """)
        self.statusBar().showMessage("🎯 监控中...")
    
    def stop_monitoring(self):
        if self.multi_grab_worker:
            self.multi_grab_worker.stop()
            self.multi_grab_worker.wait(2000)
            self.multi_grab_worker = None
        
        self.start_grab_btn.setEnabled(True)
        self.stop_grab_btn.setEnabled(False)
        self.run_indicator.setText("● 待机")
        self.run_indicator.setStyleSheet(f"""
            QLabel {{
                color: {Colors.OVERLAY0};
                background-color: {Colors.SURFACE0};
                font-size: 13px;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 14px;
                margin: 2px 8px;
            }}
        """)
        self.statusBar().showMessage("⏹ 监控已停止")
        self.log("[INFO] 监控已停止")
    
    def on_grab_success(self, msg, course):
        self.log(f"[SUCCESS] ✅ {msg}")
        
        tc_id = course.get('JXBID', '')
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                self.grab_list.takeItem(i)
                break
        
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        QMessageBox.information(self, "🎉 抢课成功", msg)
    
    def on_grab_failed(self, msg):
        self.log(f"[ERROR] {msg}")
    
    def on_grab_status(self, msg):
        self.log(msg)
        self.statusBar().showMessage(msg)
    
    def on_session_updated(self, token, cookies):
        self.token = token
        self.cookies = cookies
        self.log("[INFO] Session 已同步更新")
    
    def on_worker_finished(self):
        self.start_grab_btn.setEnabled(True)
        self.stop_grab_btn.setEnabled(False)
        
        if self._pending_monitor_courses and not self.is_logged_in:
            self.log("[INFO] Worker 异常退出，尝试自动重登...")
            self._auto_relogin_and_resume()
    
    def on_need_relogin(self):
        self.log("[WARN] Session过期，准备自动重登...")
        
        pending_courses = []
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            course = item.data(Qt.UserRole)
            if course:
                pending_courses.append(course)
        
        self._pending_monitor_courses = pending_courses
        self.log(f"[INFO] 已保存 {len(pending_courses)} 门待抢课程")
        
        self.stop_monitoring()
        self._auto_relogin_and_resume()
    
    def _auto_relogin_and_resume(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            self.log("[ERROR] 无法自动重登：缺少用户名或密码")
            QMessageBox.warning(self, "重登失败", "请手动重新登录")
            return
        
        self.log("[INFO] 开始自动重登...")
        self.login_btn.setEnabled(False)
        self.login_btn.setText("自动重登中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self.login_worker = LoginWorker(username, password)
        self.login_worker.success.connect(self.on_login_success)
        self.login_worker.failed.connect(self._on_auto_relogin_failed)
        self.login_worker.status.connect(lambda msg: self.statusBar().showMessage(f"🔐 {msg}"))
        self.login_worker.start()
    
    def _on_auto_relogin_failed(self, msg):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("🚀 一键登录")
        self.progress_bar.setVisible(False)
        self.log(f"[ERROR] 自动重登失败: {msg}")
        QMessageBox.warning(self, "自动重登失败", f"{msg}\n\n请手动重新登录")
        self._pending_monitor_courses = []
    
    def _resume_monitoring(self):
        if not self._pending_monitor_courses:
            return
        
        self.log(f"[INFO] 恢复监控 {len(self._pending_monitor_courses)} 门课程...")
        
        for course in self._pending_monitor_courses:
            tc_id = course.get('JXBID', '')
            exists = False
            for i in range(self.grab_list.count()):
                item = self.grab_list.item(i)
                if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                    exists = True
                    break
            
            if not exists:
                course_name = course.get('KCM', '')
                teacher = course.get('SKJS', '')
                is_conflict = course.get('isConflict', False)
                display_text = f"{course_name} - {teacher}"
                if is_conflict:
                    display_text += " ⚠️"
                
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, course)
                self.grab_list.addItem(item)
        
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        self._pending_monitor_courses = []
        
        QTimer.singleShot(500, self.start_monitoring)
    
    def on_course_available(self, course_name, teacher, remain, capacity):
        self.log(f"[ALERT] 🎉 {course_name} 有余量！余={remain}/{capacity}")
    
    def _start_polling(self):
        self.refresh_courses()
        self.poll_timer.start(self._poll_interval)
        self.log(f"[INFO] 自动轮询已启动 (间隔 {self._poll_interval/1000}s)")
    
    def _on_poll_timer(self):
        if not self.is_logged_in:
            self.poll_timer.stop()
            return
        
        if self._is_searching:
            return
        
        self.refresh_courses(silent=True)
    
    def closeEvent(self, event):
        self.poll_timer.stop()
        self.stop_monitoring()
        self.save_config()
        event.accept()
