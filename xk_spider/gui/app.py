"""
云南大学选课助手 - GUI主程序（精简版）
"""
import sys
import os
import json
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QTextEdit, QProgressBar, QMessageBox, QFrame, QGridLayout, QSizePolicy,
    QGroupBox, QSpinBox, QScrollArea, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# Pillow 兼容补丁
from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

try:
    import ddddocr
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，支持打包后的exe"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的临时目录
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# 课程类型映射
COURSE_TYPES = {
    '推荐课程': 'TJKC',
    '主修课程': 'ZXKC',
    '通识教育选修课程': 'TSKC',
    '公共体育课': 'TYKC',
}

# Tab ID 映射
TAB_MAP = {
    'TJKC': 'aRecommendCourse',
    'ZXKC': 'aProgramCourse',
    'TSKC': 'aPublicCourse',
    'TYKC': 'aSportCourse',
}


class CourseCard(QFrame):
    """排课卡片"""
    grab_clicked = pyqtSignal(dict)
    
    def __init__(self, course_data, parent=None):
        super().__init__(parent)
        self.course_data = course_data
        self.init_ui()
        
    def init_ui(self):
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setMinimumSize(280, 190)
        self.setMaximumWidth(360)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(14, 12, 14, 12)
        
        is_conflict = self.course_data.get('isConflict', False)
        volunteer_type = self.course_data.get('volunteerType', '')
        
        # 教师名
        teacher = self.course_data.get('SKJS', '未知')
        teacher_label = QLabel(f"👨‍🏫 {teacher}")
        teacher_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #1d1d1f;")
        layout.addWidget(teacher_label)
        
        # 志愿类型标签（如果有）
        if volunteer_type:
            vol_color = "#ff3b30" if volunteer_type == "第一志愿" else "#34c759"
            vol_label = QLabel(f"🏷️ {volunteer_type}")
            vol_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {vol_color};")
            layout.addWidget(vol_label)
        
        # 时间地点
        time_str = self.course_data.get('SKSJ', '')
        if time_str:
            time_label = QLabel(f"🕐 {time_str}")
            time_label.setStyleSheet("font-size: 11px; color: #0066cc;")
            time_label.setWordWrap(True)
            layout.addWidget(time_label)
        
        # 容量进度条
        first_vol = int(self.course_data.get('DYZY', 0) or 0)
        capacity = int(self.course_data.get('KRL', 0) or 0)
        remain = capacity - first_vol
        
        # 容量文字
        status_color = "#34c759" if remain > 0 else "#ff3b30"
        cap_label = QLabel(f"📊 {first_vol}/{capacity}  余: {remain}")
        cap_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {status_color};")
        layout.addWidget(cap_label)
        
        # 进度条
        progress = QProgressBar()
        progress.setMaximum(capacity if capacity > 0 else 1)
        progress.setValue(first_vol)
        progress.setTextVisible(False)
        progress.setFixedHeight(6)
        if remain > 0:
            progress.setStyleSheet("QProgressBar { background-color: #e8e8ed; border-radius: 3px; } QProgressBar::chunk { background-color: #34c759; border-radius: 3px; }")
        else:
            progress.setStyleSheet("QProgressBar { background-color: #e8e8ed; border-radius: 3px; } QProgressBar::chunk { background-color: #ff3b30; border-radius: 3px; }")
        layout.addWidget(progress)
        
        layout.addStretch()
        
        # 加入待抢按钮
        grab_btn = QPushButton("🎯 加入待抢")
        grab_btn.setFixedHeight(34)
        
        if is_conflict:
            grab_btn.setEnabled(False)
            if volunteer_type == "第一志愿":
                grab_btn.setText("X 第一志愿已报")
            elif volunteer_type == "第二志愿":
                grab_btn.setText("! 第二志愿已报")
            elif volunteer_type == "第三志愿":
                grab_btn.setText("! 第三志愿已报")
            else:
                grab_btn.setText("X 不可选")
            grab_btn.setStyleSheet("background-color: #d2d2d7; color: #86868b; border: none; border-radius: 6px;")
        elif volunteer_type:
            if volunteer_type == "第二志愿":
                grab_btn.setText("! 第二志愿已报")
            elif volunteer_type == "第三志愿":
                grab_btn.setText("! 第三志愿已报")
            grab_btn.setStyleSheet("background-color: #34c759; color: #ffffff; font-weight: bold; border: none; border-radius: 6px;")
            grab_btn.clicked.connect(lambda: self.grab_clicked.emit(self.course_data))
        else:
            grab_btn.setStyleSheet("background-color: #0066cc; color: #ffffff; font-weight: bold; border: none; border-radius: 6px;")
            grab_btn.clicked.connect(lambda: self.grab_clicked.emit(self.course_data))
        layout.addWidget(grab_btn)
        
        # 卡片样式
        border_color = "#ff3b30" if is_conflict else "#d2d2d7"
        self.setStyleSheet(f"""
            CourseCard {{ 
                background-color: #ffffff; 
                border: 1px solid {border_color}; 
                border-radius: 10px; 
            }}
        """)


class LoginWorker(QThread):
    """登录工作线程"""
    success = pyqtSignal(str, str, str, str, object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)
    
    LOGIN_URL = "https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/*default/index.do"
    
    def __init__(self, driver_path, username, password, selected_round="1"):
        super().__init__()
        self.driver_path = driver_path
        self.username = username
        self.password = password
        self.selected_round = selected_round
        self.driver = None
        self.ocr = None
        
        if OCR_AVAILABLE:
            try:
                self.ocr = ddddocr.DdddOcr()
            except:
                pass
    
    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--window-size=1920,1080')  # 设置窗口大小，确保验证码能正确截取
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # 获取正确的 chromedriver 路径（支持打包后的exe）
        driver_path = self.driver_path
        if driver_path:
            # 如果是相对路径，转换为绝对路径
            if not os.path.isabs(driver_path):
                driver_path = get_resource_path(driver_path)
            
            if os.path.exists(driver_path):
                service = Service(executable_path=driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # 路径不存在，尝试让 selenium 自动查找
                self.driver = webdriver.Chrome(options=chrome_options)
        else:
            self.driver = webdriver.Chrome(options=chrome_options)
        
        # 设置窗口大小（双重保险）
        self.driver.set_window_size(1920, 1080)
        
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
    
    def _recognize_captcha(self):
        """识别验证码"""
        for attempt in range(2):
            try:
                time.sleep(0.8)
                
                # 等待验证码图片加载
                captcha_img = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, 'vcodeImg'))
                )
                
                # 等待图片完全加载
                time.sleep(0.5)
                
                # 截取验证码图片
                img_bytes = captcha_img.screenshot_as_png
                
                if self.ocr and img_bytes and len(img_bytes) > 100:
                    result = self.ocr.classification(img_bytes)
                    if result:
                        # 只保留ASCII字母数字，过滤乱码
                        clean_result = ''.join(c for c in result if c.isalnum() and ord(c) < 128)
                        if len(clean_result) >= 4:
                            code = clean_result[:4]
                            print(f"[INFO] 验证码: {code}")
                            return code
                
                # 识别失败，点击刷新验证码
                print(f"[WARN] 验证码识别失败({attempt + 1}/2)，刷新...")
                captcha_img.click()
                time.sleep(1)
                
            except Exception as e:
                print(f"[ERROR] 验证码异常: {str(e)[:50]}")
                time.sleep(0.5)
        
        return None
    
    def _auto_login(self):
        """自动登录"""
        for attempt in range(10):
            try:
                self.status.emit(f"正在登录 (第{attempt + 1}次)...")
                
                # 等待登录表单
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.ID, 'loginName'))
                    )
                except TimeoutException:
                    self.driver.refresh()
                    time.sleep(2)
                    continue
                
                # 识别验证码
                captcha_code = self._recognize_captcha()
                if not captcha_code:
                    self.driver.refresh()
                    continue
                
                # 填写表单
                self.driver.find_element(By.ID, 'loginName').clear()
                self.driver.find_element(By.ID, 'loginName').send_keys(self.username)
                self.driver.find_element(By.ID, 'loginPwd').clear()
                self.driver.find_element(By.ID, 'loginPwd').send_keys(self.password)
                self.driver.find_element(By.ID, 'verifyCode').clear()
                self.driver.find_element(By.ID, 'verifyCode').send_keys(captcha_code)
                
                # 循环点击登录直到出现轮次选择弹窗
                for click in range(15):
                    self.driver.execute_script("document.getElementById('studentLoginBtn').click();")
                    time.sleep(1.5)
                    
                    # 检查错误
                    error_text = self.driver.execute_script("""
                        var err = document.getElementById('errorMsg');
                        return err && err.style.display !== 'none' ? err.textContent : '';
                    """)
                    if "验证码" in error_text:
                        # 验证码错误，点击图片刷新验证码
                        print("[WARN] 验证码不正确，刷新重试")
                        self.driver.execute_script("document.getElementById('vcodeImg').click();")
                        time.sleep(1)
                        # 重新识别验证码
                        captcha_code = self._recognize_captcha()
                        if captcha_code:
                            self.driver.find_element(By.ID, 'verifyCode').clear()
                            self.driver.find_element(By.ID, 'verifyCode').send_keys(captcha_code)
                        continue
                    if "密码" in error_text or "认证" in error_text:
                        self.status.emit("账号或密码错误！")
                        return False
                    
                    # 检查轮次弹窗
                    has_batch = self.driver.execute_script("""
                        return document.querySelector('input[name="electiveBatchSelect"]') !== null
                            && document.querySelector('.jqx-window-content') !== null;
                    """)
                    if has_batch:
                        self._process_batch_selection()
                        return True
                
            except Exception as e:
                print(f"[ERROR] 登录出错: {e}")
        
        return False
    
    def _process_batch_selection(self):
        """处理轮次选择"""
        target = "第一轮" if self.selected_round == "1" else "第二轮"
        
        # 选择轮次
        self.driver.execute_script("""
            var target = arguments[0];
            var radios = document.querySelectorAll('input[name="electiveBatchSelect"]');
            for (var r of radios) {
                var data = r.getAttribute('data-value');
                if (data && data.indexOf(target) >= 0) { r.click(); break; }
            }
        """, target)
        time.sleep(0.3)
        
        # 点确定
        self.driver.execute_script("""
            var btns = document.querySelectorAll('button.bh-btn-primary');
            for (var b of btns) { if (b.textContent.trim() === '确定') { b.click(); break; } }
        """)
    
    def _do_single_login_attempt(self):
        """执行单次登录尝试"""
        try:
            # 先检查是否有验证码错误
            error_text = self.driver.execute_script("""
                var err = document.getElementById('errorMsg');
                return err && err.style.display !== 'none' ? err.textContent : '';
            """) or ''
            
            if "验证码" in error_text:
                # 验证码错误，刷新并重新识别
                print("[WARN] 验证码不正确，刷新重新识别...")
                self.driver.execute_script("document.getElementById('vcodeImg').click();")
                time.sleep(0.8)
                captcha_code = self._recognize_captcha()
                if captcha_code:
                    self.driver.find_element(By.ID, 'verifyCode').clear()
                    self.driver.find_element(By.ID, 'verifyCode').send_keys(captcha_code)
                    print(f"[INFO] 重新填写验证码: {captcha_code}")
                    # 点击登录
                    self.driver.execute_script("document.getElementById('studentLoginBtn').click();")
                return
            
            # 检查验证码是否已输入
            vcode_value = self.driver.execute_script("""
                var el = document.getElementById('verifyCode');
                return el ? el.value : '';
            """) or ''
            
            if len(vcode_value) < 4:
                # 识别验证码
                captcha_code = self._recognize_captcha()
                if captcha_code:
                    # 填写表单
                    self.driver.find_element(By.ID, 'loginName').clear()
                    self.driver.find_element(By.ID, 'loginName').send_keys(self.username)
                    self.driver.find_element(By.ID, 'loginPwd').clear()
                    self.driver.find_element(By.ID, 'loginPwd').send_keys(self.password)
                    self.driver.find_element(By.ID, 'verifyCode').clear()
                    self.driver.find_element(By.ID, 'verifyCode').send_keys(captcha_code)
            
            # 点击登录按钮
            self.driver.execute_script("document.getElementById('studentLoginBtn').click();")
                
        except Exception as e:
            print(f"[ERROR] 登录尝试失败: {e}")
    
    def run(self):
        try:
            self.status.emit("正在启动浏览器...")
            self._init_driver()
            self.driver.get(self.LOGIN_URL)
            self.driver.implicitly_wait(5)
            
            # 实时监控页面状态，每秒检测一次，10秒没完成就刷新
            login_start_time = time.time()
            max_login_time = 10  # 10秒超时
            
            while True:
                try:
                    elapsed = time.time() - login_start_time
                    
                    # 检测页面状态
                    page_state = self.driver.execute_script("""
                        // 1. 检查是否已进入选课页面（有课程数据）
                        if (document.getElementById('aPublicCourse')) {
                            return 'logged_in';
                        }
                        // 2. 检查开始选课按钮
                        var courseBtn = document.getElementById('courseBtn');
                        if (courseBtn && courseBtn.offsetWidth > 0) {
                            return 'start_btn';
                        }
                        // 3. 检查轮次选择
                        if (document.querySelector('input[name="electiveBatchSelect"]')) {
                            return 'batch_select';
                        }
                        // 4. 检查登录页面
                        if (document.getElementById('loginName')) {
                            return 'login_page';
                        }
                        return 'unknown';
                    """)
                    
                    print(f"[DEBUG] 登录监控 - 页面状态: {page_state} ({int(elapsed)}秒)")
                    self.status.emit(f"页面状态: {page_state} ({int(elapsed)}秒)")
                    
                    if page_state == 'logged_in':
                        # 已进入选课页面，获取token
                        break
                    
                    elif page_state == 'start_btn':
                        # 点击开始选课按钮
                        self.status.emit("点击开始选课...")
                        self.driver.execute_script("document.getElementById('courseBtn').click();")
                        login_start_time = time.time()  # 重置计时
                        time.sleep(1)
                    
                    elif page_state == 'batch_select':
                        # 选择轮次
                        self.status.emit("选择轮次...")
                        self._process_batch_selection()
                        login_start_time = time.time()  # 重置计时
                        time.sleep(1)
                    
                    elif page_state == 'login_page':
                        # 执行登录
                        self.status.emit("执行登录...")
                        self._do_single_login_attempt()
                        login_start_time = time.time()  # 重置计时
                        time.sleep(1)
                    
                    else:
                        # 未知状态，等待
                        time.sleep(1)
                    
                    # 超时检测
                    if elapsed > max_login_time:
                        self.status.emit(f"登录超时({int(elapsed)}秒)，刷新页面...")
                        self.driver.refresh()
                        login_start_time = time.time()  # 重置计时
                        time.sleep(2)
                    
                except Exception as e:
                    error_msg = str(e)
                    # 检测浏览器是否被关闭
                    if 'no such window' in error_msg or 'target window already closed' in error_msg or 'web view not found' in error_msg or 'invalid session id' in error_msg:
                        self.failed.emit("浏览器已关闭，请重新登录")
                        self.driver = None
                        return
                    print(f"[ERROR] 监控页面出错: {e}")
                    time.sleep(1)
            
            # 循环获取token和batchCode
            token, batch_code = '', ''
            for _ in range(30):
                try:
                    time.sleep(1)
                    token = self.driver.execute_script('return sessionStorage.getItem("token");') or ''
                    batch_str = self.driver.execute_script('return sessionStorage.getItem("currentBatch");') or ''
                    if batch_str:
                        try:
                            batch_code = json.loads(batch_str).get('code', '')
                        except:
                            pass
                    if token and batch_code:
                        break
                except Exception as e:
                    error_msg = str(e)
                    if 'no such window' in error_msg or 'target window already closed' in error_msg or 'web view not found' in error_msg or 'invalid session id' in error_msg:
                        self.failed.emit("浏览器已关闭，请重新登录")
                        self.driver = None
                        return
            
            if not token or not batch_code:
                self.failed.emit("登录信息获取失败")
                return
            
            cookies = '; '.join([f"{c['name']}={c['value']}" for c in self.driver.get_cookies()])
            
            print(f'[SUCCESS] 登录成功！')
            print(f'  Token: {token[:20]}...')
            print(f'  BatchCode: {batch_code}')
            print(f'  StudentCode: {self.username}')
            
            self.success.emit(cookies, token, batch_code, self.username, self.driver)
            
        except TimeoutException:
            self.failed.emit("登录超时")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
        except Exception as e:
            error_msg = str(e)
            # 检测浏览器是否被关闭
            if 'no such window' in error_msg or 'target window already closed' in error_msg or 'web view not found' in error_msg or 'invalid session id' in error_msg:
                self.failed.emit("浏览器已关闭，请重新登录")
                self.driver = None
                return
            self.failed.emit(f"登录错误: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass


class GrabWorker(QThread):
    """抢课监控线程"""
    success = pyqtSignal(str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)
    need_relogin = pyqtSignal()
    
    # 板块Tab ID映射
    TAB_IDS = {
        'public': 'aPublicCourse',      # 通识教育选修课程
        'recommend': 'aRecommendCourse', # 推荐课程
        'major': 'aProgramCourse',       # 主修课程
        'sport': 'aSportCourse',         # 公共体育课
    }
    
    # 页码元素ID映射
    PAGE_IDS = {
        'public': 'publicPageNumber',
        'recommend': 'recommendPageNumber',
        'major': 'programPageNumber',
        'sport': 'sportPageNumber',
    }
    
    def __init__(self, driver, course_info, student_code, batch_code):
        super().__init__()
        self.driver = driver
        self.course_info = course_info
        self.student_code = student_code
        self.batch_code = batch_code
        self._running = True
        
        # 记录课程所在位置
        self.tab_id = self.TAB_IDS.get(course_info.get('type', 'public'), 'aPublicCourse')
        self.page_number = course_info.get('page', 1)
        self.search_keyword = course_info.get('search_keyword', '')  # 搜索关键字
    
    def stop(self):
        self._running = False
        self.status.emit("[监控] 收到停止信号")
    
    def run(self):
        try:
            course_name = self.course_info.get('KCM', '')
            tc_id = self.course_info.get('JXBID', '')
            course_number = self.course_info.get('number', '')
            course_type = self.course_info.get('type', 'public')
            
            if not tc_id:
                self.failed.emit(f"{course_name} 没有tcId")
                return
            
            if not self.driver:
                self.failed.emit(f"{course_name} 浏览器未初始化")
                return
            
            locate_info = f"搜索'{self.search_keyword}'" if self.search_keyword else f"页{self.page_number}"
            self.status.emit(f"[监控] 开始: {course_number} {course_name} ({locate_info})")
            
            # 首次进入，第一时间切换到对应板块和定位
            self._navigate_to_course(course_type)
            
            if not self._running:
                return
            
            # 到达后立即开始抢课，不等待
            
            while self._running:
                try:
                    # 检查是否停止
                    if not self._running:
                        self.status.emit(f"[监控] 已停止: {course_name}")
                        return
                    
                    # 检查driver和页面是否正常（登录页会等待登录完成）
                    if not self._check_page_valid():
                        # 只有浏览器关闭才退出，其他情况继续循环
                        if not self.driver:
                            return
                        time.sleep(1)
                        continue
                    
                    # 尝试抢课
                    if course_type == 'public':
                        self._grab_public_course_flow(tc_id, course_name, course_type)
                    else:
                        self._grab_other_course_flow(tc_id, course_number, course_name, course_type)
                    
                    if not self._running:
                        return
                    
                    time.sleep(0.5)  # 快速循环
                    
                except Exception as e:
                    error_msg = str(e)
                    # 检测浏览器是否被关闭
                    if 'no such window' in error_msg or 'target window already closed' in error_msg or 'web view not found' in error_msg or 'invalid session id' in error_msg:
                        self.status.emit("[监控] 浏览器已关闭，停止监控")
                        self.driver = None
                        return
                    self.status.emit(f"[监控] 错误: {error_msg[:80]}")
                    time.sleep(2)
                    
        except Exception as e:
            error_msg = str(e)
            if 'no such window' in error_msg or 'target window already closed' in error_msg or 'invalid session id' in error_msg:
                self.status.emit("[监控] 浏览器已关闭")
            else:
                self.failed.emit(f"监控线程异常: {error_msg[:80]}")
    
    def _navigate_to_course(self, course_type):
        """导航到课程所在位置 - 支持页码和搜索两种方式"""
        try:
            # 1. 切换到对应板块
            self.driver.execute_script(f"""
                var tab = document.getElementById('{self.tab_id}');
                if (tab) tab.click();
            """)
            time.sleep(0.3)
            
            # 2. 如果有搜索关键字，用搜索定位
            if self.search_keyword:
                self.status.emit(f"[监控] 搜索定位: {self.search_keyword}")
                
                search_id_map = {
                    'public': 'publicSearch',
                    'recommend': 'recommendSearch',
                    'major': 'programSearch',
                    'sport': 'sportSearch',
                }
                search_id = search_id_map.get(course_type, 'recommendSearch')
                
                self.driver.execute_script("""
                    var searchId = arguments[0];
                    var keyword = arguments[1];
                    var input = document.getElementById(searchId);
                    if (input) {
                        input.value = keyword;
                        input.dispatchEvent(new Event('input', {bubbles: true}));
                        input.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', keyCode: 13, bubbles: true}));
                    }
                """, search_id, self.search_keyword)
                time.sleep(0.8)
                return
            
            # 3. 否则用页码定位
            if self.page_number > 1:
                page_id_map = {
                    'public': 'publicPageNumber',
                    'recommend': 'recommendPageNumber',
                    'major': 'programPageNumber',
                    'sport': 'sportPageNumber',
                }
                up_btn_map = {
                    'public': 'publicUp',
                    'recommend': 'recommendUp',
                    'major': 'programUp',
                    'sport': 'sportUp',
                }
                down_btn_map = {
                    'public': 'publicDown',
                    'recommend': 'recommendDown',
                    'major': 'programDown',
                    'sport': 'sportDown',
                }
                page_id = page_id_map.get(course_type, 'recommendPageNumber')
                up_btn_id = up_btn_map.get(course_type, 'recommendUp')
                down_btn_id = down_btn_map.get(course_type, 'recommendDown')
                
                # 获取当前页
                current_page = self.driver.execute_script(f"""
                    var el = document.getElementById('{page_id}');
                    return el ? parseInt(el.textContent) || 1 : 1;
                """)
                
                self.status.emit(f"[监控] 当前第{current_page}页，跳转到第{self.page_number}页")
                
                # 根据当前页和目标页决定方向
                for _ in range(20):
                    current_page = self.driver.execute_script(f"""
                        var el = document.getElementById('{page_id}');
                        return el ? parseInt(el.textContent) || 1 : 1;
                    """)
                    
                    if current_page == self.page_number:
                        self.status.emit(f"[监控] 已到达第{current_page}页")
                        break
                    elif current_page < self.page_number:
                        # 需要往后翻
                        self.driver.execute_script(f"""
                            var btn = document.getElementById('{down_btn_id}');
                            if (btn) btn.click();
                        """)
                    else:
                        # 需要往前翻
                        self.driver.execute_script(f"""
                            var btn = document.getElementById('{up_btn_id}');
                            if (btn) btn.click();
                        """)
                    time.sleep(0.1)
                
                time.sleep(0.2)
            
        except Exception as e:
            self.status.emit(f"[监控] 导航失败: {e}")
    
    def _verify_page_ready(self, course_type):
        """验证页数正确且页面有数据"""
        page_id_map = {
            'public': 'publicPageNumber',
            'recommend': 'recommendPageNumber',
            'major': 'programPageNumber',
            'sport': 'sportPageNumber',
        }
        page_id = page_id_map.get(course_type, 'recommendPageNumber')
        
        # 检查当前页数
        current_page = self.driver.execute_script(f"""
            var el = document.getElementById('{page_id}');
            return el ? parseInt(el.textContent) || 1 : 1;
        """)
        
        # 检查页面是否有数据
        has_data = self.driver.execute_script("""
            var rows = document.querySelectorAll('.cv-row');
            for (var r of rows) {
                var t = r.querySelector('.cv-title-col') || r.querySelector('.cv-course');
                if (t && t.textContent.trim() && t.textContent.trim() !== '课程名称') return true;
            }
            return false;
        """)
        
        self.status.emit(f"[监控] 页数验证: 当前第{current_page}页, 目标第{self.page_number}页, 有数据: {has_data}")
    
    def _refresh_and_navigate(self, course_type):
        """刷新页面并导航回课程位置"""
        self.driver.refresh()
        time.sleep(2)
        self._navigate_to_course(course_type)
        time.sleep(0.5)
    
    def _check_page_valid(self):
        """检查页面是否有效"""
        if not self.driver:
            self.status.emit("[监控] 浏览器已关闭")
            return False
        
        try:
            # 检测是否在登录页面（通过登录表单元素判断）
            is_login_page = self.driver.execute_script("""
                return document.getElementById('loginName') !== null 
                    || document.getElementById('loginPwd') !== null
                    || document.getElementById('studentLoginBtn') !== null;
            """)
            
            if is_login_page:
                # 检测到登录页，等待主窗口定时器处理登录
                self.status.emit("[监控] 检测到登录页面，等待自动登录...")
                # 等待登录完成（最多等30秒）
                for _ in range(30):
                    time.sleep(1)
                    if not self._running:
                        return False
                    # 检查是否已离开登录页
                    still_login = self.driver.execute_script("""
                        return document.getElementById('loginName') !== null 
                            && document.getElementById('studentLoginBtn') !== null
                            && document.getElementById('studentLoginBtn').offsetWidth > 0;
                    """)
                    if not still_login:
                        self.status.emit("[监控] 登录完成，继续监控...")
                        time.sleep(2)  # 等待页面加载
                        return True
                # 超时，返回True继续尝试
                self.status.emit("[监控] 等待登录超时，继续尝试...")
                return True
        except Exception as e:
            self.status.emit(f"[监控] 检测页面状态异常: {e}")
            return True  # 异常时继续尝试，不退出
        
        return True
    
    def _close_all_dialogs(self):
        """关闭所有弹窗，确保页面干净"""
        for _ in range(5):
            # 检查是否有弹窗
            has_dialog = self.driver.execute_script("""
                // 检查失败弹窗
                var h2 = document.querySelector('.cv-body h2');
                if (h2 && (h2.textContent.indexOf('失败') >= 0 || h2.textContent.indexOf('确认') >= 0)) {
                    var btn = document.querySelector('.cv-sure.cvBtnFlag') || document.querySelector('.cv-sure');
                    if (btn) { btn.click(); return true; }
                }
                // 检查已选课程弹窗
                var closeBtn = document.querySelector('.jqx-window-close-button');
                if (closeBtn && closeBtn.offsetParent !== null) {
                    closeBtn.click();
                    return true;
                }
                return false;
            """)
            if not has_dialog:
                break
            time.sleep(0.5)
    
    def _detect_and_close_fail_dialog(self):
        """检测并关闭失败弹窗，返回是否检测到失败弹窗"""
        # 检测失败弹窗，5次，每秒1次，共5秒
        for wait in range(5):
            # 检测失败弹窗 - 多种方式检测
            fail_info = self.driver.execute_script("""
                // 方式1: 检查h2标签
                var h2s = document.querySelectorAll('h2');
                for (var h2 of h2s) {
                    if (h2.textContent.indexOf('失败') >= 0) {
                        return {hasFail: true, text: h2.textContent, method: 'h2'};
                    }
                }
                // 方式2: 检查cv-body内的h2
                var body = document.querySelector('.cv-body');
                if (body) {
                    var h2 = body.querySelector('h2');
                    if (h2 && h2.textContent.indexOf('失败') >= 0) {
                        return {hasFail: true, text: h2.textContent, method: 'cv-body'};
                    }
                }
                // 方式3: 检查弹窗图片（失败弹窗有特定图片）
                var img = document.querySelector('.cv-body img[src*="dialog-icon"]');
                if (img) {
                    var parent = img.closest('.cv-body');
                    if (parent) {
                        var h2 = parent.querySelector('h2');
                        if (h2 && h2.textContent.indexOf('失败') >= 0) {
                            return {hasFail: true, text: h2.textContent, method: 'img'};
                        }
                    }
                }
                return {hasFail: false, text: '', method: 'none'};
            """)
            
            self.status.emit(f"[DEBUG] 失败弹窗检测(第{wait+1}次): {fail_info}")
            
            if fail_info and fail_info.get('hasFail'):
                # 检测到失败弹窗，点击确认关闭
                self.status.emit(f"[监控] 检测到失败弹窗: {fail_info.get('text')}")
                self.driver.execute_script("""
                    // 点击失败弹窗的确认按钮
                    var btn = document.querySelector('.cv-foot .cv-sure.cvBtnFlag');
                    if (!btn) btn = document.querySelector('.cv-sure.cvBtnFlag');
                    if (!btn) btn = document.querySelector('.cv-foot .cv-sure');
                    if (btn) btn.click();
                """)
                time.sleep(0.5)
                
                # 等待弹窗完全关闭
                for close_wait in range(10):
                    dialog_closed = self.driver.execute_script("""
                        var h2s = document.querySelectorAll('h2');
                        for (var h2 of h2s) {
                            if (h2.textContent.indexOf('失败') >= 0) return false;
                        }
                        return true;
                    """)
                    if dialog_closed:
                        self.status.emit(f"[监控] 失败弹窗已关闭")
                        break
                    time.sleep(0.2)
                
                return True  # 检测到失败弹窗
            
            time.sleep(1)  # 每秒检测一次
        
        return False  # 未检测到失败弹窗
    
    def _grab_public_course_flow(self, tc_id, course_name, course_type):
        """通识教育选修课完整抢课流程"""
        # 0. 先检查并关闭所有弹窗
        self._close_all_dialogs()
        
        # 1. 先验证当前页数是否正确（如果不是搜索定位的话）
        if not self.search_keyword:
            page_id_map = {
                'public': 'publicPageNumber',
                'recommend': 'recommendPageNumber',
                'major': 'programPageNumber',
                'sport': 'sportPageNumber',
            }
            page_id = page_id_map.get(course_type, 'publicPageNumber')
            current_page = self.driver.execute_script(f"""
                var el = document.getElementById('{page_id}');
                return el ? parseInt(el.textContent) || 1 : 1;
            """)
            
            if current_page != self.page_number:
                self.status.emit(f"[监控] 页数不对(当前{current_page}页,目标{self.page_number}页)，重新导航")
                self._navigate_to_course(course_type)
                return
        
        # 2. 查找课程按钮，用tcid精确匹配
        course_info = self.driver.execute_script("""
            var tcId = arguments[0];
            var btn = document.querySelector('a.cv-choice[tcid="' + tcId + '"]');
            if (!btn) {
                return {found: false, reason: '未找到课程按钮'};
            }
            var isFull = btn.getAttribute('isfull') === '1';
            var isConflict = btn.getAttribute('isconflict') === '1';
            var isDisabled = btn.classList.contains('cv-disabled');
            // 获取容量信息
            var row = btn.closest('.cv-row');
            var capText = '';
            if (row) {
                var capCol = row.querySelector('.cv-capcity-col');
                var volCol = row.querySelector('.cv-firstVolunteer-col');
                if (capCol) capText = capCol.textContent.trim();
            }
            return {
                found: true,
                isFull: isFull,
                isConflict: isConflict,
                isDisabled: isDisabled,
                canGrab: !isFull && !isConflict && !isDisabled,
                capacity: capText
            };
        """, tc_id)
        
        self.status.emit(f"[DEBUG] 课程状态: {course_info}")
        
        if not course_info or not course_info.get('found'):
            # 课程不在当前页面，记录未找到次数
            if not hasattr(self, '_not_found_count'):
                self._not_found_count = 0
                self._not_found_start = time.time()
            
            self._not_found_count += 1
            elapsed = time.time() - self._not_found_start
            
            # 5秒内未找到课程，刷新页面
            if elapsed >= 5:
                self.status.emit(f"[监控] 5秒内未找到课程(tcid={tc_id})，刷新页面")
                self._not_found_count = 0
                self._not_found_start = time.time()
                self._refresh_and_navigate(course_type)
                return
            
            self.status.emit(f"[监控] 未找到课程(tcid={tc_id})，重新导航 ({int(elapsed)}秒)")
            self._navigate_to_course(course_type)
            return
        
        # 找到课程，重置计数
        self._not_found_count = 0
        self._not_found_start = time.time()
        
        if not course_info.get('canGrab'):
            # 不可选，刷新页面等待5秒后重试
            reason = '已满' if course_info.get('isFull') else ('冲突' if course_info.get('isConflict') else '不可选')
            self.status.emit(f"[监控] 课程{reason}，刷新等待: {course_name}")
            self._refresh_and_navigate(course_type)
            time.sleep(5)
            return  # 等待下次循环
        
        # 3. 点击"选择"按钮
        self.driver.execute_script("""
            var tcId = arguments[0];
            var btn = document.querySelector('a.cv-choice[tcid="' + tcId + '"]');
            if (btn) btn.click();
        """, tc_id)
        self.status.emit(f"[监控] 点击选择: {course_name}")
        time.sleep(0.5)
        
        # 4. 等待确认弹窗出现，点击确认按钮
        for _ in range(5):
            clicked = self.driver.execute_script("""
                var btn = document.querySelector('.cv-sure.cvBtnFlag[type="sure"]');
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    return true;
                }
                return false;
            """)
            if clicked:
                self.status.emit(f"[监控] 点击确认: {course_name}")
                break
            time.sleep(0.1)
        
        # 4. 立即检测失败弹窗（点击确认后弹窗可能变成失败弹窗）
        time.sleep(0.3)
        
        # 检测并关闭失败弹窗
        if self._detect_and_close_fail_dialog():
            # 检测到失败弹窗，弹窗已关闭，刷新重试
            self.status.emit(f"[监控] 刷新重试: {course_name}")
            self._refresh_and_navigate(course_type)
            return
        
        self.status.emit(f"[DEBUG] 未检测到失败弹窗，去已选课程确认")
        
        # 5. 没有失败弹窗，才去检查已选课程
        time.sleep(0.3)
        if self._check_course_selected(tc_id):
            self.success.emit(f"选课成功: {course_name}")
            self._running = False  # 成功了，停止监控
        else:
            # 已选课程里没有，刷新页面，重试
            self.status.emit(f"[监控] 未在已选课程中找到，刷新重试: {course_name}")
            self._refresh_and_navigate(course_type)
    
    def _grab_other_course_flow(self, tc_id, course_number, course_name, course_type):
        """其他课程完整抢课流程"""
        # 0. 先检查并关闭所有弹窗
        self._close_all_dialogs()
        
        # 1. 先验证当前页数是否正确（如果不是搜索定位的话）
        if not self.search_keyword:
            page_id_map = {
                'public': 'publicPageNumber',
                'recommend': 'recommendPageNumber',
                'major': 'programPageNumber',
                'sport': 'sportPageNumber',
            }
            page_id = page_id_map.get(course_type, 'recommendPageNumber')
            current_page = self.driver.execute_script(f"""
                var el = document.getElementById('{page_id}');
                return el ? parseInt(el.textContent) || 1 : 1;
            """)
            
            if current_page != self.page_number:
                self.status.emit(f"[监控] 页数不对(当前{current_page}页,目标{self.page_number}页)，重新导航")
                self._navigate_to_course(course_type)
                return
        
        # 2. 先点击课程行（用课程编号精确匹配）
        row_found = self.driver.execute_script("""
            var courseNum = arguments[0];
            var row = document.querySelector('.cv-row[coursenumber="' + courseNum + '"]');
            if (!row) {
                var nums = document.querySelectorAll('.cv-num');
                for (var n of nums) {
                    if (n.textContent.indexOf(courseNum) >= 0) {
                        row = n.closest('.cv-row');
                        break;
                    }
                }
            }
            if (row) {
                row.click();
                return true;
            }
            return false;
        """, course_number)
        
        if not row_found:
            # 课程行未找到，记录未找到次数
            if not hasattr(self, '_not_found_count'):
                self._not_found_count = 0
                self._not_found_start = time.time()
            
            self._not_found_count += 1
            elapsed = time.time() - self._not_found_start
            
            # 5秒内未找到课程，刷新页面
            if elapsed >= 5:
                self.status.emit(f"[监控] 5秒内未找到课程行(编号={course_number})，刷新页面")
                self._not_found_count = 0
                self._not_found_start = time.time()
                self._refresh_and_navigate(course_type)
                return
            
            self.status.emit(f"[监控] 未找到课程行(编号={course_number})，重新导航 ({int(elapsed)}秒)")
            self._navigate_to_course(course_type)
            return
        
        # 找到课程行，重置计数
        self._not_found_count = 0
        self._not_found_start = time.time()
        
        time.sleep(0.3)
        
        # 3. 检查卡片状态，是否可以选择（用tcid精确匹配）
        card_info = self.driver.execute_script("""
            var tcId = arguments[0];
            var result = {found: false, canGrab: false, reason: ''};
            
            var card = document.getElementById(tcId + '_courseDiv');
            if (!card) {
                var cards = document.querySelectorAll('.cv-course-card');
                for (var c of cards) {
                    if (c.id && c.id.indexOf(tcId) >= 0) { card = c; break; }
                }
            }
            
            if (card) {
                result.found = true;
                var isFull = card.getAttribute('isfull') === '1';
                var isConflict = card.getAttribute('isconflict') === '1';
                var isChosen = card.getAttribute('ischoose') === '1';
                var conflictTag = card.querySelector('.cv-tag.cv-danger:not(.cv-block-hide)');
                var hasConflict = conflictTag && conflictTag.textContent.indexOf('冲突') >= 0;
                var fullTag = card.querySelector('.cv-isfull:not(.cv-block-hide)');
                var hasFull = fullTag && fullTag.textContent.indexOf('已满') >= 0;
                
                result.isFull = isFull || hasFull;
                result.isConflict = isConflict || hasConflict;
                result.isChosen = isChosen;
                result.canGrab = !isFull && !isConflict && !isChosen && !hasConflict && !hasFull;
                
                // 获取容量信息
                var capEl = card.querySelector('.cv-caption-text:not(.cv-operation)');
                result.capacity = capEl ? capEl.textContent.trim() : '';
            }
            return result;
        """, tc_id)
        
        self.status.emit(f"[DEBUG] 课程卡片状态: {card_info}")
        
        if not card_info or not card_info.get('found'):
            # 课程卡片未找到，记录未找到次数（复用之前的计数器）
            if not hasattr(self, '_not_found_count'):
                self._not_found_count = 0
                self._not_found_start = time.time()
            
            self._not_found_count += 1
            elapsed = time.time() - self._not_found_start
            
            # 5秒内未找到课程卡片，刷新页面
            if elapsed >= 5:
                self.status.emit(f"[监控] 5秒内未找到课程卡片(tcid={tc_id})，刷新页面")
                self._not_found_count = 0
                self._not_found_start = time.time()
                self._refresh_and_navigate(course_type)
                return
            
            self.status.emit(f"[监控] 未找到课程卡片(tcid={tc_id})，重新导航 ({int(elapsed)}秒)")
            self._navigate_to_course(course_type)
            return
        
        # 找到课程卡片，重置计数
        self._not_found_count = 0
        self._not_found_start = time.time()
        
        if not card_info.get('canGrab'):
            # 不可选，刷新页面等待5秒后重试
            reason = '已满' if card_info.get('isFull') else ('冲突' if card_info.get('isConflict') else ('已选' if card_info.get('isChosen') else '不可选'))
            self.status.emit(f"[监控] 课程{reason}({card_info.get('capacity', '')})，刷新等待: {course_name}")
            self._refresh_and_navigate(course_type)
            time.sleep(5)
            return  # 等待下次循环
        
        # 4. 先点击课程卡片空白处（触发显示选择按钮）
        self.driver.execute_script("""
            var tcId = arguments[0];
            var card = document.getElementById(tcId + '_courseDiv');
            if (!card) {
                var cards = document.querySelectorAll('.cv-course-card');
                for (var c of cards) {
                    if (c.id && c.id.indexOf(tcId) >= 0) { card = c; break; }
                }
            }
            if (card) card.click();
        """, tc_id)
        self.status.emit(f"[监控] 点击卡片: {course_name}")
        time.sleep(0.3)
        
        # 4. 点击选择按钮
        self.driver.execute_script("""
            var tcId = arguments[0];
            var btn = document.querySelector('button.cv-btn-chose[tcid="' + tcId + '"]');
            if (btn) btn.click();
        """, tc_id)
        self.status.emit(f"[监控] 点击选择: {course_name}")
        
        # 5. 立即检测失败弹窗（点击选择后弹窗可能马上出现）
        time.sleep(0.3)
        
        # 检测并关闭失败弹窗
        if self._detect_and_close_fail_dialog():
            # 检测到失败弹窗，弹窗已关闭，刷新重试
            self.status.emit(f"[监控] 刷新重试: {course_name}")
            self._refresh_and_navigate(course_type)
            return
        
        self.status.emit(f"[DEBUG] 未检测到失败弹窗，去已选课程确认")
        
        # 6. 没有失败弹窗，才去检查已选课程
        time.sleep(0.3)
        if self._check_course_selected(tc_id):
            self.success.emit(f"选课成功: {course_name}")
            self._running = False
        else:
            self.status.emit(f"[监控] 未在已选课程中找到，刷新重试: {course_name}")
            self._refresh_and_navigate(course_type)
    
    def _check_course_selected(self, tc_id):
        """检查课程是否已选"""
        try:
            # 点击"已选课程"图标打开弹窗
            opened = self.driver.execute_script("""
                // 尝试多种方式打开已选课程弹窗
                var tab = document.querySelector('.cv-choice-icon[type="grablessons"]');
                if (tab) { tab.click(); return 'icon'; }
                // 备选：直接点击已选课程文字
                var tabs = document.querySelectorAll('.cv-choice-icon');
                for (var t of tabs) {
                    if (t.textContent.indexOf('已选') >= 0) { t.click(); return 'text'; }
                }
                return 'none';
            """)
            self.status.emit(f"[DEBUG] 打开已选课程: {opened}")
            time.sleep(0.5)
            
            # 检查弹窗是否打开
            has_window = self.driver.execute_script("""
                return document.querySelector('.jqx-window-content') !== null;
            """)
            
            if not has_window:
                self.status.emit("[DEBUG] 已选课程弹窗未打开")
                return False
            
            # 检查是否有数据，没有就切换标签刷新
            has_data = self.driver.execute_script("""
                return document.querySelectorAll('.cv-row a.withdrew').length > 0;
            """)
            
            if not has_data:
                # 点击"退选日志"再点回"已选课程"刷新数据
                self.driver.execute_script("""
                    var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                    for (var t of tabs) {
                        if (t.textContent.indexOf('退选日志') >= 0) { t.click(); break; }
                    }
                """)
                time.sleep(0.3)
                self.driver.execute_script("""
                    var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                    for (var t of tabs) {
                        if (t.textContent.indexOf('已选课程') >= 0) { t.click(); break; }
                    }
                """)
                time.sleep(0.5)
            
            # 检查是否有该课程
            found = self.driver.execute_script("""
                var tcId = arguments[0];
                var rows = document.querySelectorAll('.cv-row');
                for (var r of rows) {
                    var link = r.querySelector('a.withdrew[teachingclassid]');
                    if (link && link.getAttribute('teachingclassid') === tcId) return true;
                }
                return false;
            """, tc_id)
            
            self.status.emit(f"[DEBUG] 已选课程检查: tcid={tc_id}, found={found}")
            
            # 关闭已选课程弹窗
            self.driver.execute_script("""
                var closeBtn = document.querySelector('.jqx-window-close-button');
                if (closeBtn) closeBtn.click();
            """)
            time.sleep(0.3)
            
            return found
        except Exception as e:
            self.status.emit(f"[DEBUG] 检查已选课程异常: {e}")
            return False


class MultiGrabWorker(QThread):
    """多课程监控线程 - 单线程轮询所有待抢课程"""
    success = pyqtSignal(str, dict)  # 成功信号，带课程数据
    failed = pyqtSignal(str)
    status = pyqtSignal(str)
    need_relogin = pyqtSignal()
    course_available = pyqtSignal(str, str, int, int)  # 余课提醒: 课程名, 教师, 余量, 容量
    
    # 板块Tab ID映射
    TAB_IDS = {
        'public': 'aPublicCourse',
        'recommend': 'aRecommendCourse',
        'major': 'aProgramCourse',
        'sport': 'aSportCourse',
    }
    
    def __init__(self, driver, courses, student_code, batch_code, selected_round="2"):
        super().__init__()
        self.driver = driver
        self.courses = courses  # 课程列表
        self.student_code = student_code
        self.batch_code = batch_code
        self.selected_round = selected_round  # "1"=第一轮, "2"=第二轮
        self._running = True
        self._current_course_idx = 0
        self._not_found_times = {}  # 记录每个课程未找到的开始时间
        self._notified_courses = set()  # 已发送余课提醒的课程ID
    
    def stop(self):
        self._running = False
        self.status.emit("[监控] 收到停止信号")
    
    def add_course(self, course):
        """动态添加课程"""
        tc_id = course.get('JXBID', '')
        # 检查是否已存在
        for c in self.courses:
            if c.get('JXBID') == tc_id:
                return False
        self.courses.append(course)
        self.status.emit(f"[监控] 已添加: {course.get('KCM', '')}")
        return True
    
    def remove_course(self, tc_id):
        """移除课程"""
        for i, c in enumerate(self.courses):
            if c.get('JXBID') == tc_id:
                name = c.get('KCM', '')
                self.courses.pop(i)
                self.status.emit(f"[监控] 已移除: {name}")
                return True
        return False
    
    def run(self):
        self.status.emit(f"[监控] 启动多课程监控，共 {len(self.courses)} 门课程")
        
        while self._running and self.courses:
            try:
                # 检查浏览器是否有效
                if not self._check_page_valid():
                    if not self.driver:
                        self.status.emit("[监控] 浏览器已关闭，准备重新登录...")
                        self.need_relogin.emit()  # 发出重新登录信号
                        return
                    time.sleep(1)
                    continue
                
                # 轮询每个课程
                for course in list(self.courses):  # 用list复制，避免遍历时修改
                    if not self._running:
                        return
                    
                    tc_id = course.get('JXBID', '')
                    course_name = course.get('KCM', '')
                    course_type = course.get('type', 'public')
                    course_number = course.get('number', '')
                    
                    # 导航到课程位置
                    self._navigate_to_course(course)
                    
                    if not self._running:
                        return
                    
                    # 尝试抢课
                    result = self._try_grab_course(course)
                    
                    if result == 'success':
                        # 抢课成功，从列表移除
                        self.courses.remove(course)
                        self.success.emit(f"选课成功: {course_name}", course)
                        self.status.emit(f"[监控] 抢课成功: {course_name}，剩余 {len(self.courses)} 门")
                    elif result == 'not_found':
                        # 课程未找到，检查超时
                        if tc_id not in self._not_found_times:
                            self._not_found_times[tc_id] = time.time()
                        elif time.time() - self._not_found_times[tc_id] >= 5:
                            # 5秒未找到，刷新页面
                            self.status.emit(f"[监控] {course_name} 5秒未找到，刷新页面")
                            self._not_found_times[tc_id] = time.time()
                            self.driver.refresh()
                            time.sleep(2)
                    else:
                        # 找到但不可抢，重置计时
                        self._not_found_times.pop(tc_id, None)
                    
                    time.sleep(0.3)  # 课程间短暂间隔
                
                time.sleep(0.5)  # 一轮结束后短暂休息
                
            except Exception as e:
                error_msg = str(e)
                if 'no such window' in error_msg or 'target window already closed' in error_msg or 'web view not found' in error_msg or 'invalid session id' in error_msg:
                    self.status.emit("[监控] 浏览器已关闭，准备重新登录...")
                    self.driver = None
                    self.need_relogin.emit()  # 发出重新登录信号
                    return
                self.status.emit(f"[监控] 错误: {error_msg[:80]}")
                time.sleep(2)
        
        self.status.emit("[监控] 所有课程监控完成或已停止")
    
    def _check_page_valid(self):
        """检查页面是否有效"""
        if not self.driver:
            return False
        
        try:
            is_login_page = self.driver.execute_script("""
                return document.getElementById('loginName') !== null 
                    && document.getElementById('studentLoginBtn') !== null;
            """)
            
            if is_login_page:
                self.status.emit("[监控] 检测到登录页面，等待自动登录...")
                for _ in range(30):
                    time.sleep(1)
                    if not self._running:
                        return False
                    try:
                        still_login = self.driver.execute_script("""
                            return document.getElementById('loginName') !== null 
                                && document.getElementById('studentLoginBtn') !== null
                                && document.getElementById('studentLoginBtn').offsetWidth > 0;
                        """)
                        if not still_login:
                            self.status.emit("[监控] 登录完成，继续监控...")
                            time.sleep(2)
                            return True
                    except Exception as e:
                        error_msg = str(e)
                        if 'no such window' in error_msg or 'target window already closed' in error_msg or 'web view not found' in error_msg or 'invalid session id' in error_msg:
                            self.driver = None
                            return False
                return True
        except Exception as e:
            error_msg = str(e)
            if 'no such window' in error_msg or 'target window already closed' in error_msg or 'web view not found' in error_msg or 'invalid session id' in error_msg:
                self.driver = None
                return False
            return True
        return True
    
    def _navigate_to_course(self, course):
        """导航到课程位置"""
        course_type = course.get('type', 'public')
        tab_id = self.TAB_IDS.get(course_type, 'aPublicCourse')
        page_number = course.get('page', 1)
        search_keyword = course.get('search_keyword', '')
        
        try:
            # 切换板块
            self.driver.execute_script(f"""
                var tab = document.getElementById('{tab_id}');
                if (tab) tab.click();
            """)
            time.sleep(0.2)
            
            # 搜索定位
            if search_keyword:
                search_id_map = {
                    'public': 'publicSearch',
                    'recommend': 'recommendSearch',
                    'major': 'programSearch',
                    'sport': 'sportSearch',
                }
                search_id = search_id_map.get(course_type, 'recommendSearch')
                self.driver.execute_script("""
                    var input = document.getElementById(arguments[0]);
                    if (input) {
                        input.value = arguments[1];
                        input.dispatchEvent(new Event('input', {bubbles: true}));
                        input.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', keyCode: 13, bubbles: true}));
                    }
                """, search_id, search_keyword)
                time.sleep(0.5)
                return
            
            # 页码定位
            if page_number > 1:
                page_id_map = {
                    'public': 'publicPageNumber',
                    'recommend': 'recommendPageNumber',
                    'major': 'programPageNumber',
                    'sport': 'sportPageNumber',
                }
                up_btn_map = {
                    'public': 'publicUp',
                    'recommend': 'recommendUp',
                    'major': 'programUp',
                    'sport': 'sportUp',
                }
                down_btn_map = {
                    'public': 'publicDown',
                    'recommend': 'recommendDown',
                    'major': 'programDown',
                    'sport': 'sportDown',
                }
                page_id = page_id_map.get(course_type, 'recommendPageNumber')
                up_btn_id = up_btn_map.get(course_type, 'recommendUp')
                down_btn_id = down_btn_map.get(course_type, 'recommendDown')
                
                for _ in range(20):
                    current_page = self.driver.execute_script(f"""
                        var el = document.getElementById('{page_id}');
                        return el ? parseInt(el.textContent) || 1 : 1;
                    """)
                    
                    if current_page == page_number:
                        break
                    elif current_page < page_number:
                        self.driver.execute_script(f"document.getElementById('{down_btn_id}').click();")
                    else:
                        self.driver.execute_script(f"document.getElementById('{up_btn_id}').click();")
                    time.sleep(0.1)
                
                time.sleep(0.2)
        except Exception as e:
            self.status.emit(f"[监控] 导航失败: {e}")
    
    def _try_grab_course(self, course):
        """尝试抢课，返回 'success', 'not_found', 'unavailable', 'failed'"""
        course_type = course.get('type', 'public')
        tc_id = course.get('JXBID', '')
        course_name = course.get('KCM', '')
        course_number = course.get('number', '')
        
        try:
            if course_type == 'public':
                return self._try_grab_public(tc_id, course_name)
            else:
                return self._try_grab_other(tc_id, course_number, course_name)
        except Exception as e:
            self.status.emit(f"[监控] 抢课异常: {e}")
            return 'failed'
    
    def _try_grab_public(self, tc_id, course_name):
        """尝试抢通识教育选修课"""
        # 查找课程，获取容量和第一志愿人数
        course_info = self.driver.execute_script("""
            var tcId = arguments[0];
            var btn = document.querySelector('a.cv-choice[tcid="' + tcId + '"]');
            if (!btn) return {found: false};
            
            var isFull = btn.getAttribute('isfull') === '1';
            var isConflict = btn.getAttribute('isconflict') === '1';
            var isDisabled = btn.classList.contains('cv-disabled');
            
            // 获取容量和第一志愿人数
            var row = btn.closest('.cv-row');
            var capacity = 0, volunteer = 0;
            if (row) {
                var capCol = row.querySelector('.cv-capcity-col');
                var volCol = row.querySelector('.cv-firstVolunteer-col');
                // 支持 "35人" 和 "35" 两种格式
                if (capCol) capacity = parseInt(capCol.textContent.replace(/[^0-9]/g, '')) || 0;
                if (volCol) volunteer = parseInt(volCol.textContent.replace(/[^0-9]/g, '')) || 0;
            }
            
            return {
                found: true,
                isFull: isFull,
                isConflict: isConflict,
                isDisabled: isDisabled,
                capacity: capacity,
                volunteer: volunteer
            };
        """, tc_id)
        
        if not course_info or not course_info.get('found'):
            return 'not_found'
        
        # 根据轮次判断是否可抢
        is_conflict = course_info.get('isConflict', False)
        is_disabled = course_info.get('isDisabled', False)
        is_full = course_info.get('isFull', False)
        capacity = course_info.get('capacity', 0)
        volunteer = course_info.get('volunteer', 0)
        
        if is_conflict or is_disabled:
            return 'unavailable'
        
        if self.selected_round == "1":
            # 第一轮：第一志愿人数 < 课容量 才能选
            can_grab = volunteer < capacity
            self.status.emit(f"[监控] 第一轮检查: {course_name} 容量={capacity} 志愿={volunteer} 可选={can_grab}")
            if not can_grab:
                return 'unavailable'
            # 发出余课提醒（只提醒一次）
            if tc_id not in self._notified_courses:
                remain = capacity - volunteer
                self.course_available.emit(course_name, "", remain, capacity)
                self._notified_courses.add(tc_id)
        else:
            # 第二轮：看是否已满
            if is_full:
                return 'unavailable'
            # 发出余课提醒（只提醒一次）
            if tc_id not in self._notified_courses:
                remain = capacity - volunteer if capacity > 0 else 1
                self.course_available.emit(course_name, "", remain, capacity)
                self._notified_courses.add(tc_id)
        
        # 点击选择
        self.driver.execute_script("""
            var btn = document.querySelector('a.cv-choice[tcid="' + arguments[0] + '"]');
            if (btn) btn.click();
        """, tc_id)
        self.status.emit(f"[监控] 点击选择: {course_name}")
        time.sleep(0.3)
        
        # 根据轮次点击不同的确认按钮
        if self.selected_round == "1":
            # 第一轮：点击弹窗中的"选择"按钮 <button class="cv-btn cvBtnFlag" type="sure">选择</button>
            for _ in range(5):
                clicked = self.driver.execute_script("""
                    var btn = document.querySelector('button.cv-btn.cvBtnFlag[type="sure"]');
                    if (btn && btn.offsetParent !== null && btn.textContent.indexOf('选择') >= 0) { 
                        btn.click(); return true; 
                    }
                    return false;
                """)
                if clicked:
                    self.status.emit(f"[监控] 点击选择确认: {course_name}")
                    break
                time.sleep(0.1)
        else:
            # 第二轮：点击确认按钮 <button class="cv-sure cvBtnFlag" type="sure">
            for _ in range(5):
                clicked = self.driver.execute_script("""
                    var btn = document.querySelector('.cv-sure.cvBtnFlag[type="sure"]');
                    if (btn && btn.offsetParent !== null) { btn.click(); return true; }
                    return false;
                """)
                if clicked:
                    self.status.emit(f"[监控] 点击确认: {course_name}")
                    break
                time.sleep(0.1)
        
        time.sleep(0.3)
        
        # 检测失败弹窗
        if self._detect_and_close_fail_dialog():
            return 'failed'
        
        # 检查是否成功 - 通识教育选修课程在"公选课（已选）"板块
        if self._check_course_selected(tc_id, 'public'):
            return 'success'
        
        return 'failed'
    
    def _try_grab_other(self, tc_id, course_number, course_name):
        """尝试抢其他课程"""
        # 点击课程行
        row_found = self.driver.execute_script("""
            var courseNum = arguments[0];
            var row = document.querySelector('.cv-row[coursenumber="' + courseNum + '"]');
            if (!row) {
                var nums = document.querySelectorAll('.cv-num');
                for (var n of nums) {
                    if (n.textContent.indexOf(courseNum) >= 0) {
                        row = n.closest('.cv-row');
                        break;
                    }
                }
            }
            if (row) { row.click(); return true; }
            return false;
        """, course_number)
        
        if not row_found:
            return 'not_found'
        
        time.sleep(0.2)
        
        # 检查卡片状态，获取容量和第一志愿人数
        card_info = self.driver.execute_script("""
            var tcId = arguments[0];
            var card = document.getElementById(tcId + '_courseDiv');
            if (!card) {
                var cards = document.querySelectorAll('.cv-course-card');
                for (var c of cards) {
                    if (c.id && c.id.indexOf(tcId) >= 0) { card = c; break; }
                }
            }
            if (!card) return {found: false};
            
            var isFull = card.getAttribute('isfull') === '1';
            var isConflict = card.getAttribute('isconflict') === '1';
            var isChosen = card.getAttribute('ischoose') === '1';
            
            // 检查冲突标签
            var conflictTag = card.querySelector('.cv-tag.cv-danger:not(.cv-block-hide)');
            var hasConflict = conflictTag && conflictTag.textContent.indexOf('冲突') >= 0;
            
            // 检查已满标签（第二轮）
            var fullTag = card.querySelector('.cv-isfull:not(.cv-block-hide)');
            var hasFull = fullTag && fullTag.textContent.indexOf('已满') >= 0;
            
            // 检查志愿标签 - cv-one(红/第一志愿满), cv-two(绿/第二志愿), cv-three(第三志愿)
            var volunteerType = '';
            var volTag = card.querySelector('.cv-tag.cv-one, .cv-tag.cv-two, .cv-tag.cv-three');
            if (volTag) {
                if (volTag.classList.contains('cv-one')) volunteerType = '第一志愿';
                else if (volTag.classList.contains('cv-two')) volunteerType = '第二志愿';
                else if (volTag.classList.contains('cv-three')) volunteerType = '第三志愿';
            }
            // cv-one 表示第一志愿人数已满
            var isFirstVolFull = volTag && volTag.classList.contains('cv-one');
            
            // 获取容量和第一志愿人数 - 支持两种格式
            var capacity = 0, volunteer = 0;
            var capTexts = card.querySelectorAll('.cv-caption-text:not(.cv-operation)');
            for (var ct of capTexts) {
                var text = ct.textContent;
                // 第一轮格式: "课容量：40人" 和 "已报第一志愿：92人，已选中人数：0"
                var capMatch = text.match(/课容量[：:](\\d+)/);
                if (capMatch) capacity = parseInt(capMatch[1]) || 0;
                var volMatch = text.match(/第一志愿[：:](\\d+)/);
                if (volMatch) volunteer = parseInt(volMatch[1]) || 0;
                // 第二轮格式: "136/110"
                var slashMatch = text.match(/^(\\d+)\\/(\\d+)$/);
                if (slashMatch) {
                    volunteer = parseInt(slashMatch[1]) || 0;
                    capacity = parseInt(slashMatch[2]) || 0;
                }
            }
            
            return {
                found: true,
                isFull: isFull || hasFull,
                isConflict: isConflict || hasConflict,
                isChosen: isChosen,
                isFirstVolFull: isFirstVolFull,
                volunteerType: volunteerType,
                capacity: capacity,
                volunteer: volunteer
            };
        """, tc_id)
        
        if not card_info or not card_info.get('found'):
            return 'not_found'
        
        # 根据轮次判断是否可抢
        is_conflict = card_info.get('isConflict', False)
        is_chosen = card_info.get('isChosen', False)
        is_full = card_info.get('isFull', False)
        is_first_vol_full = card_info.get('isFirstVolFull', False)  # cv-one标签
        volunteer_type = card_info.get('volunteerType', '')  # 志愿类型
        capacity = card_info.get('capacity', 0)
        volunteer = card_info.get('volunteer', 0)
        
        if is_conflict or is_chosen:
            return 'unavailable'
        
        if self.selected_round == "1":
            # 第一轮：第一志愿人数 < 课容量 才能选
            # cv-one 标签表示第一志愿已满
            can_grab = (volunteer < capacity) and not is_first_vol_full
            vol_info = f"志愿={volunteer_type}" if volunteer_type else ""
            self.status.emit(f"[监控] 第一轮: {course_name} 容量={capacity} 报名={volunteer} {vol_info} 可选={can_grab}")
            if not can_grab:
                return 'unavailable'
            # 发出余课提醒（只提醒一次）
            if tc_id not in self._notified_courses:
                remain = capacity - volunteer
                self.course_available.emit(course_name, "", remain, capacity)
                self._notified_courses.add(tc_id)
        else:
            # 第二轮：看是否已满
            if is_full:
                return 'unavailable'
            # 发出余课提醒（只提醒一次）
            if tc_id not in self._notified_courses:
                remain = capacity - volunteer if capacity > 0 else 1
                self.course_available.emit(course_name, "", remain, capacity)
                self._notified_courses.add(tc_id)
        
        # 点击卡片
        self.driver.execute_script("""
            var tcId = arguments[0];
            var card = document.getElementById(tcId + '_courseDiv');
            if (!card) {
                var cards = document.querySelectorAll('.cv-course-card');
                for (var c of cards) {
                    if (c.id && c.id.indexOf(tcId) >= 0) { card = c; break; }
                }
            }
            if (card) card.click();
        """, tc_id)
        time.sleep(0.2)
        
        # 点击选择按钮
        self.driver.execute_script("""
            var btn = document.querySelector('button.cv-btn-chose[tcid="' + arguments[0] + '"]');
            if (btn) btn.click();
        """, tc_id)
        self.status.emit(f"[监控] 点击选择: {course_name}")
        time.sleep(0.5)
        
        # 第一轮：点击选择后直接去已选志愿检查
        # 第二轮：先检测失败弹窗
        if self.selected_round != "1":
            if self._detect_and_close_fail_dialog():
                return 'failed'
        
        # 检查是否成功 - 其他板块在"方案课程（已选）"板块
        if self._check_course_selected(tc_id, 'other'):
            return 'success'
        
        return 'failed'
    
    def _detect_and_close_fail_dialog(self):
        """检测并关闭失败弹窗"""
        for _ in range(3):
            fail_info = self.driver.execute_script("""
                var h2s = document.querySelectorAll('h2');
                for (var h2 of h2s) {
                    if (h2.textContent.indexOf('失败') >= 0) {
                        return {hasFail: true, text: h2.textContent};
                    }
                }
                return {hasFail: false};
            """)
            
            if fail_info and fail_info.get('hasFail'):
                self.status.emit(f"[监控] 检测到失败弹窗: {fail_info.get('text')}")
                self.driver.execute_script("""
                    var btn = document.querySelector('.cv-foot .cv-sure.cvBtnFlag');
                    if (!btn) btn = document.querySelector('.cv-sure.cvBtnFlag');
                    if (btn) btn.click();
                """)
                time.sleep(0.3)
                return True
            time.sleep(0.5)
        return False
    
    def _check_course_selected(self, tc_id, course_type='public'):
        """检查课程是否已选"""
        try:
            # 点击"已选课程"图标打开弹窗
            opened = self.driver.execute_script("""
                var tab = document.querySelector('.cv-choice-icon[type="grablessons"]');
                if (tab) { tab.click(); return 'icon'; }
                var tabs = document.querySelectorAll('.cv-choice-icon');
                for (var t of tabs) {
                    if (t.textContent.indexOf('已选') >= 0) { t.click(); return 'text'; }
                }
                return 'none';
            """)
            self.status.emit(f"[DEBUG] 打开已选课程: {opened}")
            time.sleep(0.5)
            
            # 检查弹窗是否打开
            has_window = self.driver.execute_script("""
                return document.querySelector('.jqx-window-content') !== null;
            """)
            
            if not has_window:
                self.status.emit("[DEBUG] 已选课程弹窗未打开")
                return False
            
            # 根据轮次和课程类型切换到对应板块
            if self.selected_round == "1":
                if course_type == 'public':
                    # 通识教育选修课程 - 切换到"公选课（已选）"
                    self.driver.execute_script("""
                        var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                        for (var t of tabs) {
                            if (t.textContent.indexOf('公选课') >= 0 && t.textContent.indexOf('已选') >= 0) { 
                                t.click(); break; 
                            }
                        }
                    """)
                else:
                    # 其他板块（推荐/主修/体育）- 切换到"方案课程（已选）"
                    self.driver.execute_script("""
                        var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                        for (var t of tabs) {
                            if (t.textContent.indexOf('方案课程') >= 0 && t.textContent.indexOf('已选') >= 0) { 
                                t.click(); break; 
                            }
                        }
                    """)
                time.sleep(0.5)
            else:
                # 第二轮 - 切换到"已选课程"
                self.driver.execute_script("""
                    var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                    for (var t of tabs) {
                        if (t.textContent.indexOf('已选课程') >= 0) { t.click(); break; }
                    }
                """)
                time.sleep(0.5)
            
            # 检查是否有数据，没有就切换到旁边选项再切回来
            has_data = self.driver.execute_script("""
                return document.querySelectorAll('.cv-row[teachingclassid]').length > 0 
                    || document.querySelectorAll('.cv-row a.withdrew').length > 0
                    || document.querySelectorAll('.cv-row a.delVolunteer').length > 0;
            """)
            
            if not has_data:
                # 切换到退选日志再切回来刷新数据
                self.driver.execute_script("""
                    var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                    for (var t of tabs) {
                        if (t.textContent.indexOf('退选日志') >= 0) { t.click(); break; }
                    }
                """)
                time.sleep(0.3)
                # 切回对应板块
                if self.selected_round == "1":
                    if course_type == 'public':
                        self.driver.execute_script("""
                            var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                            for (var t of tabs) {
                                if (t.textContent.indexOf('公选课') >= 0 && t.textContent.indexOf('已选') >= 0) { 
                                    t.click(); break; 
                                }
                            }
                        """)
                    else:
                        self.driver.execute_script("""
                            var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                            for (var t of tabs) {
                                if (t.textContent.indexOf('方案课程') >= 0 && t.textContent.indexOf('已选') >= 0) { 
                                    t.click(); break; 
                                }
                            }
                        """)
                else:
                    self.driver.execute_script("""
                        var tabs = document.querySelectorAll('.jqx-tabs-titleContentWrapper');
                        for (var t of tabs) {
                            if (t.textContent.indexOf('已选课程') >= 0) { t.click(); break; }
                        }
                    """)
                time.sleep(0.5)
            
            # 检查是否有该课程 - 通过teachingclassid匹配
            found = self.driver.execute_script("""
                var tcId = arguments[0];
                var rows = document.querySelectorAll('.cv-row');
                for (var r of rows) {
                    // 方式1: cv-row的teachingclassid属性
                    if (r.getAttribute('teachingclassid') === tcId) return true;
                    // 方式2: 退选链接的teachingclassid
                    var delLink = r.querySelector('a.delVolunteer[teachingclassid]');
                    if (delLink && delLink.getAttribute('teachingclassid') === tcId) return true;
                    // 方式3: 第二轮的withdrew链接
                    var link = r.querySelector('a.withdrew[teachingclassid]');
                    if (link && link.getAttribute('teachingclassid') === tcId) return true;
                    // 方式4: 第一轮公选课的退选按钮
                    var btn = r.querySelector('button.cv-delete-volunteer[tcid]');
                    if (btn && btn.getAttribute('tcid') === tcId) return true;
                }
                return false;
            """, tc_id)
            
            self.status.emit(f"[DEBUG] 已选课程检查: tcid={tc_id}, found={found}")
            
            self.driver.execute_script("""
                var closeBtn = document.querySelector('.jqx-window-close-button');
                if (closeBtn) closeBtn.click();
            """)
            time.sleep(0.2)
            
            return found
        except Exception as e:
            self.status.emit(f"[DEBUG] 检查已选课程异常: {e}")
            return False


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.driver = None
        self.is_logged_in = False
        self.token = ''
        self.batch_code = ''
        self.student_code = ''
        self.cookies = ''
        self.grab_workers = []
        self.multi_grab_worker = None  # 多课程监控线程
        self._pending_monitor_courses = []
        
        self.init_ui()
        self.load_config()
        
        # 页面状态监控定时器 - 每2秒检查一次（快速响应登录状态变化）
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.check_and_refresh)
        self.no_data_count = 0  # 连续无数据次数
    
    def init_ui(self):
        self.setWindowTitle('YNU选课助手 Pro')
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)
        
        # 设置明亮风格样式
        self.setStyleSheet("""
            /* 主窗口背景 */
            QMainWindow {
                background-color: #f5f5f7;
            }
            
            /* 通用控件样式 */
            QWidget {
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                font-size: 13px;
                color: #1d1d1f;
            }
            
            /* 分组框 */
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 10px;
                margin-top: 14px;
                padding: 16px 12px 12px 12px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                color: #0066cc;
                font-size: 12px;
            }
            
            /* 输入框 */
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 6px;
                padding: 8px 10px;
                color: #1d1d1f;
                selection-background-color: #0066cc;
            }
            QLineEdit:focus {
                border: 1px solid #0066cc;
            }
            QLineEdit:hover {
                border: 1px solid #86868b;
            }
            QLineEdit::placeholder {
                color: #86868b;
            }
            
            /* 下拉框 */
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 6px;
                padding: 8px 28px 8px 10px;
                color: #1d1d1f;
                min-width: 100px;
            }
            QComboBox:hover {
                border: 1px solid #86868b;
            }
            QComboBox:focus {
                border: 1px solid #0066cc;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #86868b;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 6px;
                selection-background-color: #e8e8ed;
                color: #1d1d1f;
                padding: 4px;
                outline: none;
            }
            
            /* 按钮 - 主要 */
            QPushButton {
                background-color: #0066cc;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0077ed;
            }
            QPushButton:pressed {
                background-color: #004499;
            }
            QPushButton:disabled {
                background-color: #d2d2d7;
                color: #86868b;
            }
            
            /* 列表控件 */
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item {
                background-color: #f5f5f7;
                border-radius: 6px;
                padding: 10px;
                margin: 3px 2px;
                border-left: 3px solid transparent;
            }
            QListWidget::item:hover {
                background-color: #e8e8ed;
                border-left: 3px solid #86868b;
            }
            QListWidget::item:selected {
                background-color: #e8e8ed;
                border-left: 3px solid #0066cc;
            }
            
            /* 文本编辑框（日志区域） */
            QTextEdit {
                background-color: #1d1d1f;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                padding: 8px;
                color: #a6e3a1;
                font-family: "Consolas", "JetBrains Mono", monospace;
                font-size: 11px;
            }
            
            /* 滚动区域 */
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            
            /* 滚动条 */
            QScrollBar:vertical {
                background-color: #f5f5f7;
                width: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background-color: #c7c7cc;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a1a1a6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar:horizontal {
                background-color: #f5f5f7;
                height: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal {
                background-color: #c7c7cc;
                border-radius: 4px;
                min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #a1a1a6;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
            }
            
            /* 标签 */
            QLabel {
                color: #1d1d1f;
                background: transparent;
            }
            
            /* 进度条 */
            QProgressBar {
                background-color: #e8e8ed;
                border: none;
                border-radius: 4px;
                height: 6px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0066cc;
                border-radius: 4px;
            }
            
            /* 复选框 */
            QCheckBox {
                color: #1d1d1f;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 2px solid #d2d2d7;
                background-color: #ffffff;
            }
            QCheckBox::indicator:hover {
                border: 2px solid #0066cc;
            }
            QCheckBox::indicator:checked {
                background-color: #0066cc;
                border: 2px solid #0066cc;
            }
            
            /* 数字输入框 */
            QSpinBox {
                background-color: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 6px;
                padding: 6px 10px;
                color: #1d1d1f;
            }
            QSpinBox:hover {
                border: 1px solid #86868b;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #e8e8ed;
                border: none;
                width: 20px;
                border-radius: 3px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #d2d2d7;
            }
            
            /* 状态栏 */
            QStatusBar {
                background-color: #ffffff;
                color: #86868b;
                border-top: 1px solid #d2d2d7;
                font-size: 11px;
            }
            
            /* 消息框 */
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QLabel {
                color: #1d1d1f;
            }
        """)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        # ===== 左侧：设置和课程列表 =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setMinimumWidth(380)
        left_panel.setMaximumWidth(420)
        
        # 登录设置
        login_group = QGroupBox("登录设置")
        login_layout = QVBoxLayout(login_group)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("学号")
        login_layout.addWidget(self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        login_layout.addWidget(self.password_input)
        
        self.driver_path_input = QLineEdit()
        self.driver_path_input.setPlaceholderText("ChromeDriver路径")
        self.driver_path_input.setText("chromedriver-win64/chromedriver.exe")
        login_layout.addWidget(self.driver_path_input)
        
        round_layout = QHBoxLayout()
        round_layout.addWidget(QLabel("选课轮次:"))
        self.round_combo = QComboBox()
        self.round_combo.addItems(["第一轮", "第二轮"])
        self.round_combo.setCurrentIndex(1)
        round_layout.addWidget(self.round_combo)
        login_layout.addLayout(round_layout)
        
        self.login_btn = QPushButton("🚀 启动登录")
        self.login_btn.clicked.connect(self.login)
        login_layout.addWidget(self.login_btn)
        
        self.logout_btn = QPushButton("🚪 退出登录")
        self.logout_btn.setStyleSheet("background-color: #ff3b30; color: #ffffff;")
        self.logout_btn.clicked.connect(self.logout)
        self.logout_btn.setEnabled(False)
        login_layout.addWidget(self.logout_btn)
        
        self.status_label = QLabel("● 未登录")
        self.status_label.setStyleSheet("color: #ff3b30; font-weight: bold;")
        login_layout.addWidget(self.status_label)
        
        # 微信推送设置（可折叠）
        self.wechat_toggle_btn = QPushButton("📱 微信推送 ▶")
        self.wechat_toggle_btn.setStyleSheet("background: transparent; border: none; text-align: left; color: #86868b; padding: 5px 0; font-weight: normal;")
        self.wechat_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.wechat_toggle_btn.clicked.connect(self._toggle_wechat_settings)
        login_layout.addWidget(self.wechat_toggle_btn)
        
        self.wechat_widget = QWidget()
        wechat_layout = QVBoxLayout(self.wechat_widget)
        wechat_layout.setContentsMargins(0, 0, 0, 0)
        
        self.wechat_enable_cb = QCheckBox("启用微信推送")
        wechat_layout.addWidget(self.wechat_enable_cb)
        
        self.sendkey_input = QLineEdit()
        self.sendkey_input.setPlaceholderText("Server酱 SendKey")
        wechat_layout.addWidget(self.sendkey_input)
        
        self.wechat_widget.setVisible(False)
        login_layout.addWidget(self.wechat_widget)
        
        left_layout.addWidget(login_group)
        
        # 课程类型选择
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("课程类型:"))
        self.course_type_combo = QComboBox()
        self.course_type_combo.addItems(list(COURSE_TYPES.keys()))
        self.course_type_combo.currentTextChanged.connect(self.on_course_type_changed)
        type_layout.addWidget(self.course_type_combo)
        left_layout.addLayout(type_layout)
        
        # 筛选条件
        filter_layout1 = QHBoxLayout()
        filter_layout1.addWidget(QLabel("冲突:"))
        self.conflict_combo = QComboBox()
        self.conflict_combo.addItems(["全部", "冲突", "不冲突"])
        self.conflict_combo.setFixedWidth(70)
        self.conflict_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout1.addWidget(self.conflict_combo)
        
        filter_layout1.addWidget(QLabel("已满:"))
        self.full_combo = QComboBox()
        self.full_combo.addItems(["全部", "已满", "未满"])
        self.full_combo.setFixedWidth(70)
        self.full_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout1.addWidget(self.full_combo)
        left_layout.addLayout(filter_layout1)
        
        # 课程类别筛选（通识教育选修课程显示"通识类别"，其他显示"课程类别"）
        filter_layout2 = QHBoxLayout()
        self.category_label = QLabel("课程类别:")
        filter_layout2.addWidget(self.category_label)
        self.category_combo = QComboBox()
        # 默认显示推荐课程的课程类别选项
        self._init_category_options('推荐课程')
        self.category_combo.setFixedWidth(160)
        self.category_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout2.addWidget(self.category_combo)
        filter_layout2.addStretch()
        left_layout.addLayout(filter_layout2)
        
        # 关键字搜索
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("关键字搜索")
        self.search_input.returnPressed.connect(self.on_search)
        search_layout.addWidget(self.search_input)
        self.search_btn = QPushButton("🔍")
        self.search_btn.setFixedWidth(30)
        self.search_btn.clicked.connect(self.on_search)
        search_layout.addWidget(self.search_btn)
        left_layout.addLayout(search_layout)
        
        # 课程列表
        left_layout.addWidget(QLabel("📚 课程列表"))
        self.course_list = QListWidget()
        self.course_list.itemClicked.connect(self.on_course_selected)
        left_layout.addWidget(self.course_list)
        
        # 翻页控制
        page_layout = QHBoxLayout()
        self.prev_page_btn = QPushButton("◀ 上一页")
        self.prev_page_btn.clicked.connect(self.on_prev_page)
        page_layout.addWidget(self.prev_page_btn)
        
        self.page_label = QLabel("第1页")
        self.page_label.setAlignment(Qt.AlignCenter)
        page_layout.addWidget(self.page_label)
        
        self.next_page_btn = QPushButton("下一页 ▶")
        self.next_page_btn.clicked.connect(self.on_next_page)
        page_layout.addWidget(self.next_page_btn)
        left_layout.addLayout(page_layout)
        
        self.course_count_label = QLabel("共 0 门课程")
        left_layout.addWidget(self.course_count_label)
        
        main_layout.addWidget(left_panel)
        
        # ===== 中间：排课卡片 =====
        middle_panel = QWidget()
        middle_layout = QVBoxLayout(middle_panel)
        
        self.schedule_title = QLabel("📋 排课详情")
        self.schedule_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        middle_layout.addWidget(self.schedule_title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        cards_widget = QWidget()
        self.cards_layout = QGridLayout(cards_widget)
        self.cards_layout.setSpacing(12)
        scroll.setWidget(cards_widget)
        middle_layout.addWidget(scroll)
        
        main_layout.addWidget(middle_panel, 2)
        
        # ===== 右侧：待抢列表和日志 =====
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #ffffff; border-left: 1px solid #d2d2d7;")
        right_layout = QVBoxLayout(right_panel)
        right_panel.setMinimumWidth(320)
        right_panel.setMaximumWidth(380)
        
        # 待抢列表标题
        grab_title = QLabel("🎯 任务队列")
        grab_title.setStyleSheet("font-weight: bold; color: #0066cc; padding: 8px 0;")
        right_layout.addWidget(grab_title)
        
        self.grab_list = QListWidget()
        self.grab_list.setMinimumHeight(180)
        self.grab_list.setMaximumHeight(250)
        right_layout.addWidget(self.grab_list)
        
        self.grab_count_label = QLabel("待抢: 0 门")
        self.grab_count_label.setStyleSheet("color: #86868b; font-size: 11px;")
        right_layout.addWidget(self.grab_count_label)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.start_btn = QPushButton("▶ 开始")
        self.start_btn.clicked.connect(self.start_monitoring)
        self.start_btn.setStyleSheet("background-color: #34c759; color: #ffffff;")
        btn_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.clicked.connect(self.stop_monitoring)
        self.stop_btn.setStyleSheet("background-color: #ff3b30; color: #ffffff;")
        btn_layout.addWidget(self.stop_btn)
        
        self.remove_btn = QPushButton("🗑️")
        self.remove_btn.clicked.connect(self.remove_from_grab_list)
        self.remove_btn.setStyleSheet("background-color: #8e8e93; color: #ffffff; max-width: 40px;")
        btn_layout.addWidget(self.remove_btn)
        right_layout.addLayout(btn_layout)
        
        # 日志标题
        log_title = QLabel("📝 实时日志")
        log_title.setStyleSheet("font-weight: bold; color: #0066cc; padding: 8px 0; margin-top: 10px;")
        right_layout.addWidget(log_title)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        right_layout.addWidget(self.log_text)
        
        main_layout.addWidget(right_panel)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        
        # 菜单栏
        menubar = self.menuBar()
        menubar.setStyleSheet("QMenuBar { background-color: #ffffff; } QMenuBar::item:selected { background-color: #e8e8ed; }")
        
        help_menu = menubar.addMenu("帮助")
        
        about_action = help_menu.addAction("关于")
        about_action.triggered.connect(self.show_about)
        
        update_action = help_menu.addAction("检查更新")
        update_action.triggered.connect(self.check_update)
    
    def show_about(self):
        """显示关于对话框"""
        about_text = """
<h2>YNU选课助手 Pro</h2>
<p>版本：测试版 (Beta) - 2026.01</p>
<p>适配 Chrome：132.x</p>
<p>作者：YHalo-wyh</p>
<p>原项目：<a href="https://github.com/starwingChen/YNU-xk_spider">starwingChen/YNU-xk_spider</a></p>
<p>GitHub：<a href="https://github.com/YHalo-wyh/YNU-xk_spider">https://github.com/YHalo-wyh/YNU-xk_spider</a></p>

<h3>📱 微信推送配置</h3>
<p>使用 Server酱 实现微信推送：</p>
<ol>
<li>访问 <a href="https://sct.ftqq.com/">https://sct.ftqq.com/</a></li>
<li>微信扫码登录</li>
<li>获取 SendKey</li>
<li>在程序中启用微信推送并填入 SendKey</li>
</ol>

<h3>⚠️ 免责声明</h3>
<p>1. 本工具仅供学习交流使用，请勿用于商业用途</p>
<p>2. 使用本工具产生的一切后果由用户自行承担</p>
<p>3. 本工具不保证抢课成功率，选课结果以学校系统为准</p>
<p>4. 请遵守学校相关规定，合理使用本工具</p>
<p>5. 使用本工具即表示您已阅读并同意以上声明</p>
"""
        msg = QMessageBox(self)
        msg.setWindowTitle("关于")
        msg.setTextFormat(Qt.RichText)
        msg.setText(about_text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
    
    def check_update(self):
        """检查更新"""
        import requests
        try:
            self.statusBar().showMessage("正在检查更新...")
            response = requests.get(
                "https://api.github.com/repos/YHalo-wyh/YNU-xk_spider/releases/latest",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get("tag_name", "unknown")
                current_version = "beta"
                
                if latest_version != current_version:
                    # 查找安装包下载链接
                    download_url = None
                    assets = data.get("assets", [])
                    for asset in assets:
                        name = asset.get("name", "")
                        if name.endswith(".exe") and "Setup" in name:
                            download_url = asset.get("browser_download_url")
                            break
                    
                    if download_url:
                        reply = QMessageBox.question(
                            self, "发现新版本",
                            f"当前版本：{current_version}\n最新版本：{latest_version}\n\n是否自动下载并安装？",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if reply == QMessageBox.Yes:
                            self._download_and_install(download_url, latest_version)
                    else:
                        # 没有找到安装包，打开浏览器
                        reply = QMessageBox.question(
                            self, "发现新版本",
                            f"当前版本：{current_version}\n最新版本：{latest_version}\n\n是否前往下载？",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if reply == QMessageBox.Yes:
                            import webbrowser
                            webbrowser.open("https://github.com/YHalo-wyh/YNU-xk_spider/releases")
                else:
                    QMessageBox.information(self, "检查更新", f"当前已是最新版本 {current_version}")
            elif response.status_code == 404:
                # 没有发布任何 Release
                QMessageBox.information(self, "检查更新", f"当前版本：beta\n\n暂无新版本发布")
            else:
                QMessageBox.warning(self, "检查更新", f"无法获取版本信息 (HTTP {response.status_code})")
            self.statusBar().showMessage("检查更新完成", 3000)
        except requests.exceptions.Timeout:
            QMessageBox.warning(self, "检查更新", "连接超时，请检查网络后重试")
            self.statusBar().showMessage("检查更新超时", 3000)
        except requests.exceptions.ConnectionError:
            QMessageBox.warning(self, "检查更新", "网络连接失败，请检查网络后重试")
            self.statusBar().showMessage("网络连接失败", 3000)
        except Exception as e:
            QMessageBox.warning(self, "检查更新", f"检查更新失败：{str(e)}")
            self.statusBar().showMessage("检查更新失败", 3000)
    
    def _download_and_install(self, url, version):
        """下载并安装更新"""
        import requests
        import tempfile
        import subprocess
        
        try:
            self.statusBar().showMessage(f"正在下载 {version}...")
            
            # 下载文件
            response = requests.get(url, stream=True, timeout=300)
            total_size = int(response.headers.get('content-length', 0))
            
            # 保存到临时目录
            temp_dir = tempfile.gettempdir()
            installer_path = os.path.join(temp_dir, f"YNU_Course_Helper_{version}_Setup.exe")
            
            downloaded = 0
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            self.statusBar().showMessage(f"下载中... {percent}%")
            
            self.statusBar().showMessage("下载完成，正在启动安装程序...")
            
            # 启动安装程序
            subprocess.Popen([installer_path], shell=True)
            
            # 提示用户关闭当前程序
            QMessageBox.information(
                self, "更新",
                "安装程序已启动，请关闭当前程序后完成安装。"
            )
            
        except Exception as e:
            QMessageBox.warning(self, "下载失败", f"下载更新失败：{str(e)}")
            self.statusBar().showMessage("下载失败", 3000)
    
    def log(self, msg):
        # 限制日志最多500条，超过清空
        if self.log_text.document().blockCount() > 500:
            self.log_text.clear()
            self.log_text.append("[INFO] 日志已清空（超过500条）")
        self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    def load_config(self):
        try:
            with open('xk_spider/config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.username_input.setText(config.get('username', ''))
                self.password_input.setText(config.get('password', ''))
                if config.get('driver_path'):
                    self.driver_path_input.setText(config['driver_path'])
                # 微信推送设置
                self.wechat_enable_cb.setChecked(config.get('wechat_enable', False))
                self.sendkey_input.setText(config.get('sendkey', ''))
        except:
            pass
    
    def save_config(self):
        config = {
            'username': self.username_input.text(),
            'password': self.password_input.text(),
            'driver_path': self.driver_path_input.text(),
            'wechat_enable': self.wechat_enable_cb.isChecked(),
            'sendkey': self.sendkey_input.text()
        }
        try:
            os.makedirs('xk_spider', exist_ok=True)
            with open('xk_spider/config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def _toggle_wechat_settings(self):
        """切换微信推送设置的显示/隐藏"""
        visible = not self.wechat_widget.isVisible()
        self.wechat_widget.setVisible(visible)
        self.wechat_toggle_btn.setText("📱 微信推送 ▼" if visible else "📱 微信推送 ▶")
    
    def send_wechat_notify(self, title, content):
        """发送微信推送"""
        if not self.wechat_enable_cb.isChecked():
            return
        sendkey = self.sendkey_input.text().strip()
        if not sendkey:
            return
        try:
            import requests
            url = f'https://sctapi.ftqq.com/{sendkey}.send'
            requests.get(url, params={'text': title, 'desp': content}, timeout=5)
            self.log(f"[INFO] 微信推送已发送: {title}")
        except Exception as e:
            self.log(f"[WARN] 微信推送失败: {e}")
    
    def login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        driver_path = self.driver_path_input.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, "提示", "请输入学号和密码")
            return
        
        self.save_config()
        self.login_btn.setEnabled(False)
        self.login_btn.setText("登录中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        selected_round = "1" if self.round_combo.currentIndex() == 0 else "2"
        
        self.login_worker = LoginWorker(driver_path, username, password, selected_round)
        self.login_worker.success.connect(self.on_login_success)
        self.login_worker.failed.connect(self.on_login_failed)
        self.login_worker.status.connect(lambda msg: self.statusBar().showMessage(msg))
        self.login_worker.start()
    
    def on_login_success(self, cookies, token, batch_code, student_code, driver):
        self.cookies = cookies
        self.token = token
        self.batch_code = batch_code
        self.student_code = student_code
        self.driver = driver
        self.is_logged_in = True
        
        self.status_label.setText(f"● 已登录 - {student_code}")
        self.status_label.setStyleSheet("color: #34c759; font-weight: bold;")
        self.login_btn.setText("已登录")
        self.login_btn.setEnabled(False)
        self.logout_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.log("[SUCCESS] 登录成功！")
        
        # 登录成功后立即刷新课程列表
        QTimer.singleShot(500, self.refresh_courses)
        
        # 启动页面状态监控（每5秒检测一次）
        self.no_data_count = 0
        self.refresh_timer.start(5000)
        
        # 恢复待监控课程 - 第一时间找到课程位置并开始监控
        if self._pending_monitor_courses:
            self.log(f"[INFO] 恢复监控 {len(self._pending_monitor_courses)} 门课程")
            for course in self._pending_monitor_courses:
                self.start_grab_course(course)
            self._pending_monitor_courses = []
    
    def on_login_failed(self, error):
        self.log(f"[ERROR] {error}")
        self.login_btn.setEnabled(True)
        self.login_btn.setText("🚀 启动登录")
        self.logout_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        QMessageBox.warning(self, "登录失败", error)
    
    def logout(self):
        """退出登录"""
        # 停止所有监控
        self.stop_monitoring()
        self.refresh_timer.stop()
        
        # 关闭浏览器
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        
        # 重置状态
        self.is_logged_in = False
        self.token = ''
        self.batch_code = ''
        self.cookies = ''
        self.no_data_count = 0
        self._pending_monitor_courses = []
        
        # 清空课程列表
        self.course_list.clear()
        self._courses_data = {}
        self.clear_cards()
        
        # 更新UI
        self.login_btn.setEnabled(True)
        self.login_btn.setText("🚀 启动登录")
        self.logout_btn.setEnabled(False)
        self.status_label.setText("● 未登录")
        self.status_label.setStyleSheet("color: #ff3b30; font-weight: bold;")
        self.course_count_label.setText("共 0 门课程")
        self.page_label.setText("第1页")
        
        self.log("[INFO] 已退出登录")
    
    def check_and_refresh(self):
        """检查页面状态 - 每5秒检测一次"""
        if not self.driver or not self.is_logged_in:
            return
        
        try:
            # 检测页面状态
            page_state = self.driver.execute_script("""
                // 1. 检查轮次选择弹窗
                if (document.querySelector('input[name="electiveBatchSelect"]')) {
                    return 'batch_select';
                }
                // 2. 检查开始选课按钮
                var btn = document.getElementById('courseBtn');
                if (btn && btn.offsetWidth > 0) return 'start_btn';
                // 3. 检查登录页面
                var loginBtn = document.getElementById('studentLoginBtn');
                if (loginBtn && loginBtn.offsetWidth > 0) return 'login_page';
                
                // 4. 检查是否有课程数据 - 和refresh_courses一样的逻辑
                var containers = ['#cvCanSelectPublicCourse', '#cvCanSelectRecommendCourse', 
                                  '#cvCanSelectProgramCourse', '#cvCanSelectSportCourse', '.cv-body'];
                for (var sel of containers) {
                    var container = document.querySelector(sel);
                    if (container) {
                        var rows = container.querySelectorAll('.cv-row');
                        for (var r of rows) {
                            var t = r.querySelector('.cv-title-col') || r.querySelector('.cv-course');
                            if (t) {
                                var text = t.textContent.trim().replace(/\\[冲突\\]/g, '');
                                if (text && text !== '课程名称' && text !== '课程名' && text.length > 2) {
                                    return 'has_data';
                                }
                            }
                        }
                    }
                }
                
                // 5. 检查是否在选课页面
                if (document.getElementById('aPublicCourse')) return 'no_data';
                return 'unknown';
            """)
            
            self.log(f"[DEBUG] 页面状态: {page_state}")
            
            if page_state == 'login_page':
                self.log("[INFO] 检测到登录页面，立即执行登录...")
                self._do_login_steps()
                self.no_data_count = 0
                self._no_program_data_time = None
                return
            
            if page_state == 'start_btn':
                # 点击开始选课按钮
                self.log("[INFO] 检测到开始选课按钮，点击进入...")
                self.driver.execute_script("document.getElementById('courseBtn').click();")
                self.no_data_count = 0
                self._no_program_data_time = None
                return
            
            if page_state == 'batch_select':
                # 选择轮次并点确定
                self.log("[INFO] 检测到轮次选择页面，选择轮次...")
                target = "第一轮" if self.round_combo.currentIndex() == 0 else "第二轮"
                self.driver.execute_script("""
                    var target = arguments[0];
                    var radios = document.querySelectorAll('input[name="electiveBatchSelect"]');
                    for (var r of radios) {
                        var data = r.getAttribute('data-value');
                        if (data && data.indexOf(target) >= 0) { r.click(); break; }
                    }
                """, target)
                time.sleep(0.3)
                self.driver.execute_script("""
                    var btns = document.querySelectorAll('button.bh-btn-primary');
                    for (var b of btns) { if (b.textContent.trim() === '确定') { b.click(); break; } }
                """)
                self.no_data_count = 0
                self._no_program_data_time = None
                return
            
            if page_state == 'has_data':
                # 页面有数据，重置页面无数据计数
                self.no_data_count = 0
                
                # 同步数据到程序
                if self.course_list.count() == 0:
                    # 程序没数据，记录开始时间
                    if not hasattr(self, '_no_program_data_time') or self._no_program_data_time is None:
                        self._no_program_data_time = time.time()
                    
                    elapsed = time.time() - self._no_program_data_time
                    if elapsed >= 5:
                        # 超过5秒程序没数据，强制刷新页面
                        self.log(f"[WARN] 程序无数据超过5秒，强制刷新页面")
                        self._no_program_data_time = None
                        self.course_list.clear()
                        self._courses_data = {}
                        self.driver.refresh()
                    else:
                        # 尝试同步数据
                        self.refresh_courses()
                else:
                    # 程序有数据，重置计时
                    self._no_program_data_time = None
            else:
                # no_data - 页面没有课程数据，清空程序列表并刷新
                self.no_data_count += 1
                self._no_program_data_time = None
                
                # 清空程序课程列表
                self.course_list.clear()
                self._courses_data = {}
                self.course_count_label.setText("加载中...")
                
                self.log(f"[WARN] 页面无课程数据，刷新中... (第{self.no_data_count}次)")
                
                if self.no_data_count >= 3:
                    # 连续3次无数据，关闭旧浏览器，打开新的重新登录
                    self.log("[WARN] 连续3次无数据，关闭旧浏览器，重新登录...")
                    self.auto_relogin()
                else:
                    # 无数据就刷新
                    self.driver.refresh()
                    
        except Exception as e:
            error_msg = str(e)
            # 检测浏览器是否被关闭
            if 'no such window' in error_msg or 'target window already closed' in error_msg or 'web view not found' in error_msg or 'invalid session id' in error_msg:
                self.log("[WARN] 浏览器已关闭，准备重新登录...")
                self.driver = None
                self.is_logged_in = False
                self.auto_relogin()
            else:
                self.log(f"[ERROR] 检查页面失败: {error_msg[:100]}")
    
    def _do_login_steps(self):
        """在登录页面执行登录步骤 - 快速执行"""
        try:
            # 检查当前登录页状态
            login_state = self.driver.execute_script("""
                var result = {
                    hasLoginForm: document.getElementById('loginName') !== null,
                    hasVerifyCode: document.getElementById('verifyCode') !== null,
                    verifyCodeValue: '',
                    hasError: false,
                    errorText: '',
                    hasBatchSelect: document.querySelector('input[name="electiveBatchSelect"]') !== null
                };
                var vcode = document.getElementById('verifyCode');
                if (vcode) result.verifyCodeValue = vcode.value || '';
                var err = document.getElementById('errorMsg');
                if (err && err.style.display !== 'none') {
                    result.hasError = true;
                    result.errorText = err.textContent || '';
                }
                return result;
            """)
            
            self.log(f"[DEBUG] 登录页状态: {login_state}")
            
            # 如果已经出现轮次选择，说明登录成功了，不需要再操作
            if login_state.get('hasBatchSelect'):
                self.log("[INFO] 已出现轮次选择，跳过登录步骤")
                return
            
            # 如果有错误提示（验证码错误等），必须刷新验证码并重新识别
            has_error = login_state.get('hasError', False)
            error_text = login_state.get('errorText', '')
            
            if has_error and '验证码' in error_text:
                self.log("[INFO] 验证码错误，刷新并重新识别...")
                # 刷新验证码图片
                self.driver.execute_script("document.getElementById('vcodeImg').click();")
                time.sleep(0.8)  # 等待新验证码图片加载
                
                # 重新识别验证码
                captcha_code = self._recognize_captcha_quick()
                if not captcha_code:
                    self.log("[WARN] 验证码识别失败，等待下次重试")
                    return
                
                # 清空并重新填写验证码
                self.driver.execute_script("""
                    var c = arguments[0];
                    var vcode = document.getElementById('verifyCode');
                    if (vcode) { vcode.value = ''; vcode.value = c; }
                """, captcha_code)
                
                self.log(f"[INFO] 重新填写验证码={captcha_code}")
                
                # 点击登录按钮
                self.driver.execute_script("document.getElementById('studentLoginBtn').click();")
                self.log("[INFO] 已点击登录按钮")
                return
            
            # 如果验证码已经填写且没有错误，直接点击登录
            vcode_value = login_state.get('verifyCodeValue', '')
            if len(vcode_value) >= 4 and not has_error:
                self.log(f"[INFO] 验证码已填写({vcode_value})，点击登录")
                self.driver.execute_script("document.getElementById('studentLoginBtn').click();")
                return
            
            # 首次填写或验证码为空，刷新验证码并识别
            self.log("[INFO] 首次填写，刷新验证码...")
            self.driver.execute_script("document.getElementById('vcodeImg').click();")
            time.sleep(0.8)  # 等待新验证码图片加载
            
            # 识别验证码
            captcha_code = self._recognize_captcha_quick()
            if not captcha_code:
                self.log("[WARN] 验证码识别失败，等待下次重试")
                return
            
            # 快速填写表单
            username = self.username_input.text().strip()
            password = self.password_input.text().strip()
            
            self.driver.execute_script("""
                var u = arguments[0], p = arguments[1], c = arguments[2];
                document.getElementById('loginName').value = u;
                document.getElementById('loginPwd').value = p;
                document.getElementById('verifyCode').value = c;
            """, username, password, captcha_code)
            
            self.log(f"[INFO] 填写完成，验证码={captcha_code}")
            
            # 点击登录按钮
            self.driver.execute_script("document.getElementById('studentLoginBtn').click();")
            self.log("[INFO] 已点击登录按钮")
                
        except Exception as e:
            self.log(f"[ERROR] 登录步骤失败: {e}")
    
    def _recognize_captcha_quick(self):
        """快速识别验证码"""
        # 复用OCR实例
        if not hasattr(self, '_ocr_instance'):
            if OCR_AVAILABLE:
                try:
                    self._ocr_instance = ddddocr.DdddOcr(show_ad=False)
                except:
                    self._ocr_instance = ddddocr.DdddOcr()
            else:
                self._ocr_instance = None
        
        for attempt in range(2):
            try:
                # 等待验证码图片加载完成
                time.sleep(0.5)
                
                # 检查图片是否加载完成
                img_loaded = self.driver.execute_script("""
                    var img = document.getElementById('vcodeImg');
                    return img && img.complete && img.naturalWidth > 0;
                """)
                
                if not img_loaded:
                    self.log(f"[WARN] 验证码图片未加载，等待...")
                    time.sleep(0.5)
                
                captcha_img = self.driver.find_element(By.ID, 'vcodeImg')
                img_bytes = captcha_img.screenshot_as_png
                
                if self._ocr_instance and img_bytes and len(img_bytes) > 100:
                    result = self._ocr_instance.classification(img_bytes)
                    if result:
                        # 只保留字母和数字，过滤乱码
                        clean_result = ''.join(c for c in result if c.isalnum() and ord(c) < 128)
                        if len(clean_result) >= 4:
                            code = clean_result[:4]
                            self.log(f"[INFO] 验证码: {code}")
                            return code
                
                # 识别失败，点击刷新验证码
                self.log(f"[WARN] 验证码识别失败({attempt + 1}/2)，刷新...")
                captcha_img.click()
                time.sleep(0.8)
                
            except Exception as e:
                self.log(f"[ERROR] 验证码异常: {str(e)[:50]}")
                time.sleep(0.3)
        return None
    
    def switch_tab_and_back(self):
        """切换到其他板块再切回来"""
        try:
            current_type = self.course_type_combo.currentText()
            current_code = COURSE_TYPES.get(current_type, 'TJKC')
            current_tab_id = TAB_MAP.get(current_code, 'aRecommendCourse')
            
            # 选一个不同的板块
            other_tab_ids = [v for k, v in TAB_MAP.items() if v != current_tab_id]
            if other_tab_ids:
                other_tab_id = other_tab_ids[0]
                
                self.log(f"[INFO] 切换板块刷新...")
                # 切到其他板块
                self.driver.execute_script(f"""
                    var el = document.getElementById('{other_tab_id}');
                    if (el) el.click();
                """)
                time.sleep(1)
                # 切回来
                self.driver.execute_script(f"""
                    var el = document.getElementById('{current_tab_id}');
                    if (el) el.click();
                """)
                time.sleep(1)
        except Exception as e:
            self.log(f"[ERROR] 切换板块失败: {e}")
    
    def auto_relogin(self):
        """自动重新登录 - 关闭旧浏览器，打开新的"""
        self.log("[INFO] 关闭旧浏览器，重新启动登录...")
        
        # 停止定时器
        self.refresh_timer.stop()
        self.no_data_count = 0
        
        # 保存待抢列表（包含课程位置信息）
        self._pending_monitor_courses = []
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                self._pending_monitor_courses.append(data)
        
        if self._pending_monitor_courses:
            self.log(f"[INFO] 保存待抢课程 {len(self._pending_monitor_courses)} 门，重新登录后继续监控")
        
        # 停止监控
        for w in self.grab_workers:
            w.stop()
        self.grab_workers.clear()
        
        # 关闭旧浏览器
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        
        self.is_logged_in = False
        self.login_btn.setEnabled(True)
        self.login_btn.setText("🚀 启动登录")
        
        # 自动重新登录
        self.login()
    
    def on_course_type_changed(self, course_type):
        """课程类型改变 - 立即刷新"""
        # 清空显示和缓存
        self.course_list.clear()
        self.clear_cards()
        self._courses_data = {}  # 清空缓存
        self.course_count_label.setText("加载中...")
        self.page_label.setText("第1页")
        
        # 更新类别筛选选项
        self._init_category_options(course_type)
        
        if self.is_logged_in and self.driver:
            # 立即刷新，不等定时器
            self.no_data_count = 0
            # 使用 QTimer 延迟执行，避免阻塞 UI
            QTimer.singleShot(100, self.refresh_courses)
    
    def _init_category_options(self, course_type):
        """根据课程类型初始化类别选项"""
        self.category_combo.blockSignals(True)  # 阻止触发信号
        self.category_combo.clear()
        self.category_combo.addItem("全部", "")
        
        if course_type == '通识教育选修课程':
            # 通识教育选修课程 - 通识类别
            self.category_label.setText("通识类别:")
            self.category_combo.addItem("科学精神与技术进步", "13")
            self.category_combo.addItem("创新创业与能力提升", "16")
            self.category_combo.addItem("民族文化与社会情怀", "22")
            self.category_combo.addItem("人文素养与艺术审美", "23")
            self.category_combo.addItem("生态文明与健康生活", "24")
            self.category_combo.addItem("文明对话与国际视野", "25")
        else:
            # 其他板块 - 课程类别
            self.category_label.setText("课程类别:")
            self.category_combo.addItem("通识教育必修课程", "17")
            self.category_combo.addItem("跨学科教育课程", "13")
            self.category_combo.addItem("专业核心课程", "08")
            self.category_combo.addItem("专业选修课程", "04")
            self.category_combo.addItem("个性拓展教育课程", "15")
            self.category_combo.addItem("专业深度教育课程", "14")
            self.category_combo.addItem("综合实践课程", "07")
            self.category_combo.addItem("新生研讨课程", "16")
            self.category_combo.addItem("方案外课程", "19")
            self.category_combo.addItem("创新创业与能力提升", "23")
            self.category_combo.addItem("人文素养与艺术审美", "24")
            self.category_combo.addItem("文明对话与国际视野", "25")
            self.category_combo.addItem("民族文化与社会情怀", "26")
            self.category_combo.addItem("生态文明与健康生活", "27")
            self.category_combo.addItem("科学精神与技术进步", "28")
            self.category_combo.addItem('"AI+"课程', "30")
            self.category_combo.addItem("（大类）学科基础必修课程", "31")
            self.category_combo.addItem("（大类）学科基础选修课程", "32")
            self.category_combo.addItem("拓展教育课程", "33")
            self.category_combo.addItem("微专业必修课程", "36")
        
        self.category_combo.blockSignals(False)
    
    def on_filter_changed(self):
        """筛选条件改变"""
        if not self.is_logged_in or not self.driver:
            return
        
        course_type = self.course_type_combo.currentText()
        
        # 获取筛选值
        conflict_idx = self.conflict_combo.currentIndex()  # 0=全部, 1=冲突, 2=不冲突
        full_idx = self.full_combo.currentIndex()  # 0=全部, 1=已满, 2=未满
        category_value = self.category_combo.currentData() or ""
        
        # 获取当前课程类型对应的筛选元素ID前缀
        prefix_map = {
            '推荐课程': 'recommend',
            '主修课程': 'program',
            '通识教育选修课程': 'public',
            '公共体育课': 'sport',
        }
        prefix = prefix_map.get(course_type, 'recommend')
        
        # 转换筛选值：0=全部(2), 1=是(1), 2=否(0)
        conflict_value = "2" if conflict_idx == 0 else ("1" if conflict_idx == 1 else "0")
        full_value = "2" if full_idx == 0 else ("1" if full_idx == 1 else "0")
        
        # 判断是否是通识教育选修课程
        is_public = (course_type == '通识教育选修课程')
        
        try:
            # 设置筛选条件
            self.driver.execute_script("""
                var prefix = arguments[0];
                var conflict = arguments[1];
                var full = arguments[2];
                var category = arguments[3];
                var isPublic = arguments[4];
                
                // 是否冲突
                var sfct = document.getElementById(prefix + '_sfct');
                if (sfct) {
                    sfct.value = conflict;
                    sfct.dispatchEvent(new Event('change', {bubbles: true}));
                }
                
                // 是否已满
                var sfym = document.getElementById(prefix + '_sfym');
                if (sfym) {
                    sfym.value = full;
                    sfym.dispatchEvent(new Event('change', {bubbles: true}));
                }
                
                // 类别筛选
                if (isPublic) {
                    // 通识教育选修课程 - 使用 public_xgxklb
                    var xgxklb = document.getElementById('public_xgxklb');
                    if (xgxklb) {
                        xgxklb.value = category;
                        xgxklb.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                } else {
                    // 其他板块 - 使用 prefix_kclb
                    var kclb = document.getElementById(prefix + '_kclb');
                    if (kclb) {
                        kclb.value = category;
                        kclb.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }
            """, prefix, conflict_value, full_value, category_value, is_public)
            
            self.log(f"[INFO] 筛选: 冲突={conflict_value}, 已满={full_value}, 类别={category_value or '全部'}")
            time.sleep(0.5)
            self.refresh_courses()
        except Exception as e:
            self.log(f"[ERROR] 设置筛选条件失败: {e}")
    
    def on_search(self):
        """关键字搜索"""
        if not self.is_logged_in or not self.driver:
            return
        
        keyword = self.search_input.text().strip()
        
        # 获取当前课程类型对应的搜索框ID
        course_type = self.course_type_combo.currentText()
        search_id_map = {
            '推荐课程': 'recommendSearch',
            '主修课程': 'programSearch',
            '通识教育选修课程': 'publicSearch',
            '公共体育课': 'sportSearch',
        }
        search_id = search_id_map.get(course_type, 'recommendSearch')
        
        try:
            # 设置搜索关键字并触发搜索
            self.driver.execute_script("""
                var searchId = arguments[0];
                var keyword = arguments[1];
                var input = document.getElementById(searchId);
                if (input) {
                    input.value = keyword;
                    // 触发input和keyup事件
                    input.dispatchEvent(new Event('input'));
                    input.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', keyCode: 13}));
                }
            """, search_id, keyword)
            
            self.log(f"[INFO] 搜索: {keyword}")
            time.sleep(0.5)
            self.refresh_courses()
        except Exception as e:
            self.log(f"[ERROR] 搜索失败: {e}")
    
    def on_prev_page(self):
        """上一页"""
        if not self.is_logged_in or not self.driver:
            return
        
        course_type = self.course_type_combo.currentText()
        btn_id_map = {
            '推荐课程': 'recommendUp',
            '主修课程': 'programUp',
            '通识教育选修课程': 'publicUp',
            '公共体育课': 'sportUp',
        }
        btn_id = btn_id_map.get(course_type, 'recommendUp')
        
        try:
            # 先清空课程列表
            self.course_list.clear()
            self._courses_data = {}
            self.course_count_label.setText("加载中...")
            
            self.driver.execute_script(f"""
                var btn = document.getElementById('{btn_id}');
                if (btn) btn.click();
            """)
            time.sleep(0.5)
            self._update_page_label()
            self.refresh_courses()
        except Exception as e:
            self.log(f"[ERROR] 上一页失败: {e}")
    
    def on_next_page(self):
        """下一页"""
        if not self.is_logged_in or not self.driver:
            return
        
        course_type = self.course_type_combo.currentText()
        btn_id_map = {
            '推荐课程': 'recommendDown',
            '主修课程': 'programDown',
            '通识教育选修课程': 'publicDown',
            '公共体育课': 'sportDown',
        }
        btn_id = btn_id_map.get(course_type, 'recommendDown')
        
        try:
            # 先清空课程列表
            self.course_list.clear()
            self._courses_data = {}
            self.course_count_label.setText("加载中...")
            
            self.driver.execute_script(f"""
                var btn = document.getElementById('{btn_id}');
                if (btn) btn.click();
            """)
            time.sleep(0.5)
            self._update_page_label()
            self.refresh_courses()
        except Exception as e:
            self.log(f"[ERROR] 下一页失败: {e}")
    
    def _update_page_label(self):
        """更新页码显示"""
        if not self.driver:
            return
        
        course_type = self.course_type_combo.currentText()
        page_id_map = {
            '推荐课程': 'recommendPageNumber',
            '主修课程': 'programPageNumber',
            '通识教育选修课程': 'publicPageNumber',
            '公共体育课': 'sportPageNumber',
        }
        total_id_map = {
            '推荐课程': 'recommendTotalPage',
            '主修课程': 'programTotalPage',
            '通识教育选修课程': 'publicTotalPage',
            '公共体育课': 'sportTotalPage',
        }
        page_id = page_id_map.get(course_type, 'recommendPageNumber')
        total_id = total_id_map.get(course_type, 'recommendTotalPage')
        
        try:
            page_info = self.driver.execute_script(f"""
                var pageEl = document.getElementById('{page_id}');
                var totalEl = document.getElementById('{total_id}');
                return {{
                    current: pageEl ? parseInt(pageEl.textContent) || 1 : 1,
                    total: totalEl ? parseInt(totalEl.textContent) || 1 : 1
                }};
            """)
            self.page_label.setText(f"第{page_info['current']}/{page_info['total']}页")
        except:
            pass
    
    def refresh_courses(self):
        """刷新课程列表"""
        if not self.driver:
            return
        
        # 清空缓存和显示
        self._courses_data = {}
        self.course_list.clear()
        
        course_type = self.course_type_combo.currentText()
        course_type_code = COURSE_TYPES.get(course_type, 'TJKC')
        tab_id = TAB_MAP.get(course_type_code, 'aRecommendCourse')
        
        # 板块容器ID映射
        container_map = {
            '推荐课程': '#cvCanSelectRecommendCourse',
            '主修课程': '#cvCanSelectProgramCourse', 
            '通识教育选修课程': '#cvCanSelectPublicCourse',
            '公共体育课': '#cvCanSelectSportCourse',
        }
        container_selector = container_map.get(course_type, '#cvCanSelectRecommendCourse')
        
        # 判断是否是通识教育选修课程
        is_public_course = (course_type == '通识教育选修课程')
        
        try:
            # 点击Tab
            self.driver.execute_script(f"""
                var tab = document.getElementById('{tab_id}');
                if (tab) tab.click();
            """)
            
            # 等待数据加载
            time.sleep(0.8)
            
            # 等待行数据出现
            for _ in range(6):
                row_count = self.driver.execute_script("""
                    var container = document.querySelector(arguments[0]);
                    if (!container) container = document;
                    var rows = container.querySelectorAll('.cv-row');
                    var count = 0;
                    for (var r of rows) {
                        var t = r.querySelector('.cv-title-col') || r.querySelector('.cv-course');
                        if (t && t.textContent.trim() && t.textContent.trim() !== '课程名称' && t.textContent.trim() !== '课程名') count++;
                    }
                    return count;
                """, container_selector)
                if row_count > 0:
                    break
                time.sleep(0.3)
            
            # 获取数据
            if is_public_course:
                result = self._fetch_public_courses(container_selector)
            else:
                result = self._fetch_other_courses(container_selector)
            
            self._courses_data = json.loads(result) if result else {}
            
            # 更新列表
            for number, data in self._courses_data.items():
                name = data.get('name', '')
                teacher = data.get('teacher', '')
                display = f"{number} {name}" + (f" - {teacher}" if teacher else "")
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, number)
                self.course_list.addItem(item)
            
            self.course_count_label.setText(f"共 {self.course_list.count()} 门课程")
            
            # 更新页码显示
            self._update_page_label()
            
            if self.course_list.count() == 0:
                self.course_count_label.setText("暂无课程")
            
        except Exception as e:
            self.log(f"[ERROR] 刷新失败: {e}")
    
    def _fetch_public_courses(self, container_selector):
        """获取通识教育选修课程数据"""
        return self.driver.execute_script("""
            var containerSel = arguments[0];
            var container = document.querySelector(containerSel);
            
            // 如果找不到容器，尝试其他方式
            if (!container) {
                container = document.querySelector('.cv-body');
            }
            if (!container) {
                container = document;
            }
            
            var courses = {};
            var rows = container.querySelectorAll('.cv-row');
            rows.forEach(function(row) {
                var titleCol = row.querySelector('.cv-title-col');
                var numCol = row.querySelector('.cv-number-col');
                var teacherCol = row.querySelector('.cv-teacher-col');
                var timeCol = row.querySelector('.cv-time-col');
                var capCol = row.querySelector('.cv-capcity-col');
                var volCol = row.querySelector('.cv-firstVolunteer-col');
                var choice = row.querySelector('a.cv-choice');
                
                if (titleCol && numCol) {
                    var name = titleCol.textContent.trim();
                    // 去掉[冲突]标记
                    name = name.replace(/\\[冲突\\]/g, '').trim();
                    
                    if (name && name !== '课程名称') {
                        // 优先从title属性获取完整编号
                        var number = numCol.getAttribute('title') || '';
                        if (!number) {
                            var numLink = numCol.querySelector('a.cv-detail');
                            number = numLink ? numLink.textContent.trim() : numCol.textContent.replace(/教学班详情/g, '').trim();
                        }
                        var tcid = choice ? choice.getAttribute('tcid') : '';
                        
                        if (number && !courses[number]) {
                            courses[number] = {
                                number: number,
                                name: name,
                                tcid: tcid,
                                teacher: teacherCol ? teacherCol.textContent.trim() : '',
                                time: timeCol ? (timeCol.getAttribute('title') || timeCol.textContent.trim()) : '',
                                capacity: capCol ? capCol.textContent.trim() : '0',
                                volunteer: volCol ? volCol.textContent.trim() : '0',
                                isConflict: choice ? choice.getAttribute('isconflict') === '1' : false,
                                type: 'public'
                            };
                        }
                    }
                }
            });
            return JSON.stringify(courses);
        """, container_selector)
    
    def _fetch_other_courses(self, container_selector):
        """获取其他课程数据"""
        return self.driver.execute_script("""
            var containerSel = arguments[0];
            var container = document.querySelector(containerSel);
            
            // 如果找不到容器，尝试找 .cv-body
            if (!container) {
                container = document.querySelector('.cv-body');
            }
            if (!container) {
                // 直接从整个页面获取
                container = document;
            }
            
            var courses = {};
            var rows = container.querySelectorAll('.cv-row');
            rows.forEach(function(row) {
                var courseEl = row.querySelector('.cv-course');
                var numEl = row.querySelector('.cv-num');
                var courseNum = row.getAttribute('coursenumber');
                
                if (courseEl && (numEl || courseNum)) {
                    var name = courseEl.textContent.trim();
                    var number = courseNum || (numEl ? numEl.textContent.replace(/课程详情/g, '').trim() : '');
                    
                    if (name && name !== '课程名称' && name !== '课程名' && number) {
                        if (!courses[number]) {
                            courses[number] = {
                                number: number,
                                name: name,
                                type: 'recommend'
                            };
                        }
                    }
                }
            });
            return JSON.stringify(courses);
        """, container_selector)
    
    def on_course_selected(self, item):
        """课程被选中 - 显示该课程的详情卡片"""
        if not item:
            return
        
        course_number = item.data(Qt.UserRole)
        if not course_number or not hasattr(self, '_courses_data'):
            return
        
        course_data = self._courses_data.get(course_number, {})
        course_type = course_data.get('type', 'public')
        
        # 先清空所有卡片
        self.clear_cards()
        
        name = course_data.get('name', '')
        teacher = course_data.get('teacher', '')
        self.schedule_title.setText(f"📋 {course_number} {name}")
        
        if course_type == 'public':
            # 通识教育课 - 直接显示这个课程编号的卡片
            card_data = {
                'JXBID': course_data.get('tcid', ''),
                'KCM': name,
                'SKJS': teacher,
                'SKSJ': course_data.get('time', ''),
                'KRL': course_data.get('capacity', '0'),
                'DYZY': course_data.get('volunteer', '0'),
                'isConflict': course_data.get('isConflict', False),
                'number': course_number,
                'type': 'public'  # 标记为通识教育课
            }
            card = CourseCard(card_data)
            card.grab_clicked.connect(self.add_to_grab_list)
            self.cards_layout.addWidget(card, 0, 0)
        elif course_type == 'recommend' and self.driver:
            # 推荐课程等 - 先点击浏览器中的课程行，再获取排课卡片
            self.fetch_recommend_schedules(course_number, name)
    
    def fetch_recommend_schedules(self, course_number, course_name):
        """获取推荐课程的排课卡片 - 先点击课程行再获取该课程的卡片"""
        # 先清空卡片
        self.clear_cards()
        
        try:
            # 先点击浏览器中的课程行
            self.driver.execute_script("""
                var courseNum = arguments[0];
                // 找到课程行并点击
                var row = document.querySelector('.cv-row[coursenumber="' + courseNum + '"]');
                if (row) {
                    row.click();
                } else {
                    // 尝试通过课程编号文本查找
                    var nums = document.querySelectorAll('.cv-num');
                    for (var n of nums) {
                        if (n.textContent.indexOf(courseNum) >= 0) {
                            var r = n.closest('.cv-row');
                            if (r) r.click();
                            break;
                        }
                    }
                }
            """, course_number)
            
            # 等待排课卡片加载
            time.sleep(0.8)
            
            # 只获取当前课程的排课卡片（通过tcid包含课程编号来筛选）
            result = self.driver.execute_script("""
                var courseNum = arguments[0];
                var schedules = [];
                var cards = document.querySelectorAll('.cv-course-card');
                cards.forEach(function(card) {
                    var tcid = card.id ? card.id.replace('_courseDiv', '') : '';
                    if (!tcid) tcid = card.getAttribute('tcid') || '';
                    if (!tcid) {
                        var btn = card.querySelector('.cv-btn-chose[tcid]');
                        if (btn) tcid = btn.getAttribute('tcid');
                    }
                    
                    // 只筛选当前课程的卡片（tcid包含课程编号）
                    if (!tcid || tcid.indexOf(courseNum) < 0) return;
                    
                    var titleEl = card.querySelector('.cv-info-title');
                    var timeEl = card.querySelector('div[title]:not(.cv-info-title)');
                    
                    // 获取容量和志愿人数 - 支持两种格式
                    var cap = '0', vol = '0';
                    var capTexts = card.querySelectorAll('.cv-caption-text:not(.cv-operation)');
                    for (var ct of capTexts) {
                        var text = ct.textContent;
                        // 第一轮格式
                        var capMatch = text.match(/课容量[：:](\\d+)/);
                        if (capMatch) cap = capMatch[1];
                        var volMatch = text.match(/第一志愿[：:](\\d+)/);
                        if (volMatch) vol = volMatch[1];
                        // 第二轮格式
                        var slashMatch = text.match(/^(\\d+)\\/(\\d+)$/);
                        if (slashMatch) { vol = slashMatch[1]; cap = slashMatch[2]; }
                    }
                    
                    // 检查状态
                    var isFull = card.getAttribute('isfull') === '1';
                    var isConflict = card.getAttribute('isconflict') === '1';
                    var isChosen = card.getAttribute('ischoose') === '1';
                    
                    // 检查是否有"课程冲突"标签
                    var conflictTag = card.querySelector('.cv-tag.cv-danger:not(.cv-block-hide)');
                    var hasConflictTag = conflictTag && conflictTag.textContent.indexOf('冲突') >= 0;
                    
                    // 检查是否有"人数已满"标签
                    var fullTag = card.querySelector('.cv-isfull:not(.cv-block-hide)');
                    var hasFullTag = fullTag && fullTag.textContent.indexOf('已满') >= 0;
                    
                    // 检查志愿标签类型
                    var volunteerType = '';
                    var volTag = card.querySelector('.cv-tag.cv-one, .cv-tag.cv-two, .cv-tag.cv-three');
                    if (volTag) {
                        if (volTag.classList.contains('cv-one')) volunteerType = '第一志愿';
                        else if (volTag.classList.contains('cv-two')) volunteerType = '第二志愿';
                        else if (volTag.classList.contains('cv-three')) volunteerType = '第三志愿';
                    }
                    var isFirstVolFull = volTag && volTag.classList.contains('cv-one');
                    
                    schedules.push({
                        tcid: tcid,
                        teacher: titleEl ? titleEl.textContent.trim() : '',
                        time: timeEl ? (timeEl.getAttribute('title') || timeEl.textContent.trim()) : '',
                        capacity: cap,
                        volunteer: vol,
                        volunteerType: volunteerType,
                        isChosen: isChosen,
                        isFull: isFull || hasFullTag,
                        isConflict: isConflict || hasConflictTag,
                        isFirstVolFull: isFirstVolFull
                    });
                });
                return JSON.stringify(schedules);
            """, course_number)
            
            schedules = json.loads(result) if result else []
            self.schedule_title.setText(f"📋 {course_number} {course_name} ({len(schedules)} 个排课)")
            
            # 获取当前轮次
            selected_round = "1" if self.round_combo.currentIndex() == 0 else "2"
            
            row, col = 0, 0
            for s in schedules:
                # 根据轮次判断是否可选
                is_conflict = s.get('isConflict', False)
                is_chosen = s.get('isChosen', False)
                is_full = s.get('isFull', False)
                is_first_vol_full = s.get('isFirstVolFull', False)
                
                if selected_round == "1":
                    # 第一轮：cv-one标签表示已满
                    is_unavailable = is_conflict or is_chosen or is_first_vol_full
                    volunteer_type = s.get('volunteerType', '')  # 第一轮显示志愿类型
                else:
                    # 第二轮：isfull表示已满，不显示志愿信息
                    is_unavailable = is_conflict or is_chosen or is_full
                    volunteer_type = ''  # 第二轮不显示志愿类型
                
                card_data = {
                    'JXBID': s.get('tcid', ''),
                    'KCM': course_name,
                    'SKJS': s.get('teacher', ''),
                    'SKSJ': s.get('time', ''),
                    'KRL': s.get('capacity', '0'),
                    'DYZY': s.get('volunteer', '0'),
                    'volunteerType': volunteer_type,  # 志愿类型（仅第一轮）
                    'isConflict': is_unavailable,
                    'number': course_number,
                    'type': 'recommend'  # 标记为其他课程类型
                }
                card = CourseCard(card_data)
                card.grab_clicked.connect(self.add_to_grab_list)
                self.cards_layout.addWidget(card, row, col)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
        except Exception as e:
            self.log(f"[ERROR] 获取推荐课程排课失败: {e}")
    
    def clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def add_to_grab_list(self, course_data):
        """添加到待抢列表"""
        tcid = course_data.get('JXBID', '')
        name = course_data.get('KCM', '')
        teacher = course_data.get('SKJS', '')
        course_type = course_data.get('type', 'public')
        
        # 检查重复
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            if item.data(Qt.UserRole).get('JXBID') == tcid:
                self.log(f"[INFO] 已在待抢列表: {name}")
                return
        
        # 获取当前页数
        page = 1
        if self.driver:
            try:
                page_id_map = {
                    'public': 'publicPageNumber',
                    'recommend': 'recommendPageNumber',
                    'major': 'programPageNumber',
                    'sport': 'sportPageNumber',
                }
                page_id = page_id_map.get(course_type, 'recommendPageNumber')
                page = self.driver.execute_script(f"""
                    var el = document.getElementById('{page_id}');
                    return el ? parseInt(el.textContent) || 1 : 1;
                """)
            except:
                page = 1
        
        # 记录页数和搜索关键字到课程数据
        course_data['page'] = page
        
        # 记录当前搜索关键字（如果有）
        search_keyword = self.search_input.text().strip()
        if search_keyword:
            course_data['search_keyword'] = search_keyword
        
        item = QListWidgetItem(f"{name} - {teacher}")
        item.setData(Qt.UserRole, course_data)
        self.grab_list.addItem(item)
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        
        locate_info = f"搜索'{search_keyword}'" if search_keyword else f"页{page}"
        self.log(f"[INFO] 已添加: {name} - {teacher} ({locate_info})")
    
    def remove_from_grab_list(self):
        """从待抢列表移除"""
        item = self.grab_list.currentItem()
        if item:
            self.grab_list.takeItem(self.grab_list.row(item))
            self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
    
    def start_monitoring(self):
        """开始监控 - 使用单线程轮询所有课程"""
        if not self.is_logged_in or not self.driver:
            self.log("[WARN] 请先登录")
            QMessageBox.warning(self, "提示", "请先登录后再开始监控")
            return
        
        if self.grab_list.count() == 0:
            self.log("[WARN] 待抢列表为空")
            QMessageBox.warning(self, "提示", "待抢列表为空，请先添加课程")
            return
        
        # 如果已有监控线程在运行，添加新课程到现有线程
        if self.multi_grab_worker and self.multi_grab_worker.isRunning():
            # 添加新课程到现有监控
            for i in range(self.grab_list.count()):
                item = self.grab_list.item(i)
                course = item.data(Qt.UserRole)
                if course:
                    self.multi_grab_worker.add_course(course)
            self.log("[INFO] 已添加课程到监控队列")
            return
        
        # 收集所有待抢课程
        courses = []
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            course = item.data(Qt.UserRole)
            if course:
                courses.append(course)
        
        if not courses:
            return
        
        # 获取当前轮次
        selected_round = "1" if self.round_combo.currentIndex() == 0 else "2"
        
        # 创建多课程监控线程
        self.multi_grab_worker = MultiGrabWorker(self.driver, courses, self.student_code, self.batch_code, selected_round)
        self.multi_grab_worker.success.connect(self.on_grab_success)
        self.multi_grab_worker.failed.connect(lambda msg: self.log(f"[FAILED] {msg}"))
        self.multi_grab_worker.status.connect(self.log)
        self.multi_grab_worker.need_relogin.connect(self.auto_relogin)
        self.multi_grab_worker.course_available.connect(self.on_course_available)
        self.multi_grab_worker.start()
        
        round_text = "第一轮" if selected_round == "1" else "第二轮"
        self.log(f"[INFO] 多课程监控已启动({round_text})，共 {len(courses)} 门课程")
    
    def on_grab_success(self, msg, course):
        """抢课成功回调"""
        self.log(f"[SUCCESS] {msg}")
        
        # 从待抢列表中移除成功的课程
        tc_id = course.get('JXBID', '')
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            data = item.data(Qt.UserRole)
            if data and data.get('JXBID') == tc_id:
                self.grab_list.takeItem(i)
                break
        
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        
        # 微信推送
        course_name = course.get('KCM', '')
        teacher = course.get('teacher', '')
        self.send_wechat_notify(f"🎉 抢课成功: {course_name}", f"课程: {course_name}\n教师: {teacher}\n已成功选课！")
        
        # 弹窗提示
        QMessageBox.information(self, "抢课成功", f"🎉 {course_name} 选课成功！")
    
    def on_course_available(self, course_name, teacher, remain, capacity):
        """余课提醒回调"""
        self.log(f"[INFO] 余课提醒: {course_name} 有 {remain} 个空位")
        self.send_wechat_notify(f"📢 余课提醒: {course_name}", f"课程: {course_name}\n空余: {remain}/{capacity}\n正在尝试抢课...")
    
    def start_grab_course(self, course):
        """启动单个课程监控（兼容旧逻辑，用于恢复监控）"""
        # 如果多课程监控线程在运行，添加到队列
        if self.multi_grab_worker and self.multi_grab_worker.isRunning():
            self.multi_grab_worker.add_course(course)
            self.log(f"[INFO] 已添加到监控队列: {course.get('KCM', '')}")
            return
        
        # 获取当前轮次
        selected_round = "1" if self.round_combo.currentIndex() == 0 else "2"
        
        # 否则启动新的多课程监控
        self.multi_grab_worker = MultiGrabWorker(self.driver, [course], self.student_code, self.batch_code, selected_round)
        self.multi_grab_worker.success.connect(self.on_grab_success)
        self.multi_grab_worker.failed.connect(lambda msg: self.log(f"[FAILED] {msg}"))
        self.multi_grab_worker.status.connect(self.log)
        self.multi_grab_worker.need_relogin.connect(self.auto_relogin)
        self.multi_grab_worker.course_available.connect(self.on_course_available)
        self.multi_grab_worker.start()
        self.log(f"[INFO] 开始监控: {course.get('KCM', '')}")
    
    def stop_monitoring(self):
        """停止课程监控（页面数据监控不受影响）"""
        # 停止多课程监控线程
        if self.multi_grab_worker:
            self.multi_grab_worker.stop()
            self.multi_grab_worker = None
        
        # 兼容旧的单课程监控
        for w in self.grab_workers:
            w.stop()
        self.grab_workers.clear()
        
        self.log("[INFO] 已停止课程监控，页面监控继续运行")
    
    def closeEvent(self, event):
        self.stop_monitoring()
        self.refresh_timer.stop()
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        event.accept()

