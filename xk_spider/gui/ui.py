"""
用户界面模块 - View
Modern Dark Dashboard 风格 (Catppuccin Mocha 配色)
"""
import os
import time
import sys
import subprocess
import json
import re

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QTextEdit, QProgressBar, QMessageBox, QFrame, QGridLayout, QSizePolicy,
    QSpinBox, QScrollArea, QCheckBox, QSplitter, QApplication, QMenu,
    QGraphicsDropShadowEffect, QMenuBar, QAction, QDialog, QDialogButtonBox,
    QProgressDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtProperty, QUrl
from PyQt5.QtGui import QFont, QPainter, QColor, QTextCursor, QDesktopServices, QIcon

from .config import COURSE_TYPES, COURSE_NAME_TO_TYPE, parse_int, MONITOR_STATE_FILE, WATCHDOG_SIGNAL_FILE
from .workers import LoginWorker, MultiGrabWorker, CourseFetchWorker, UpdateCheckWorker, DownloadUpdateWorker
from .logger import get_logger
from .utils import (
    default_webhook_config, make_legacy_feedback_channel,
    normalize_webhook_channels, send_custom_webhooks,
    validate_webhook_channels,
)
from xk_spider.storage import (
    CONFIG_FILE, migrate_legacy_data, read_json, write_json_atomic,
)


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
        if is_chosen or is_full or is_conflict:
            status_layout = QHBoxLayout()
            status_layout.setSpacing(8)

            if is_chosen:
                status_label = QLabel("✓ 已选")
                status_label.setStyleSheet(f"""
                    font-size: 13px; font-weight: bold; 
                    color: {Colors.CRUST}; 
                    background-color: {Colors.GREEN}; 
                    padding: 4px 12px; border-radius: 12px;
                """)
                status_layout.addWidget(status_label)
            else:
                if is_full:
                    full_label = QLabel("已满")
                    full_label.setStyleSheet(f"""
                        font-size: 13px; font-weight: bold; 
                        color: {Colors.CRUST}; 
                        background-color: {Colors.RED}; 
                        padding: 4px 12px; border-radius: 12px;
                    """)
                    status_layout.addWidget(full_label)

                if is_conflict:
                    conflict_label = QLabel("冲突")
                    conflict_label.setStyleSheet(f"""
                        font-size: 13px; font-weight: bold; 
                        color: {Colors.CRUST}; 
                        background-color: {Colors.YELLOW}; 
                        padding: 4px 12px; border-radius: 12px;
                    """)
                    status_layout.addWidget(conflict_label)

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
    VERSION = "v2.4.0"
    GITHUB_URL = "https://github.com/YHalo-wyh/YNU-xk_spider-Pro"
    
    def __init__(self):
        super().__init__()
        self.is_logged_in = False
        self.token = ''
        self.batch_code = ''
        self.batch_name = ''
        self.student_code = ''
        self.campus = '02'  # 默认呈贡校区
        self.cookies = ''
        self.multi_grab_worker = None
        self._api_courses_grouped = {}
        self._pending_monitor_courses = []
        self._is_searching = False
        self._current_search_keyword = ''
        self._showing_search_empty_state = False
        self._is_manual_login_attempt = False
        self._manual_login_fail_count = 0
        self._auto_relogin_retry_count = 0
        self._installing_update = False
        self._update_resume_monitoring = False
        self._active_conflict_policy = None
        self._pending_resume_conflict_policy = None
        
        # Server酱配置
        self.serverchan_enabled = False
        self.serverchan_key = ''

        # 开发者模式配置
        self.developer_mode_enabled = False
        self.feedback_url = ''
        self.developer_webhooks = []
        
        # 日志系统
        self._logger = get_logger()
        self._heartbeat_count = 0
        migrated = migrate_legacy_data()
        if migrated:
            self._logger.info(f"已迁移 {len(migrated)} 个旧版用户数据文件到独立数据目录")
        
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
        
        # 检查是否需要恢复监控（闪退恢复）
        self._pending_restore_state = None
        state = self.load_monitor_state()
        if state and state.get('courses'):
            self._restore_saved_watchlist(state)
            if state.get('is_monitoring'):
                self._pending_restore_state = state
                self._logger.info(f"检测到上次监控未正常结束，待恢复 {len(state['courses'])} 门课程")
                # 延迟自动登录（等待窗口显示后）
                QTimer.singleShot(500, self._auto_login_for_restore)
            else:
                self._logger.info(f"已恢复 {len(state['courses'])} 门待选课程")
    
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
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
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
        
        self.batch_label = QLabel("📅 选课批次: 自动识别")
        self.batch_label.setStyleSheet(f"color: {Colors.SUBTEXT0}; font-size: 13px; padding: 4px 0;")
        login_layout.addWidget(self.batch_label)
        
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
        self.login_btn.clicked.connect(self.on_manual_login_clicked)
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
        
        conc_label = QLabel("⚡ HTTP并发")
        conc_label.setStyleSheet(f"color: {Colors.SUBTEXT1}; font-size: 14px;")
        concurrency_layout.addWidget(conc_label)
        
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 20)
        self.concurrency_spin.setValue(5)
        self.concurrency_spin.setFixedWidth(70)
        self.concurrency_spin.setToolTip("同时进行的网络请求数量（建议 3-10）")
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
        self.start_grab_btn.clicked.connect(lambda _=False: self.start_monitoring())
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
        self.stop_grab_btn.clicked.connect(lambda _=False: self.stop_monitoring())
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

        developer_action = QAction("🛠 开发者模式", self)
        developer_action.triggered.connect(self._show_developer_mode_dialog)
        help_menu.addAction(developer_action)
        
        help_menu.addSeparator()
        
        # 关于
        about_action = QAction("ℹ️ 关于", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
    
    def _open_github(self):
        """打开 GitHub 仓库"""
        QDesktopServices.openUrl(QUrl(self.GITHUB_URL))

    def _show_developer_mode_dialog(self):
        """配置开发者模式下的自定义 Webhook 通道。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("开发者模式")
        dialog.setMinimumWidth(820)
        dialog.setMinimumHeight(680)

        layout = QVBoxLayout(dialog)
        description = QLabel(
            "开发者模式用于接入自定义通知接口。这里直接使用完整 Webhook 配置："
            "支持多个端点、事件筛选、请求方法、Headers、URL 参数和 Body 模板。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        enable_frame = QFrame()
        enable_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.SURFACE0};
                border: 2px solid {Colors.MAUVE};
                border-radius: 12px;
            }}
        """)
        enable_layout = QVBoxLayout(enable_frame)
        enable_layout.setContentsMargins(14, 12, 14, 12)
        enable_layout.setSpacing(6)

        enabled_checkbox = QCheckBox("启用开发者模式 / 自定义 Webhook 通知")
        enabled_checkbox.setChecked(self.developer_mode_enabled)
        enabled_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {Colors.TEXT};
                font-size: 16px;
                font-weight: bold;
                spacing: 12px;
            }}
            QCheckBox::indicator {{
                width: 26px;
                height: 26px;
                border-radius: 7px;
                border: 3px solid {Colors.MAUVE};
                background-color: {Colors.MANTLE};
            }}
            QCheckBox::indicator:checked {{
                background-color: {Colors.MAUVE};
                border-color: {Colors.LAVENDER};
            }}
            QCheckBox::indicator:hover {{
                border-color: {Colors.LAVENDER};
            }}
        """)
        enable_layout.addWidget(enabled_checkbox)

        enable_hint = QLabel("勾选后才会按下面 JSON 配置向自定义 Webhook 发送事件通知。")
        enable_hint.setWordWrap(True)
        enable_hint.setStyleSheet(f"color: {Colors.SUBTEXT0}; font-size: 12px;")
        enable_layout.addWidget(enable_hint)
        layout.addWidget(enable_frame)

        current_config = {"webhooks": self.developer_webhooks}
        if not self.developer_webhooks and self.feedback_url:
            migrated = make_legacy_feedback_channel(self.feedback_url)
            current_config = {"webhooks": [migrated] if migrated else []}
        if not current_config.get("webhooks"):
            current_config = default_webhook_config()

        config_label = QLabel("Webhook 配置 JSON")
        layout.addWidget(config_label)

        config_editor = QTextEdit()
        config_editor.setAcceptRichText(False)
        config_editor.setPlainText(json.dumps(current_config, ensure_ascii=False, indent=2))
        config_editor.setEnabled(enabled_checkbox.isChecked())
        layout.addWidget(config_editor, 1)

        hint = QLabel(
            "可用事件：test、course_available、select_success、swap_success、"
            "rollback_success、rollback_failed、conflict_target_retired，也可以用 * 表示所有事件。\n"
            "常用占位符：{event}、{title}、{content}、{course_name}、{teacher}、{remain}、"
            "{capacity}、{old_course_name}、{new_course_name}、{message}、{timestamp}、"
            "{username_masked}。URL 内占位符会自动 URL 编码。\n"
            "提示：配置里可能包含访问密钥，请勿截图或分享配置文件。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.SUBTEXT0}; font-size: 12px;")
        layout.addWidget(hint)

        enabled_checkbox.toggled.connect(config_editor.setEnabled)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        test_button = buttons.addButton("测试发送", QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)

        def parse_config_from_editor():
            text = config_editor.toPlainText().strip()
            if not text:
                return {"webhooks": []}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(f"JSON 格式错误：第 {error.lineno} 行第 {error.colno} 列，{error.msg}")
            channels = normalize_webhook_channels(parsed)
            valid, error = validate_webhook_channels(channels)
            if not valid:
                raise ValueError(error)
            return {"webhooks": channels}

        def save_developer_config():
            enabled = enabled_checkbox.isChecked()
            try:
                parsed = parse_config_from_editor()
            except ValueError as error:
                QMessageBox.warning(dialog, "Webhook 配置无效", str(error))
                return
            self.developer_mode_enabled = enabled
            self.developer_webhooks = parsed.get("webhooks", [])
            self.feedback_url = ''
            self.save_config()
            state = "已启用" if enabled else "已关闭"
            self.log(f"[INFO] 开发者模式自定义 Webhook {state}，通道数: {len(self.developer_webhooks)}")
            dialog.accept()

        def test_developer_config():
            try:
                parsed = parse_config_from_editor()
            except ValueError as error:
                QMessageBox.warning(dialog, "Webhook 配置无效", str(error))
                return
            send_custom_webhooks(
                parsed,
                'test',
                '🧪 YNU选课助手 Webhook 测试',
                '这是一条开发者模式测试通知。只有 events 包含 test 或 * 的通道会收到。',
                {
                    'course_name': '测试课程',
                    'teacher': '测试教师',
                    'remain': 1,
                    'capacity': 30,
                    'message': '开发者模式测试通知',
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'username_masked': self.username_input.text()[:2] + '****'
                    if self.username_input.text() else '',
                }
            )
            QMessageBox.information(
                dialog,
                "测试已发送",
                "已触发 test 事件。只有 events 包含 test 或 * 的启用通道会收到。"
            )

        buttons.accepted.connect(save_developer_config)
        buttons.rejected.connect(dialog.reject)
        test_button.clicked.connect(test_developer_config)
        dialog.exec_()
    
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
    
    def _format_version(self, version):
        """统一版本号展示格式，避免出现 vv2.0.0"""
        normalized = str(version or '').strip().lstrip('vV')
        return f"v{normalized}" if normalized else "未知"
    
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

        current_text = self._format_version(self.VERSION)
        latest_text = self._format_version(latest_version)

        if has_update:
            # 检查是否是直接下载链接（.exe）
            is_direct_download = str(download_url or '').lower().split('?', 1)[0].endswith('.exe')

            if is_direct_download:
                msg = f"发现新版本！\n\n当前版本: {current_text}\n最新版本: {latest_text}"
                reply = QMessageBox.question(
                    self, "发现新版本",
                    msg + "\n\n是否立即下载并安装？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._start_download_update(download_url, latest_version)
            else:
                # 没有找到 .exe，回退到打开浏览器
                msg = f"发现新版本！\n\n当前版本: {current_text}\n最新版本: {latest_text}"
                reply = QMessageBox.question(
                    self, "发现新版本",
                    msg + "\n\n是否前往下载页面？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    QDesktopServices.openUrl(QUrl(download_url))
        else:
            QMessageBox.information(self, "检查更新", f"当前已是最新版本 {current_text}")

    def _start_download_update(self, download_url, version):
        """开始下载更新"""
        # 确定保存路径
        normalized_version = str(version or '').strip().lstrip('vV') or 'latest'
        filename = f"YNU.Pro_v{normalized_version}_Setup.exe"
        save_path = os.path.join(os.path.expanduser("~"), "Downloads", filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # 创建进度对话框
        self._download_dialog = QProgressDialog(self)
        self._download_dialog.setWindowTitle("下载更新")
        self._download_dialog.setLabelText(f"正在下载 {filename}...\n0 MB / 0 MB (0%)")
        self._download_dialog.setMinimum(0)
        self._download_dialog.setMaximum(100)
        self._download_dialog.setValue(0)
        self._download_dialog.setWindowModality(Qt.WindowModal)
        self._download_dialog.setAutoClose(False)
        self._download_dialog.setAutoReset(False)
        self._download_dialog.setStyleSheet(f"""
            QProgressDialog {{
                background-color: {Colors.BASE};
                color: {Colors.TEXT};
            }}
            QLabel {{
                color: {Colors.TEXT};
            }}
            QPushButton {{
                background-color: {Colors.SURFACE0};
                color: {Colors.TEXT};
                border: none;
                padding: 5px 15px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE1};
            }}
            QProgressBar {{
                border: 2px solid {Colors.SURFACE0};
                border-radius: 5px;
                text-align: center;
                background-color: {Colors.SURFACE0};
                color: {Colors.TEXT};
            }}
            QProgressBar::chunk {{
                background-color: {Colors.BLUE};
                border-radius: 3px;
            }}
        """)
        self._download_dialog.canceled.connect(self._on_download_canceled)
        self._download_dialog.show()

        # 启动下载 Worker
        self._download_worker = DownloadUpdateWorker(download_url, save_path)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.start()

    def _on_download_progress(self, downloaded, total, percentage):
        """下载进度更新"""
        if hasattr(self, '_download_dialog') and self._download_dialog:
            downloaded_mb = downloaded / (1024 * 1024)
            if total and total > 0:
                total_mb = total / (1024 * 1024)
                label_text = f"正在下载更新...\n{downloaded_mb:.1f} MB / {total_mb:.1f} MB ({percentage}%)"
                self._download_dialog.setRange(0, 100)
                self._download_dialog.setValue(percentage)
            else:
                label_text = f"正在下载更新...\n已下载 {downloaded_mb:.1f} MB（服务器未返回总大小）"
                self._download_dialog.setRange(0, 0)
            self._download_dialog.setLabelText(label_text)

    def _on_download_finished(self, file_path, error):
        """下载完成回调"""
        # 关闭进度对话框
        if hasattr(self, '_download_dialog') and self._download_dialog:
            self._download_dialog.close()

        if error:
            QMessageBox.warning(self, "下载失败", f"更新下载失败\n\n{error}")
            return

        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "下载失败", "文件下载失败，请稍后重试")
            return

        # 下载成功，询问是否立即安装
        reply = QMessageBox.question(
            self, "下载完成",
            f"更新已下载完成！\n\n文件位置: {file_path}\n\n是否立即打开安装程序？\n"
            "程序会先保存账号和待选课程，然后停止监控并自动退出。",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # 更新前持久化账号配置和待选课程，并停止守护进程。
                self._installing_update = True
                self._update_resume_monitoring = (
                    self.multi_grab_worker is not None
                    and self.multi_grab_worker.isRunning()
                )
                self.save_config()
                self.save_monitor_state(is_monitoring=self._update_resume_monitoring)
                self.write_watchdog_signal('stop')
                if self.multi_grab_worker:
                    if not self.stop_monitoring(clear_state=False, reason='update'):
                        raise RuntimeError("监控线程尚未完全停止，请稍后重试安装")

                # 打开安装程序
                if sys.platform == 'win32':
                    os.startfile(file_path)
                else:
                    subprocess.Popen(['xdg-open', file_path])
                QTimer.singleShot(500, QApplication.instance().quit)
            except Exception as e:
                self._installing_update = False
                QMessageBox.warning(self, "打开失败", f"无法打开安装程序\n\n{str(e)}\n\n请手动打开: {file_path}")

    def _on_download_canceled(self):
        """用户取消下载"""
        if hasattr(self, '_download_worker') and self._download_worker:
            self._download_worker.cancel()
            try:
                self._download_worker.finished.disconnect()
            except TypeError:
                pass
    
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
            config = read_json(CONFIG_FILE, {})
            if config:
                self.username_input.setText(config.get('username', ''))
                self.password_input.setText(config.get('password', ''))
                
                # Server酱配置
                self.serverchan_enabled = config.get('serverchan_enabled', False)
                self.serverchan_key = config.get('serverchan_key', '')
                self.serverchan_checkbox.setChecked(self.serverchan_enabled)
                self.serverchan_key_input.setText(self.serverchan_key)
                self.serverchan_key_input.setVisible(self.serverchan_enabled)

                self.developer_mode_enabled = config.get('developer_mode_enabled', False)
                self.feedback_url = str(config.get('feedback_url', '') or '').strip()
                self.developer_webhooks = normalize_webhook_channels(
                    config.get('developer_webhooks', [])
                )
                if not self.developer_webhooks and self.feedback_url:
                    migrated = make_legacy_feedback_channel(self.feedback_url)
                    if migrated:
                        self.developer_webhooks = [migrated]
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
            'developer_mode_enabled': self.developer_mode_enabled,
            'feedback_url': self.feedback_url,
            'developer_webhooks': self.developer_webhooks,
        }
        try:
            write_json_atomic(CONFIG_FILE, config)
        except Exception as e:
            self._logger.error(f"保存账号配置失败: {e}")

    def save_monitor_state(self, is_monitoring=False):
        """保存监控状态到文件（用于闪退恢复）"""
        state = {
            'is_monitoring': is_monitoring,
            'courses': [],
            'course_type': self.course_type_combo.currentText(),
            'concurrency': self.concurrency_spin.value(),
            'conflict_policy': self._active_conflict_policy if is_monitoring else None,
            'timestamp': time.time(),
        }
        
        # 无论是否正在监控，都保存待选课程列表。
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            course = item.data(Qt.UserRole)
            if course:
                state['courses'].append(course)
        
        try:
            write_json_atomic(MONITOR_STATE_FILE, state)
        except Exception as e:
            self._logger.error(f"保存监控状态失败: {e}")

    def load_monitor_state(self):
        """加载监控状态文件"""
        return read_json(MONITOR_STATE_FILE)

    def _restore_saved_watchlist(self, state):
        """恢复上次保存的待选课程和界面设置，但不自动开始监控。"""
        course_type = state.get('course_type', '')
        index = self.course_type_combo.findText(course_type)
        if index >= 0:
            self.course_type_combo.blockSignals(True)
            self.course_type_combo.setCurrentIndex(index)
            self.course_type_combo.blockSignals(False)

        if 'concurrency' in state:
            self.concurrency_spin.setValue(state['concurrency'])

        existing_ids = {
            self.grab_list.item(i).data(Qt.UserRole).get('JXBID', '')
            for i in range(self.grab_list.count())
            if self.grab_list.item(i).data(Qt.UserRole)
        }
        for course in state.get('courses', []):
            if not isinstance(course, dict):
                continue
            tc_id = course.get('JXBID', '')
            if not tc_id or tc_id in existing_ids:
                continue
            item = QListWidgetItem(self._build_grab_item_text(course))
            item.setData(Qt.UserRole, course)
            self.grab_list.addItem(item)
            existing_ids.add(tc_id)
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")

    def clear_monitor_state(self):
        """仅清除自动恢复标记，保留待选课程。"""
        self.save_monitor_state(is_monitoring=False)

    def write_watchdog_signal(self, action, pid=None):
        """写入 watchdog 信号文件"""
        signal_data = {
            'action': action,
            'timestamp': time.time(),
        }
        if pid is not None:
            signal_data['pid'] = pid

        try:
            write_json_atomic(WATCHDOG_SIGNAL_FILE, signal_data)
        except Exception as e:
            self._logger.error(f"写入 watchdog 信号失败: {e}")

    def start_watchdog_process(self):
        """按需启动守护进程（开始监控时调用）"""
        try:
            main_pid = os.getpid()

            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
                watchdog_exe = os.path.join(base_dir, 'Watchdog.exe')
                if not os.path.exists(watchdog_exe):
                    self._logger.warning(f"Watchdog.exe 不存在: {watchdog_exe}")
                    return

                subprocess.Popen(
                    [watchdog_exe, str(main_pid)],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                    start_new_session=True,
                    cwd=base_dir
                )
            else:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
                watchdog_script = os.path.join(base_dir, 'run_watchdog.py')
                if not os.path.exists(watchdog_script):
                    self._logger.warning(f"run_watchdog.py 不存在: {watchdog_script}")
                    return

                subprocess.Popen(
                    [sys.executable, watchdog_script, str(main_pid)],
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                    start_new_session=True,
                    cwd=base_dir
                )
        except Exception as e:
            self._logger.error(f"启动 watchdog 失败: {e}")

    def _auto_login_for_restore(self):
        """闪退恢复时自动登录"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            self.log("[WARN] 无法自动登录：缺少保存的用户名或密码")
            self._pending_restore_state = None
            self.clear_monitor_state()
            return
        
        self.log("[INFO] 正在自动登录以恢复监控...")
        self._is_manual_login_attempt = False
        self.login()

    def on_manual_login_clicked(self):
        """用户主动点击一键登录"""
        self._is_manual_login_attempt = True
        self.login()

    def login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            missing = "账号和密码" if not username and not password else "账号" if not username else "密码"
            self._logger.warning(f"登录输入检查失败：未填写{missing}")
            QMessageBox.warning(self, "提示", "请输入学号和密码")
            self._is_manual_login_attempt = False
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
    
    def on_login_success(self, cookies, token, batch_code, batch_name, student_code, campus):
        self.cookies = cookies
        self.token = token
        self.batch_code = batch_code
        self.batch_name = batch_name or ''
        self.student_code = student_code
        self.campus = campus  # 保存校区代码
        self.is_logged_in = True
        self._is_manual_login_attempt = False
        self._manual_login_fail_count = 0
        self._auto_relogin_retry_count = 0
        
        # 显示校区信息
        campus_name = "呈贡校区" if campus == "02" else "东陆校区" if campus == "01" else f"校区{campus}"
        self.status_label.setText(f"● 已登录 - {student_code} ({campus_name})")
        self.status_label.setStyleSheet(f"color: {Colors.GREEN}; font-weight: bold; font-size: 13px;")
        self.login_btn.setText("已登录")
        self.login_btn.setEnabled(False)
        self.logout_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.log(f"[SUCCESS] ✓ 登录成功！")
        self.log(f"[INFO] 校区: {campus_name} ({campus})")
        self.log("[INFO] Token 已获取")
        if self.batch_name and self.batch_name != self.batch_code:
            self.batch_label.setText(f"📅 选课批次: {self.batch_name} ({self.batch_code})")
            self.log(f"[INFO] Batch: {self.batch_name} ({self.batch_code})")
        else:
            self.batch_label.setText(f"📅 选课批次: {self.batch_code}")
            self.log(f"[INFO] BatchCode: {self.batch_code}")
        self.statusBar().showMessage("✓ 纯API模式已就绪，课程列表自动刷新中...")
        
        # 优先从状态文件恢复（闪退恢复）
        if self._pending_restore_state and self._pending_restore_state.get('courses'):
            courses = self._pending_restore_state['courses']
            self.log(f"[INFO] 从状态文件恢复 {len(courses)} 门监控课程")
            
            # 恢复并发数设置
            if 'concurrency' in self._pending_restore_state:
                self.concurrency_spin.setValue(self._pending_restore_state['concurrency'])
            
            # 添加课程到待抢列表
            for course in courses:
                tc_id = course.get('JXBID', '')
                exists = False
                for i in range(self.grab_list.count()):
                    item = self.grab_list.item(i)
                    if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                        exists = True
                        break
                
                if not exists:
                    display_text = self._build_grab_item_text(course)
                    
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, course)
                    self.grab_list.addItem(item)
            
            self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
            restored_conflict_policy = self._pending_restore_state.get('conflict_policy')
            self._active_conflict_policy = (
                restored_conflict_policy if isinstance(restored_conflict_policy, dict)
                else None
            )
            self._pending_restore_state = None
	            
            # 自动开始监控
            self.log("[INFO] 自动恢复监控中...")
            QTimer.singleShot(
                1000,
                lambda policy=restored_conflict_policy: self.start_monitoring(
                    conflict_policy=policy,
                    skip_policy_dialog=True
                )
            )
        elif self._pending_monitor_courses:
            self.log(f"[INFO] 检测到 {len(self._pending_monitor_courses)} 门待恢复课程")
            QTimer.singleShot(1000, self._resume_monitoring)
        else:
            QTimer.singleShot(300, self._start_polling)
    
    def on_login_failed(self, msg):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("🚀 一键登录")
        self.progress_bar.setVisible(False)
        self.log(f"[ERROR] 登录失败: {msg}")

        credentials_error = '登录名或密码不正确' in str(msg)
        if self._is_manual_login_attempt and credentials_error:
            self._manual_login_fail_count = 0
            QMessageBox.warning(self, "登录失败", "登录名或密码不正确，请检查后重试。")
            self.statusBar().showMessage("登录名或密码不正确")
        elif self._is_manual_login_attempt:
            self._manual_login_fail_count += 1
            remain = 5 - self._manual_login_fail_count
            if remain > 0:
                self.statusBar().showMessage(f"登录失败，已连续失败 {self._manual_login_fail_count} 次")
                self.log(f"[WARN] 手动登录连续失败 {self._manual_login_fail_count} 次")
            else:
                QMessageBox.warning(self, "登录失败", "连续登录失败 5 次，可能是用户名或密码错误，请检查后重试")
                self._manual_login_fail_count = 0

        self._is_manual_login_attempt = False
    
    def logout(self):
        self.poll_timer.stop()
        self._is_searching = False
        
        was_monitoring = self.multi_grab_worker is not None
        self.stop_monitoring(reason='logout')
        self.is_logged_in = False
        self.token = ''
        self.batch_code = ''
        self.batch_name = ''
        self.student_code = ''
        self.campus = '02'  # 重置为默认
        self.cookies = ''
        self.batch_label.setText("📅 选课批次: 自动识别")
        
        self.status_label.setText("● 未登录")
        self.status_label.setStyleSheet(f"color: {Colors.RED}; font-weight: bold; font-size: 13px;")
        self.login_btn.setText("🚀 一键登录")
        self.login_btn.setEnabled(True)
        self.logout_btn.setEnabled(False)
        
        self.course_list.clear()
        self.clear_cards()
        self._api_courses_grouped = {}
        
        if not was_monitoring:
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
        self._current_search_keyword = search_keyword
        
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
            campus=self.campus,  # 传入校区代码
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
                    self.log("[WARN] 检测到会话过期，开始自动重登...")
                    self._auto_relogin_and_resume()
            return
        
        # 成功获取，重置计数器
        self._fetch_retry_count = 0
        self._fetch_fail_count = 0

        # 本地搜索过滤：仅匹配课程名/教师名
        search_keyword = self._current_search_keyword.strip().lower() if self._current_search_keyword else ''
        if search_keyword and courses_grouped:
            filtered_grouped = {}
            for grouped_course_name, tc_list in courses_grouped.items():
                grouped_course_name_lower = str(grouped_course_name or '').lower()
                matched_tc_list = []

                for tc in tc_list or []:
                    teacher_name = str(tc.get('SKJS', '') or '').lower()
                    tc_course_name = str(tc.get('KCM', '') or '').lower()

                    if (search_keyword in grouped_course_name_lower
                            or search_keyword in tc_course_name
                            or search_keyword in teacher_name):
                        matched_tc_list.append(tc)

                if matched_tc_list:
                    filtered_grouped[grouped_course_name] = matched_tc_list

            courses_grouped = filtered_grouped
        
        if courses_grouped:
            if self._showing_search_empty_state:
                self.clear_cards()
                self.schedule_title.setText("📅 选择课程查看教学班")
                self._showing_search_empty_state = False

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
                if self._is_searching and search_keyword:
                    self.course_count_label.setText("未找到结果")
                    self.statusBar().showMessage("未找到结果")
                    self.show_search_empty_state(self._current_search_keyword)
                else:
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

    def show_search_empty_state(self, keyword):
        """显示搜索空结果状态"""
        self.clear_cards()
        self.schedule_title.setText("📅 未找到结果")

        empty_label = QLabel(f"未找到结果：{keyword}")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {Colors.OVERLAY0};
            padding: 30px 0;
        """)
        self.cards_layout.addWidget(empty_label, 0, 0, 1, 2)
        self._showing_search_empty_state = True
    
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

    def _to_bool(self, value):
        """统一布尔解析，兼容 0/1、true/false、yes/no 等字符串"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'1', 'true', 'yes', 'y', 'on'}:
                return True
            if normalized in {'0', 'false', 'no', 'n', 'off', ''}:
                return False
        return bool(value)

    def _build_grab_item_text(self, course):
        """构建待抢列表显示文本，图标顺序：冲突 -> 已满"""
        course_name = course.get('KCM', '')
        teacher = course.get('SKJS', '')

        is_conflict = self._to_bool(course.get('isConflict', False))
        is_full = self._to_bool(course.get('isFull', False))

        display_text = f"{course_name} - {teacher}"
        if is_conflict:
            display_text += " ⚠️"
        if is_full:
            display_text += " 🔴"

        return display_text
    
    def add_to_grab_list(self, course):
        tc_id = course.get('JXBID', '')
        course_name = course.get('KCM', '')
        teacher = course.get('SKJS', '')
        
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                QMessageBox.information(self, "提示", f"课程已在待抢列表中")
                return
        
        display_text = self._build_grab_item_text(course)
        
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, course)
        self.grab_list.addItem(item)
        
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        self.log(f"[INFO] 添加待抢: {course_name} - {teacher}")
        
        if self.multi_grab_worker and self.multi_grab_worker.isRunning():
            self.multi_grab_worker.add_course(course)
        self.save_monitor_state(
            is_monitoring=self.multi_grab_worker is not None
            and self.multi_grab_worker.isRunning()
        )
    
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
            self.save_monitor_state(
                is_monitoring=self.multi_grab_worker is not None
                and self.multi_grab_worker.isRunning()
            )

    def _course_time_text(self, course):
        return (
            course.get('SKSJ', '')
            or course.get('classTime', '')
            or course.get('time', '')
            or course.get('teachingTime', '')
            or ''
        )

    def _parse_time_slots(self, time_str):
        if not time_str:
            return []

        slots = []
        segments = re.split(r'[,;，；/]', str(time_str))
        day_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7,
            '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
        }

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            slot = {'weeks': set(), 'day': 0, 'periods': set()}

            week_match = re.search(r'第?(\d+)-(\d+)周(?:\(([单双])\))?', segment)
            if week_match:
                start_week = int(week_match.group(1))
                end_week = int(week_match.group(2))
                odd_even = week_match.group(3)
                for week in range(start_week, end_week + 1):
                    if odd_even == '单' and week % 2 == 0:
                        continue
                    if odd_even == '双' and week % 2 == 1:
                        continue
                    slot['weeks'].add(week)
            else:
                single_week = re.search(r'第?(\d+)周', segment)
                if single_week:
                    slot['weeks'].add(int(single_week.group(1)))

            day_match = re.search(r'(?:星期|周|礼拜)([一二三四五六日天1-7])', segment)
            if day_match:
                slot['day'] = day_map.get(day_match.group(1), 0)

            period_match = re.search(r'第?(\d+)-(\d+)节', segment)
            if period_match:
                start_period = int(period_match.group(1))
                end_period = int(period_match.group(2))
                for period in range(start_period, end_period + 1):
                    slot['periods'].add(period)
            else:
                period_singles = re.findall(r'第(\d+)节', segment)
                if period_singles:
                    for period in period_singles:
                        slot['periods'].add(int(period))
                else:
                    period_singles = re.findall(r'(\d+)节', segment)
                    for period in period_singles:
                        slot['periods'].add(int(period))
                    comma_periods = re.search(r'(\d+(?:,\d+)+)节', segment)
                    if comma_periods:
                        for period in comma_periods.group(1).split(','):
                            if period.strip():
                                slot['periods'].add(int(period.strip()))

            if slot['weeks'] and slot['day'] and slot['periods']:
                slots.append(slot)
            elif slot['day'] and slot['periods']:
                slot['weeks'] = set(range(1, 19))
                slots.append(slot)

        return slots

    def _check_time_conflict(self, time_str1, time_str2):
        slots1 = self._parse_time_slots(time_str1)
        slots2 = self._parse_time_slots(time_str2)
        if not slots1 or not slots2:
            return False

        for slot1 in slots1:
            for slot2 in slots2:
                if slot1['day'] != slot2['day']:
                    continue
                if not (slot1['weeks'] & slot2['weeks']):
                    continue
                if slot1['periods'] & slot2['periods']:
                    return True
        return False

    def _build_pending_conflict_groups(self, courses):
        """按待抢课程之间的时间冲突构建连通冲突组。"""
        indexed = []
        for index, course in enumerate(courses):
            tc_id = str(course.get('JXBID', '') or '')
            time_text = self._course_time_text(course)
            if tc_id and time_text:
                indexed.append((index, course, tc_id, time_text))

        edges = {item[2]: set() for item in indexed}
        course_by_id = {item[2]: item[1] for item in indexed}
        for left_pos in range(len(indexed)):
            _, left_course, left_id, left_time = indexed[left_pos]
            for right_pos in range(left_pos + 1, len(indexed)):
                _, right_course, right_id, right_time = indexed[right_pos]
                if self._check_time_conflict(left_time, right_time):
                    edges[left_id].add(right_id)
                    edges[right_id].add(left_id)

        groups = []
        visited = set()
        for tc_id in edges:
            if tc_id in visited or not edges[tc_id]:
                continue
            stack = [tc_id]
            component = []
            visited.add(tc_id)
            while stack:
                current = stack.pop()
                component.append(course_by_id[current])
                for neighbor in edges[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)
            if len(component) >= 2:
                groups.append(component)
        return groups

    def _show_pending_conflict_policy_dialog(self, groups):
        """提示待抢列表内部冲突，并让用户选择每组首选课程。"""
        if not groups:
            return {"enabled": True, "groups": []}

        dialog = QDialog(self)
        dialog.setWindowTitle("⚠️ 待抢列表内部冲突")
        dialog.setMinimumWidth(760)
        dialog.setMinimumHeight(520)

        layout = QVBoxLayout(dialog)
        intro = QLabel(
            "检测到待抢列表里有课程之间时间互相冲突。\n\n"
            "默认安全策略：同一冲突组里，只要任意一门抢成功，就自动停止本组其它待抢课程，"
            "避免程序后续又把刚抢到的课当作冲突课退掉。\n\n"
            "如果你给某组选择了“首选优先级”：非首选课程先抢到时，首选课程仍会继续监控；"
            "后续首选课程出现余量时，可能触发自动换课。注意：换课需要先退旧课再抢新课，"
            "不能保证一定抢到或一定回滚成功，请慎重选择。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        combo_records = []

        for index, group in enumerate(groups, start=1):
            frame = QFrame()
            frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {Colors.SURFACE0};
                    border: 1px solid {Colors.SURFACE2};
                    border-radius: 10px;
                    padding: 8px;
                }}
            """)
            frame_layout = QVBoxLayout(frame)
            title = QLabel(f"冲突组 {index}")
            title.setStyleSheet(f"font-weight: bold; color: {Colors.YELLOW};")
            frame_layout.addWidget(title)

            detail_lines = []
            for course in group:
                course_name = course.get('KCM', '') or '未知课程'
                teacher = course.get('SKJS', '') or '未知教师'
                time_text = self._course_time_text(course) or '时间未知'
                detail_lines.append(f"• {course_name} - {teacher}｜{time_text}")
            detail = QLabel("\n".join(detail_lines))
            detail.setWordWrap(True)
            frame_layout.addWidget(detail)

            combo = QComboBox()
            combo.addItem("默认：抢到任意一门就停止本组其它课程", "")
            for course in group:
                course_name = course.get('KCM', '') or '未知课程'
                teacher = course.get('SKJS', '') or '未知教师'
                combo.addItem(f"首选：{course_name} - {teacher}", str(course.get('JXBID', '') or ''))
            frame_layout.addWidget(combo)
            combo_records.append((index, group, combo))
            container_layout.addWidget(frame)

        container_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("按此策略开始监控")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addWidget(buttons)

        result = {"accepted": False, "policy": None}

        def accept_policy():
            policy_groups = []
            for index, group, combo in combo_records:
                preferred_id = str(combo.currentData() or '')
                preferred_name = ''
                for course in group:
                    if str(course.get('JXBID', '') or '') == preferred_id:
                        preferred_name = course.get('KCM', '') or '未知课程'
                        break
                policy_groups.append({
                    "id": f"pending_conflict_group_{index}",
                    "course_ids": [str(course.get('JXBID', '') or '') for course in group],
                    "preferred_id": preferred_id,
                    "preferred_name": preferred_name,
                })
            result["accepted"] = True
            result["policy"] = {"enabled": True, "groups": policy_groups}
            dialog.accept()

        buttons.accepted.connect(accept_policy)
        buttons.rejected.connect(dialog.reject)
        dialog.exec_()

        if not result["accepted"]:
            return None
        return result["policy"]

    def _build_default_conflict_policy(self, groups):
        """为静默恢复构建默认冲突组策略：抢到任意一门即停止本组其它课程。"""
        policy_groups = []
        for index, group in enumerate(groups, start=1):
            policy_groups.append({
                "id": f"pending_conflict_group_{index}",
                "course_ids": [str(course.get('JXBID', '') or '') for course in group],
                "preferred_id": "",
                "preferred_name": "",
            })
        return {"enabled": True, "groups": policy_groups}

    def _log_conflict_policy(self, conflict_policy, restored=False):
        groups = conflict_policy.get('groups', []) if isinstance(conflict_policy, dict) else []
        if not groups:
            return
        prefix = "恢复待抢冲突组策略" if restored else "待抢冲突组策略"
        for group in groups:
            preferred_name = group.get('preferred_name') or ''
            if preferred_name:
                self.log(
                    f"[INFO] {prefix}: 首选 {preferred_name}；"
                    "非首选先成功时首选继续监控"
                )
            else:
                self.log(f"[INFO] {prefix}: 默认抢到任意一门即停止本组其它课程")

    def start_monitoring(self, conflict_policy=None, skip_policy_dialog=False):
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

        pending_conflict_groups = self._build_pending_conflict_groups(courses)
        if skip_policy_dialog:
            if not isinstance(conflict_policy, dict):
                conflict_policy = self._build_default_conflict_policy(pending_conflict_groups)
                if conflict_policy.get('groups'):
                    self.log("[WARN] 未找到上次冲突组策略，恢复时按默认安全策略继续监控")
            else:
                self.log("[INFO] 已复用上次待抢冲突组策略，恢复监控不再弹窗确认")
            self._log_conflict_policy(conflict_policy, restored=True)
        else:
            conflict_policy = self._show_pending_conflict_policy_dialog(pending_conflict_groups)
            if conflict_policy is None:
                self.log("[INFO] 用户取消启动：未确认待抢列表内部冲突策略")
                return
            self._log_conflict_policy(conflict_policy)

        self._active_conflict_policy = conflict_policy

        conflict_courses = [
            course for course in courses
            if self._to_bool(course.get('isConflict', False))
            or bool(str(course.get('conflictDesc', '') or '').strip())
        ]
        if conflict_courses:
            names = [str(course.get('KCM', '') or '未知课程') for course in conflict_courses]
            preview = '、'.join(names[:5])
            if len(names) > 5:
                preview += f" 等 {len(names)} 门"
            reply = QMessageBox.warning(
                self,
                "⚠️ 冲突换课风险确认",
                f"检测到待选课程与当前已选课程存在时间冲突：\n\n{preview}\n\n"
                "自动换课需要先退掉冲突的旧课程，再尝试选择目标课程。"
                "在多人同时抢课、旧课名额被他人占用或网络异常时，"
                "目标课程可能抢不到，旧课程也无法保证回滚成功。\n\n"
                "请确认你已理解风险，并慎重决定是否继续监控。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.log("[INFO] 用户取消启动：未接受冲突换课风险")
                return
        
        # 获取 Server酱 key
        serverchan_key = ''
        if self.serverchan_enabled:
            serverchan_key = self.serverchan_key_input.text().strip()
            self.serverchan_key = serverchan_key

        webhook_channels = []
        if self.developer_mode_enabled:
            valid, error = validate_webhook_channels(self.developer_webhooks)
            if valid:
                webhook_channels = normalize_webhook_channels(self.developer_webhooks)
            else:
                self.log(f"[WARN] 自定义 Webhook 配置无效，本次未启用: {error}")
	        
        self.log(f"[INFO] 开始监控 {len(courses)} 门课程 (HTTP并发: {self.concurrency_spin.value()})")
        if serverchan_key:
            self.log(f"[INFO] Server酱通知已启用")
        if webhook_channels:
            enabled_count = sum(1 for item in webhook_channels if item.get('enabled', True))
            self.log(f"[INFO] 开发者模式自定义 Webhook 已启用，启用通道: {enabled_count}")
	        
        self.multi_grab_worker = MultiGrabWorker(
            courses=courses,
            student_code=self.student_code,
            batch_code=self.batch_code,
            token=self.token,
            cookies=self.cookies,
            campus=self.campus,  # 传入校区代码
            username=self.username_input.text(),
            password=self.password_input.text(),
            max_workers=self.concurrency_spin.value(),
            serverchan_key=serverchan_key,
            webhook_channels=webhook_channels,
            conflict_policy=conflict_policy,
        )
        
        self.multi_grab_worker.success.connect(self.on_grab_success)
        self.multi_grab_worker.failed.connect(self.on_grab_failed)
        self.multi_grab_worker.status.connect(self.on_grab_status)
        self.multi_grab_worker.need_relogin.connect(self.on_need_relogin)
        self.multi_grab_worker.course_available.connect(self.on_course_available)
        self.multi_grab_worker.session_updated.connect(self.on_session_updated)
        self.multi_grab_worker.finished.connect(self.on_worker_finished)
        self.multi_grab_worker.heartbeat.connect(self.update_heartbeat)
        self.multi_grab_worker.courses_retired.connect(self.on_courses_retired)

        # 写入守护信号并按需启动 watchdog
        self.write_watchdog_signal('start', pid=os.getpid())
        self.start_watchdog_process()
        
        self.multi_grab_worker.start()

        # 立即保存监控状态（即使程序崩溃也能恢复）
        self.save_monitor_state(is_monitoring=True)
        
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
    
    def stop_monitoring(self, clear_state=True, reason='manual'):
        was_monitoring = self.multi_grab_worker is not None

        if self.multi_grab_worker:
            self.multi_grab_worker.stop()
            wait_ms = 10000 if reason == 'update' else 5000
            if not self.multi_grab_worker.wait(wait_ms):
                self._logger.warning(f"停止监控超时: reason={reason}")
                if reason == 'update':
                    return False
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
        if reason == 'logout':
            if was_monitoring:
                self.statusBar().showMessage("👋 已退出登录（监控已停止）")
                self.log("[INFO] 已退出登录（监控已停止）")
            else:
                self.statusBar().showMessage("👋 已退出登录")
        elif reason == 'relogin':
            if was_monitoring:
                self.statusBar().showMessage("🔐 会话过期，监控已暂停")
                self.log("[WARN] 会话过期，监控已暂停，准备自动重登")
            else:
                self.statusBar().showMessage("🔐 会话过期，准备自动重登")
        elif reason == 'close':
            # 关闭程序时不追加停止日志，避免与手动停止混淆
            pass
        elif reason == 'update':
            self.statusBar().showMessage("🔄 正在退出并安装更新")
            self.log("[INFO] 更新安装前已停止监控")
        else:
            self.statusBar().showMessage("⏹ 监控已停止")
            self.log("[INFO] 监控已停止")
        
        # 只有用户主动停止时才清除状态文件
        if clear_state:
            self.write_watchdog_signal('stop')
            self.clear_monitor_state()
            if reason not in ('relogin',):
                self._active_conflict_policy = None
        return True
    
    def on_grab_success(self, msg, course):
        """抢课成功回调 - 带异常保护"""
        try:
            self.log(f"[SUCCESS] ✅ {msg}")
            
            tc_id = course.get('JXBID', '') if course else ''
            for i in range(self.grab_list.count()):
                item = self.grab_list.item(i)
                if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                    self.grab_list.takeItem(i)
                    break
            
            self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
            self.save_monitor_state(
                is_monitoring=self.multi_grab_worker is not None
                and self.multi_grab_worker.isRunning()
            )
            QMessageBox.information(self, "🎉 抢课成功", msg)
        except Exception as e:
            try:
                self._logger.error(f"on_grab_success 异常: {str(e)[:50]}")
            except Exception:
                pass

    def on_courses_retired(self, tc_ids, reason):
        """worker 自动停止冲突待抢课程后，同步刷新 UI 列表。"""
        try:
            remove_ids = {str(tc_id) for tc_id in (tc_ids or [])}
            if not remove_ids:
                return
            for i in range(self.grab_list.count() - 1, -1, -1):
                item = self.grab_list.item(i)
                course = item.data(Qt.UserRole) if item else None
                if course and str(course.get('JXBID', '') or '') in remove_ids:
                    self.grab_list.takeItem(i)

            self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
            self.log(f"[INFO] {reason}")
            self.save_monitor_state(
                is_monitoring=self.multi_grab_worker is not None
                and self.multi_grab_worker.isRunning()
            )
        except Exception as e:
            try:
                self._logger.error(f"on_courses_retired 异常: {str(e)[:50]}")
            except Exception:
                pass
    
    def on_grab_failed(self, msg):
        """抢课失败回调 - 带异常保护"""
        try:
            self.log(f"[ERROR] {msg}")
        except Exception:
            pass
    
    def on_grab_status(self, msg):
        """状态更新回调 - 带异常保护"""
        try:
            self.log(msg)
            self.statusBar().showMessage(msg)
        except Exception:
            pass
    
    def on_session_updated(self, token, cookies):
        """Session 更新回调 - 带异常保护"""
        try:
            self.token = token
            self.cookies = cookies
            self.log("[INFO] Session 已同步更新")
        except Exception:
            pass
    
    def on_worker_finished(self):
        """Worker 完成回调 - 带异常保护"""
        try:
            self.start_grab_btn.setEnabled(True)
            self.stop_grab_btn.setEnabled(False)
            
            if self._pending_monitor_courses and not self.is_logged_in:
                self.log("[INFO] Worker 异常退出，尝试自动重登...")
                self._auto_relogin_and_resume()
        except Exception as e:
            try:
                self._logger.error(f"on_worker_finished 异常: {str(e)[:50]}")
            except Exception:
                pass
    
    def on_need_relogin(self):
        """需要重登回调 - 带异常保护"""
        try:
            self.log("[WARN] Session过期，准备自动重登...")
            
            pending_courses = []
            for i in range(self.grab_list.count()):
                item = self.grab_list.item(i)
                course = item.data(Qt.UserRole)
                if course:
                    pending_courses.append(course)
            
            self._pending_monitor_courses = pending_courses
            self._pending_resume_conflict_policy = self._active_conflict_policy
            self.log(f"[INFO] 已保存 {len(pending_courses)} 门待抢课程")
	            
            self.stop_monitoring(clear_state=False, reason='relogin')
            self._auto_relogin_and_resume()
        except Exception as e:
            try:
                self._logger.error(f"on_need_relogin 异常: {str(e)[:50]}")
            except Exception:
                pass
    
    def _auto_relogin_and_resume(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            self.log("[ERROR] 无法自动重登：缺少用户名或密码")
            return
        
        self._is_manual_login_attempt = False
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
        if '登录名或密码不正确' in str(msg):
            self._auto_relogin_retry_count = 0
            self.save_monitor_state(is_monitoring=False)
            self.statusBar().showMessage("自动重登已停止：请重新输入正确的账号密码")
            QMessageBox.warning(self, "自动重登已停止", "保存的账号或密码不正确，请修改后重新登录。")
            return
        self._auto_relogin_retry_count += 1
        retry_delay_ms = min(10000, 2000 * self._auto_relogin_retry_count)
        self.log(f"[INFO] {retry_delay_ms // 1000}s 后自动重试重登 (第 {self._auto_relogin_retry_count} 次)")
        self.statusBar().showMessage("自动重登失败，正在重试...")
        QTimer.singleShot(retry_delay_ms, self._auto_relogin_and_resume)
    
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
                display_text = self._build_grab_item_text(course)
                
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, course)
                self.grab_list.addItem(item)
        
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        self._pending_monitor_courses = []
	        
        resume_policy = self._pending_resume_conflict_policy or self._active_conflict_policy
        self._pending_resume_conflict_policy = None
        QTimer.singleShot(
            500,
            lambda policy=resume_policy: self.start_monitoring(
                conflict_policy=policy,
                skip_policy_dialog=True
            )
        )
    
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
        """程序关闭事件"""
        if self._installing_update:
            # 更新流程已经保存过状态并停止 Watchdog，避免把恢复标记覆盖为 False。
            self.save_config()
            event.accept()
            return

        # 保存监控状态（如果正在监控中则标记 is_monitoring=True，用于重启恢复）
        is_monitoring = self.multi_grab_worker is not None and self.multi_grab_worker.isRunning()
        self.save_monitor_state(is_monitoring=is_monitoring)
        
        self.poll_timer.stop()
        # 关闭程序时不清除状态文件，让程序可以自动重启恢复
        self.stop_monitoring(clear_state=False, reason='close')
        self.save_config()
        event.accept()
