"""
业务逻辑核心模块 - Workers
高并发非阻塞架构：每门课程独立监控线程
"""
import json
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from .config import (
    get_api_endpoint, get_course_type_code,
    DEFAULT_BATCH_CODE, BASE_URL
)
from .utils import create_ocr_instance, OCR_AVAILABLE, send_notification
from .logger import get_logger


# ========== 状态解析工具 ==========
def parse_bool_field(value):
    """解析 API 返回的布尔字段（可能是 "0"/"1"/True/False/None）"""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value == "1" or value.lower() == "true"
    if isinstance(value, int):
        return value == 1
    return False


def parse_int_field(value, default=0):
    """安全解析整数字段"""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


class UpdateCheckWorker(QThread):
    """后台检查更新的 Worker"""
    finished = pyqtSignal(bool, str, str, str)  # (has_update, latest_version, download_url, error)
    
    GITHUB_API_URL = "https://api.github.com/repos/YHalo-wyh/YNU-xk_spider-Pro/releases/latest"
    
    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version
    
    def run(self):
        try:
            with requests.Session() as session:
                resp = session.get(self.GITHUB_API_URL, timeout=(5, 10))
                
                if resp.status_code == 200:
                    data = resp.json()
                    latest_version = data.get('tag_name', '').lstrip('v')
                    download_url = data.get('html_url', '')
                    release_notes = data.get('body', '')[:500]
                    
                    if not latest_version:
                        self.finished.emit(False, '', '', '无法获取版本号')
                        return
                    
                    # 版本比较
                    has_update = self._compare_versions(latest_version, self.current_version)
                    self.finished.emit(has_update, latest_version, download_url, '')
                    
                elif resp.status_code == 404:
                    self.finished.emit(False, '', '', '暂无发布版本')
                else:
                    self.finished.emit(False, '', '', f'HTTP {resp.status_code}')
                    
        except requests.exceptions.Timeout:
            self.finished.emit(False, '', '', '请求超时')
        except Exception as e:
            self.finished.emit(False, '', '', f'网络错误: {str(e)[:50]}')
    
    def _compare_versions(self, latest, current):
        """比较版本号，返回 True 表示有更新"""
        try:
            def version_tuple(v):
                return tuple(map(int, v.split('.')))
            return version_tuple(latest) > version_tuple(current)
        except:
            return latest != current


class CourseFetchWorker(QThread):
    """后台获取课程列表的 Worker"""
    finished = pyqtSignal(dict, str)  # (courses_grouped, error)
    
    def __init__(self, token, cookies, student_code, batch_code, 
                 course_type_code, internal_type, search_keyword=''):
        super().__init__()
        self.token = token
        self.cookies = cookies
        self.student_code = student_code
        self.batch_code = batch_code
        self.course_type_code = course_type_code
        self.internal_type = internal_type
        self.search_keyword = search_keyword
    
    def run(self):
        try:
            api_endpoint = get_api_endpoint(self.course_type_code)
            
            query_param = {
                "data": {
                    "studentCode": self.student_code,
                    "campus": "02",
                    "electiveBatchCode": self.batch_code,
                    "isMajor": "1",
                    "teachingClassType": self.course_type_code,
                    "checkConflict": "2",
                    "checkCapacity": "2",
                    "queryContent": self.search_keyword
                },
                "pageSize": "500",
                "pageNumber": "0",
                "order": ""
            }
            
            url = f"{BASE_URL}/elective/{api_endpoint}"
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "token": self.token,
                "Origin": "https://xk.ynu.edu.cn",
                "Referer": f"{BASE_URL}/*default/grablessons.do?token={self.token}",
            }
            
            cookie_dict = self._parse_cookies(self.cookies)
            data = {"querySetting": json.dumps(query_param, ensure_ascii=False)}
            
            # 使用 Session 上下文管理器确保连接正确释放
            with requests.Session() as session:
                resp = session.post(url, headers=headers, cookies=cookie_dict, 
                                   data=data, timeout=(3, 10), verify=False)
                
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get('code') == '1' or 'dataList' in result:
                        courses_grouped = self._parse_course_list(result.get('dataList', []))
                        self.finished.emit(courses_grouped, '')
                    else:
                        self.finished.emit({}, result.get('msg', '未知错误'))
                else:
                    self.finished.emit({}, f"HTTP {resp.status_code}")
        except Exception as e:
            self.finished.emit({}, str(e)[:50])
    
    def _parse_cookies(self, cookies_str):
        cookie_dict = {}
        for item in cookies_str.split('; '):
            if '=' in item:
                k, v = item.split('=', 1)
                cookie_dict[k] = v
        return cookie_dict
    
    def _parse_course_list(self, data_list):
        """解析课程列表，正确处理状态字段"""
        courses_grouped = {}
        
        for item in data_list:
            course_name = item.get('courseName') or item.get('KCM') or item.get('KCMC', '')
            course_number = item.get('courseNumber') or item.get('KCH', '')
            tc_list = item.get('tcList', [])
            
            if tc_list:
                if course_name not in courses_grouped:
                    courses_grouped[course_name] = []
                for tc in tc_list:
                    courses_grouped[course_name].append(
                        self._extract_course_info(tc, course_name, course_number))
            else:
                tc_id = item.get('teachingClassID') or item.get('JXBID', '')
                if tc_id:
                    if course_name not in courses_grouped:
                        courses_grouped[course_name] = []
                    courses_grouped[course_name].append(
                        self._extract_course_info(item, course_name, course_number))
        
        return courses_grouped
    
    def _extract_course_info(self, tc, course_name, course_number):
        """提取教学班信息，正确解析状态字段"""
        # 状态字段可能是 "0"/"1" 字符串
        is_full = parse_bool_field(tc.get('isFull'))
        is_conflict = parse_bool_field(tc.get('isConflict'))
        is_chosen = parse_bool_field(tc.get('isChoose') or tc.get('isChosen'))
        
        # 提取教师名和体育项目名
        teacher_name = tc.get('teacherName') or tc.get('SKJS', '')
        sport_name = tc.get('sportName', '')  # 体育课程特有字段
        
        # 如果有体育项目名，拼接到教师名后面
        if sport_name:
            display_teacher = f"{teacher_name} -- {sport_name}"
        else:
            display_teacher = teacher_name
        
        return {
            'JXBID': tc.get('teachingClassID') or tc.get('JXBID', ''),
            'KCM': course_name,
            'SKJS': display_teacher,  # 教师名 + 体育项目名
            'SKJS_RAW': teacher_name,  # 保留原始教师名（用于日志等）
            'SPORT_NAME': sport_name,  # 保留体育项目名（用于后续处理）
            'SKSJ': tc.get('teachingPlace') or tc.get('classTime') or tc.get('SKSJ', ''),
            'KRL': parse_int_field(tc.get('classCapacity') or tc.get('KRL')),
            'YXRS': parse_int_field(tc.get('numberOfFirstVolunteer') or tc.get('YXRS')),
            'type': self.internal_type,
            'number': course_number,
            'isConflict': is_conflict,
            'isChosen': is_chosen,
            'isFull': is_full,
            'conflictDesc': tc.get('conflictDesc', ''),
        }


class LoginWorker(QThread):
    """纯API登录线程"""
    success = pyqtSignal(str, str, str, str)  # cookies, token, batch_code, student_code
    failed = pyqtSignal(str)
    status = pyqtSignal(str)
    
    def __init__(self, username, password):
        super().__init__()
        self.username = username
        self.password = password
        self.ocr = None
        self._server_time_offset = 0
        
        if OCR_AVAILABLE:
            self.ocr = create_ocr_instance()
    
    def _get_server_timestamp(self):
        return int(time.time() * 1000) + self._server_time_offset
    
    def _sync_server_time(self):
        try:
            local_before = int(time.time() * 1000)
            resp = requests.head(f"{BASE_URL}/*default/index.do", timeout=(2, 3), verify=False)
            local_after = int(time.time() * 1000)
            server_date = resp.headers.get('Date')
            if server_date:
                from email.utils import parsedate_to_datetime
                server_time = int(parsedate_to_datetime(server_date).timestamp() * 1000)
                local_mid = (local_before + local_after) // 2
                self._server_time_offset = server_time - local_mid
        except:
            self._server_time_offset = 0
    
    def _api_login_attempt(self):
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"{BASE_URL}/*default/index.do",
                "X-Requested-With": "XMLHttpRequest"
            })
            
            self.status.emit("访问首页获取Cookie...")
            resp = session.get(f"{BASE_URL}/*default/index.do", timeout=(5, 10), verify=False)
            
            if resp.status_code != 200:
                return None, f"访问首页失败:{resp.status_code}"
            
            if 'JSESSIONID' not in session.cookies.get_dict():
                return None, "未获取到JSESSIONID"
            
            timestamp = str(self._get_server_timestamp())
            resp = session.get(f"{BASE_URL}/student/4/vcode.do?timestamp={timestamp}",
                             headers={"Accept": "application/json"}, timeout=(3, 8), verify=False)
            
            if resp.status_code != 200:
                return None, f"获取vtoken失败:{resp.status_code}"
            
            try:
                vtoken = resp.json().get('data', {}).get('token', '')
                if not vtoken:
                    return None, "vtoken为空"
            except:
                return None, "解析vtoken失败"
            
            resp_img = session.get(f"{BASE_URL}/student/vcode/image.do?vtoken={vtoken}",
                                  timeout=(3, 8), verify=False)
            
            if resp_img.status_code != 200 or len(resp_img.content) < 100:
                return None, "下载验证码失败"
            
            if not self.ocr:
                return None, "OCR未初始化"
            
            captcha_code = self.ocr.classification(resp_img.content)
            if not captcha_code:
                return None, "验证码识别失败"
            
            captcha_code = ''.join(c for c in captcha_code if c.isalnum() and ord(c) < 128)[:4]
            if len(captcha_code) < 4:
                return None, f"验证码格式错误:{captcha_code}"
            
            self.status.emit(f"OCR识别: {captcha_code}")
            
            login_params = {
                "timestrap": str(self._get_server_timestamp()),
                "loginName": self.username,
                "loginPwd": self.password,
                "verifyCode": captcha_code,
                "vtoken": vtoken
            }
            
            login_resp = session.get(f"{BASE_URL}/student/check/login.do",
                                    params=login_params, timeout=(3, 8), verify=False)
            
            if login_resp.status_code != 200:
                return None, f"登录请求失败:{login_resp.status_code}"
            
            result = login_resp.json()
            msg = result.get('msg', '')
            
            if result.get('code') == '1':
                data = result.get('data', {})
                return {
                    'token': data.get('token', ''),
                    'number': data.get('number', '') or data.get('studentCode', '') or self.username,
                    'name': data.get('name', '') or data.get('studentName', ''),
                    'cookies': session.cookies.get_dict(),
                }, "success"
            else:
                if '验证码' in msg:
                    return None, "captcha_error"
                elif '密码' in msg or '用户名' in msg or '账号' in msg:
                    return None, f"login_error:{msg}"
                return None, f"error:{msg}"
            
        except requests.exceptions.Timeout:
            return None, "请求超时"
        except Exception as e:
            return None, f"exception:{str(e)[:50]}"
    
    def run(self):
        self.status.emit("同步服务器时间...")
        self._sync_server_time()
        
        max_attempts = 10
        for attempt in range(max_attempts):
            self.status.emit(f"尝试登录 ({attempt + 1}/{max_attempts})...")
            
            login_data, result = self._api_login_attempt()
            
            if result == "success" and login_data:
                token = login_data.get('token', '')
                if token:
                    self.status.emit(f"✓ 登录成功！{login_data.get('name', '')}")
                    cookies_str = '; '.join([f"{k}={v}" for k, v in login_data['cookies'].items()])
                    self.success.emit(cookies_str, token, DEFAULT_BATCH_CODE, login_data['number'])
                    return
                continue
                    
            elif result == "captcha_error":
                self.status.emit("验证码错误，重试...")
                time.sleep(0.2)
                continue
            elif result and result.startswith("login_error:"):
                self.failed.emit(f"登录失败：{result[12:]}\n\n请检查学号和密码是否正确。")
                return
            else:
                self.status.emit(f"{result}，重试...")
                continue
        
        self.failed.emit("登录失败，请检查网络或稍后重试")


class MultiGrabWorker(QThread):
    """
    高并发非阻塞抢课 Worker
    每门课程独立监控线程，互不阻塞
    """
    # 信号定义
    success = pyqtSignal(str, dict)       # (消息, 课程数据)
    failed = pyqtSignal(str)              # 错误消息
    status = pyqtSignal(str)              # 状态消息
    need_relogin = pyqtSignal()           # 需要重新登录
    course_available = pyqtSignal(str, str, int, int)  # (课程名, 教师, 余量, 容量)
    session_updated = pyqtSignal(str, str)  # (token, cookies)
    heartbeat = pyqtSignal(int)           # 心跳信号 (总请求次数)
    login_status = pyqtSignal(bool, str)  # 登录状态信号 (是否在线, 状态描述)
    
    def __init__(self, courses, student_code, batch_code, token, cookies,
                 username='', password='', max_workers=5, serverchan_key=''):
        super().__init__()
        self.student_code = student_code
        self.batch_code = batch_code
        self.token = token
        self.cookies = cookies
        self.username = username
        self.password = password
        self.max_workers = max_workers
        self.serverchan_key = serverchan_key  # Server酱 SendKey
        
        # 线程安全：课程列表保护
        self._courses_mutex = QMutex()
        self._courses = list(courses)  # 深拷贝
        
        # 控制标志
        self._running = True
        self._relogin_in_progress = False
        self._relogin_mutex = QMutex()  # 重登互斥锁
        self._relogin_failed_permanently = False  # 永久失败标志（密码错误等）
        
        # 每门课程的状态追踪（减少日志噪音）
        self._course_states = {}  # tc_id -> {'last_remain': int, 'last_status': str}
        
        # 心跳计数器（线程安全）
        self._request_count = 0
        self._request_count_lock = threading.Lock()
        self._last_heartbeat_time = time.time()
        self._last_login_check_time = 0  # 初始化为0，启动后立即检测一次
        
        # 初始化 HTTP Session（大连接池）
        self.http_session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=Retry(
                total=2,
                backoff_factor=0.1,
                status_forcelist=[500, 502, 503, 504]
            )
        )
        self.http_session.mount('https://', adapter)
        self.http_session.mount('http://', adapter)
        self.http_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://xk.ynu.edu.cn",
        })
        
        # OCR 实例（用于自动重登）
        self.ocr = None
        if OCR_AVAILABLE:
            self.ocr = create_ocr_instance()
        
        # 日志
        self._logger = get_logger()
    
    def _increment_request_count(self):
        """线程安全地增加请求计数并发送心跳"""
        with self._request_count_lock:
            self._request_count += 1
            count = self._request_count
        
        current_time = time.time()
        
        # 每 10 次请求或每 5 秒发送一次心跳信号到 UI（减少跨线程通信）
        if count % 10 == 0 or (current_time - self._last_heartbeat_time) >= 5:
            self.heartbeat.emit(count)
        
        # 每 60 次请求或每 30 秒发送一次保活日志
        if count % 60 == 0 or (current_time - self._last_heartbeat_time) >= 30:
            self._last_heartbeat_time = current_time
            self.status.emit(f"[系统] 正在持续监控中... (已检测 {count} 次)")
            self._logger.info(f"心跳: 已检测 {count} 次")
        
        # 每 60 秒检测一次登录状态
        if (current_time - self._last_login_check_time) >= 60:
            self._last_login_check_time = current_time
            self._check_login_status()
    
    def add_course(self, course):
        """线程安全地添加课程"""
        self._courses_mutex.lock()
        try:
            tc_id = course.get('JXBID', '')
            if not any(c.get('JXBID') == tc_id for c in self._courses):
                self._courses.append(course)
        finally:
            self._courses_mutex.unlock()
    
    def remove_course(self, tc_id):
        """线程安全地移除课程"""
        self._courses_mutex.lock()
        try:
            self._courses = [c for c in self._courses if c.get('JXBID') != tc_id]
        finally:
            self._courses_mutex.unlock()
    
    def _get_courses_snapshot(self):
        """获取课程列表快照"""
        self._courses_mutex.lock()
        try:
            return list(self._courses)
        finally:
            self._courses_mutex.unlock()
    
    def _remove_course_safe(self, tc_id):
        """从内部列表安全移除课程"""
        self._courses_mutex.lock()
        try:
            self._courses = [c for c in self._courses if c.get('JXBID') != tc_id]
        finally:
            self._courses_mutex.unlock()
    
    def stop(self):
        """停止所有监控"""
        self._running = False
    
    def _parse_cookies(self, cookies_str):
        """解析 Cookie 字符串为字典"""
        cookie_dict = {}
        if not cookies_str:
            return cookie_dict
        for item in cookies_str.split('; '):
            if '=' in item:
                k, v = item.split('=', 1)
                cookie_dict[k] = v
        return cookie_dict
    
    def _check_login_status(self):
        """检测登录状态 - 使用已选课程接口"""
        self.status.emit("[登录] 正在检测登录状态...")
        try:
            # 使用已选课程接口检测登录状态
            timestamp = str(int(time.time() * 1000))
            url = f"{BASE_URL}/elective/courseResult.do"
            
            params = {
                "timestamp": timestamp,
                "studentCode": self.student_code,
                "electiveBatchCode": self.batch_code,
            }
            
            resp = self.http_session.get(
                url,
                headers=self._get_headers(),
                cookies=self._parse_cookies(self.cookies),
                params=params,
                timeout=(5, 10),
                verify=False,
                allow_redirects=False
            )
            
            # 检查 302 跳转（Session 过期）
            if resp.status_code == 302:
                self.login_status.emit(False, "Session 已过期")
                self.status.emit("[登录] ⚠️ Session 已过期，需要重新登录")
                self._handle_session_expired()
                return
            
            if resp.status_code == 200:
                result = resp.json()
                # 检查响应内容是否表示过期
                if self._is_session_expired(result=result):
                    self.login_status.emit(False, "Session 已过期")
                    self.status.emit("[登录] ⚠️ Session 已过期，需要重新登录")
                    self._handle_session_expired()
                else:
                    self.login_status.emit(True, "在线")
                    self.status.emit("[登录] ✅ 登录状态正常")
            else:
                # 非 200 状态码，可能是服务器问题或登录过期
                self.login_status.emit(False, f"HTTP {resp.status_code}")
                self.status.emit(f"[登录] ⚠️ 异常状态 HTTP {resp.status_code}，尝试重登...")
                self._handle_session_expired()
                
        except requests.exceptions.Timeout:
            self.login_status.emit(False, "网络超时")
            self.status.emit("[登录] ⚠️ 网络超时，稍后重试")
        except Exception as e:
            self.login_status.emit(False, f"检测失败")
            self.status.emit(f"[登录] ❌ 检测异常: {str(e)[:50]}")
    
    def _get_headers(self):
        """获取请求头"""
        return {
            "token": self.token,
            "Referer": f"{BASE_URL}/*default/grablessons.do?token={self.token}",
        }
    
    def _is_session_expired(self, response=None, result=None, msg=''):
        """
        判断 Session 是否过期
        支持多种检测方式：HTTP 状态码、响应内容、错误消息
        """
        # 检查 HTTP 302 跳转
        if response is not None:
            if response.status_code == 302:
                return True
            # 检查是否被重定向到登录页
            if response.history and any(r.status_code == 302 for r in response.history):
                return True
        
        # 检查响应结果
        if result is not None:
            code = result.get('code', '')
            result_msg = result.get('msg', '')
            
            if code == '-1':
                return True
            
            # 关键词检测
            expired_keywords = ['登录', 'token', '过期', '失效', 'invalid', 'expired', 
                              '未登录', '会话', 'session', '认证', '授权']
            for keyword in expired_keywords:
                if keyword.lower() in result_msg.lower():
                    return True
        
        # 检查错误消息
        if msg:
            expired_keywords = ['登录', 'token', '过期', '失效', 'invalid', 'expired',
                              '未登录', 'session_expired']
            for keyword in expired_keywords:
                if keyword.lower() in msg.lower():
                    return True
        
        return False
    
    def _handle_session_expired(self):
        """
        处理 Session 过期（线程安全）
        返回: True 表示恢复成功，False 表示需要通知 UI
        """
        # 如果已经永久失败（密码错误等），直接返回
        if self._relogin_failed_permanently:
            return False
        
        # 尝试获取锁
        if not self._relogin_mutex.tryLock():
            # 其他线程正在重登，等待完成
            self.status.emit("[自动重登] 等待其他线程完成重登...")
            max_wait = 30  # 最多等待30秒
            waited = 0
            while waited < max_wait:
                time.sleep(0.5)
                waited += 0.5
                # 尝试获取锁检查是否完成
                if self._relogin_mutex.tryLock():
                    self._relogin_mutex.unlock()
                    break
            
            # 检查重登是否成功（通过 token 是否更新判断）
            if self.token and not self._relogin_failed_permanently:
                return True
            return False
        
        try:
            # 再次检查是否已经永久失败
            if self._relogin_failed_permanently:
                return False
            
            # 检查是否正在重登（双重检查）
            if self._relogin_in_progress:
                return self.token != ''
            
            self._relogin_in_progress = True
            self.status.emit("[自动重登] Session已过期，正在后台恢复...")
            
            # 执行重登，最多3次
            max_relogin_attempts = 3
            for attempt in range(max_relogin_attempts):
                if not self._running:
                    return False
                
                self.status.emit(f"[自动重登] 尝试 {attempt + 1}/{max_relogin_attempts}...")
                success, new_token, new_cookies = self._do_relogin()
                
                if success:
                    self.status.emit("[自动重登] ✓ 恢复成功")
                    return True
                
                # 如果是密码错误等致命错误，标记永久失败
                if self._relogin_failed_permanently:
                    return False
                
                time.sleep(0.5)
            
            self.status.emit("[自动重登] 恢复失败，已达最大尝试次数")
            return False
            
        finally:
            self._relogin_in_progress = False
            self._relogin_mutex.unlock()
    
    def _api_query_course_capacity(self, course, retry_on_expired=True):
        """
        查询课程余量
        返回: (remain, capacity, course_info) 或 (None, None, None) 表示查询失败
        特殊返回: ('session_expired', None, None) 表示需要重登且重登失败
        """
        tc_id = course.get('JXBID', '')
        course_type = course.get('type', 'recommend')
        course_number = course.get('number', '')
        course_name = course.get('KCM', '')
        
        # 优先使用课程号查询，更精确
        query_content = course_number if course_number else course_name
        
        try:
            api_endpoint = get_api_endpoint(course_type)
            course_type_code = get_course_type_code(course_type)
            
            query_param = {
                "data": {
                    "studentCode": self.student_code,
                    "campus": "02",
                    "electiveBatchCode": self.batch_code,
                    "isMajor": "1",
                    "teachingClassType": course_type_code,
                    "checkConflict": "2",
                    "checkCapacity": "2",
                    "queryContent": query_content
                },
                "pageSize": "500",  # 大分页防止截断
                "pageNumber": "0",
                "order": ""
            }
            
            url = f"{BASE_URL}/elective/{api_endpoint}"
            data = {"querySetting": json.dumps(query_param, ensure_ascii=False)}
            
            resp = self.http_session.post(
                url,
                headers=self._get_headers(),
                cookies=self._parse_cookies(self.cookies),
                data=data,
                timeout=(3, 5),
                verify=False,
                allow_redirects=False  # 禁止自动重定向，便于检测302
            )
            
            # 检查 302 跳转
            if resp.status_code == 302 or self._is_session_expired(response=resp):
                if retry_on_expired:
                    if self._handle_session_expired():
                        # 重登成功，立即重试
                        return self._api_query_course_capacity(course, retry_on_expired=False)
                return 'session_expired', None, None
            
            if resp.status_code != 200:
                return None, None, None
            
            result = resp.json()
            
            # 检查 Session 过期
            if self._is_session_expired(result=result):
                if retry_on_expired:
                    if self._handle_session_expired():
                        return self._api_query_course_capacity(course, retry_on_expired=False)
                return 'session_expired', None, None
            
            data_list = result.get('dataList', [])
            
            # 在返回列表中查找目标教学班
            for item in data_list:
                tc_list = item.get('tcList', [])
                if tc_list:
                    for tc in tc_list:
                        if tc.get('teachingClassID') == tc_id or tc.get('JXBID') == tc_id:
                            capacity = parse_int_field(tc.get('classCapacity') or tc.get('KRL'))
                            selected = parse_int_field(tc.get('numberOfFirstVolunteer') or tc.get('YXRS'))
                            remain = capacity - selected
                            
                            # 正确解析状态字段
                            tc['isFull'] = parse_bool_field(tc.get('isFull'))
                            tc['isConflict'] = parse_bool_field(tc.get('isConflict'))
                            tc['isChoose'] = parse_bool_field(tc.get('isChoose') or tc.get('isChosen'))
                            
                            return remain, capacity, tc
                else:
                    # 单层结构
                    item_tc_id = item.get('teachingClassID') or item.get('JXBID', '')
                    if item_tc_id == tc_id:
                        capacity = parse_int_field(item.get('classCapacity') or item.get('KRL'))
                        selected = parse_int_field(item.get('numberOfFirstVolunteer') or item.get('YXRS'))
                        remain = capacity - selected
                        
                        item['isFull'] = parse_bool_field(item.get('isFull'))
                        item['isConflict'] = parse_bool_field(item.get('isConflict'))
                        item['isChoose'] = parse_bool_field(item.get('isChoose') or item.get('isChosen'))
                        
                        return remain, capacity, item
            
            # 未找到目标课程（可能被过滤），返回 None 触发盲抢
            return None, None, None
            
        except requests.exceptions.Timeout:
            return None, None, None
        except Exception:
            return None, None, None

    def _api_select_course_fast(self, course, retry_on_expired=True):
        """
        快速选课 API
        POST /elective/volunteer.do
        参数: addParam={"data": {...}}
        返回: (success: bool, msg: str, need_rollback: bool)
        
        修复: 正确处理 course_type 为数字字符串的情况
        """
        tc_id = course.get('JXBID', '')
        course_type = course.get('type', 'recommend')
        
        # 修复: 处理 course_type 为数字字符串的情况（直接使用，不查字典）
        if isinstance(course_type, str) and course_type.isdigit():
            course_type_code = course_type
        else:
            course_type_code = get_course_type_code(course_type)
        
        try:
            url = f"{BASE_URL}/elective/volunteer.do"
            
            # 正确的参数结构: addParam={"data": {...}}
            add_param = {
                "data": {
                    "operationType": "1",
                    "studentCode": self.student_code,
                    "electiveBatchCode": self.batch_code,
                    "teachingClassId": tc_id,
                    "teachingClassType": course_type_code,
                    "isMajor": "1",
                    "campus": "02",
                }
            }
            
            payload = {
                "addParam": json.dumps(add_param, ensure_ascii=False)
            }
            
            self._logger.info(f"选课请求: tc_id={tc_id}, type={course_type_code}")
            
            resp = self.http_session.post(
                url,
                headers=self._get_headers(),
                cookies=self._parse_cookies(self.cookies),
                data=payload,
                timeout=(3, 5),
                verify=False,
                allow_redirects=False
            )
            
            # 检查 302 跳转
            if resp.status_code == 302 or self._is_session_expired(response=resp):
                if retry_on_expired:
                    if self._handle_session_expired():
                        return self._api_select_course_fast(course, retry_on_expired=False)
                return False, "session_expired", False
            
            if resp.status_code != 200:
                self._logger.error(f"选课失败: HTTP {resp.status_code}")
                return False, f"HTTP {resp.status_code}", False
            
            result = resp.json()
            self._logger.info(f"选课响应: {json.dumps(result, ensure_ascii=False)}")
            
            code = result.get('code', '')
            msg = result.get('msg', '')
            
            # 检查 Session 过期
            if self._is_session_expired(result=result, msg=msg):
                if retry_on_expired:
                    if self._handle_session_expired():
                        return self._api_select_course_fast(course, retry_on_expired=False)
                return False, "session_expired", False
            
            if code == '1':
                self._logger.info(f"选课成功: {tc_id}")
                return True, "选课成功", False
            elif '已选' in msg or '重复' in msg:
                return True, "课程已选中", False
            elif '冲突' in msg:
                self._logger.warning(f"选课冲突: {msg}")
                return False, f"时间冲突: {msg}", True  # 需要回滚
            elif '容量' in msg or '已满' in msg or '人数' in msg:
                return False, "课程已满", False
            else:
                self._logger.warning(f"选课失败: {msg}")
                return False, msg or "选课失败", False
                
        except requests.exceptions.Timeout:
            return False, "请求超时", False
        except Exception as e:
            self._logger.error(f"选课异常: {e}")
            return False, str(e)[:50], False
    
    def _api_delete_course(self, tc_id, course_type='recommend', retry_on_expired=True):
        """
        退课 API
        GET /elective/deleteVolunteer.do?timestamp=xxx&deleteParam={JSON}
        返回: (success: bool, msg: str)
        """
        try:
            timestamp = str(int(time.time() * 1000))
            url = f"{BASE_URL}/elective/deleteVolunteer.do"
            
            # 构建 deleteParam JSON
            delete_param = {
                "data": {
                    "operationType": "2",
                    "studentCode": self.student_code,
                    "electiveBatchCode": self.batch_code,
                    "teachingClassId": tc_id,
                    "isMajor": "1",
                }
            }
            
            params = {
                "timestamp": timestamp,
                "deleteParam": json.dumps(delete_param, ensure_ascii=False),
            }
            
            self._logger.info(f"退课请求: tc_id={tc_id}, params={params}")
            
            resp = self.http_session.get(
                url,
                params=params,
                headers=self._get_headers(),
                cookies=self._parse_cookies(self.cookies),
                timeout=(3, 5),
                verify=False,
                allow_redirects=False
            )
            
            # 检查 302 跳转
            if resp.status_code == 302 or self._is_session_expired(response=resp):
                if retry_on_expired:
                    if self._handle_session_expired():
                        return self._api_delete_course(tc_id, course_type, retry_on_expired=False)
                return False, "session_expired"
            
            if resp.status_code != 200:
                self._logger.error(f"退课失败: HTTP {resp.status_code}")
                return False, f"HTTP {resp.status_code}"
            
            result = resp.json()
            self._logger.info(f"退课响应: {json.dumps(result, ensure_ascii=False)}")
            
            code = result.get('code', '')
            msg = result.get('msg', '')
            
            # 检查 Session 过期
            if self._is_session_expired(result=result, msg=msg):
                if retry_on_expired:
                    if self._handle_session_expired():
                        return self._api_delete_course(tc_id, course_type, retry_on_expired=False)
                return False, "session_expired"
            
            if code == '1':
                self._logger.info(f"退课成功: {tc_id}")
                return True, "退课成功"
            else:
                self._logger.warning(f"退课失败: {msg}")
                return False, msg or "退课失败"
                
        except Exception as e:
            self._logger.error(f"退课异常: {e}")
            return False, str(e)[:50]
    
    def _api_get_selected_courses(self):
        """
        获取已选课程列表
        GET /elective/courseResult.do?timestamp=xxx&studentCode=xxx&electiveBatchCode=xxx
        返回: list of tc_id 或 None
        """
        try:
            timestamp = str(int(time.time() * 1000))
            url = f"{BASE_URL}/elective/courseResult.do"
            
            params = {
                "timestamp": timestamp,
                "studentCode": self.student_code,
                "electiveBatchCode": self.batch_code,
            }
            
            resp = self.http_session.get(
                url,
                params=params,
                headers=self._get_headers(),
                cookies=self._parse_cookies(self.cookies),
                timeout=(3, 5),
                verify=False
            )
            
            if resp.status_code != 200:
                self._logger.warning(f"获取已选课程失败: HTTP {resp.status_code}")
                return None
            
            result = resp.json()
            if result.get('code') == '-1':
                return None
            
            selected_ids = []
            data_list = result.get('dataList', []) or result.get('data', [])
            for item in data_list:
                tc_id = item.get('teachingClassID') or item.get('JXBID', '') or item.get('tcId', '')
                if tc_id:
                    selected_ids.append(tc_id)
            
            return selected_ids
            
        except Exception as e:
            self._logger.error(f"获取已选课程异常: {e}")
            return None
    
    def _api_get_selected_courses_details(self):
        """
        获取已选课程详情列表（包含时间信息）
        GET /elective/courseResult.do
        返回: [{'id': tc_id, 'name': name, 'time': time_str, 'type': type}] 或 None
        """
        try:
            timestamp = str(int(time.time() * 1000))
            url = f"{BASE_URL}/elective/courseResult.do"
            
            params = {
                "timestamp": timestamp,
                "studentCode": self.student_code,
                "electiveBatchCode": self.batch_code,
            }
            
            resp = self.http_session.get(
                url,
                params=params,
                headers=self._get_headers(),
                cookies=self._parse_cookies(self.cookies),
                timeout=(3, 5),
                verify=False
            )
            
            if resp.status_code != 200:
                self._logger.warning(f"获取已选课程详情失败: HTTP {resp.status_code}")
                return None
            
            result = resp.json()
            self._logger.info(f"已选课程响应: {json.dumps(result, ensure_ascii=False)[:500]}")
            
            if result.get('code') == '-1':
                return None
            
            selected_courses = []
            data_list = result.get('dataList', []) or result.get('data', [])
            for item in data_list:
                tc_id = item.get('teachingClassID') or item.get('JXBID', '') or item.get('tcId', '')
                if tc_id:
                    selected_courses.append({
                        'id': tc_id,
                        'name': item.get('courseName') or item.get('KCM') or item.get('KCMC', ''),
                        'time': item.get('classTime') or item.get('SKSJ') or item.get('teachingPlace', '') or item.get('time', ''),
                        'type': item.get('teachingClassType') or item.get('type', 'recommend'),
                        'teacher': item.get('teacherName') or item.get('SKJS', ''),
                    })
            
            self._logger.info(f"解析到 {len(selected_courses)} 门已选课程")
            return selected_courses
            
        except Exception as e:
            self._logger.error(f"获取已选课程详情异常: {e}")
            return None
    
    def _parse_time_slots(self, time_str):
        """
        解析教务系统时间格式
        输入: "1-18周 星期二 5-6节" 或 "1-18周 星期二 第5-6节" 或 "1-9周 星期一 1-2节, 11-18周 星期一 1-2节"
        输出: [{'weeks': set, 'day': int, 'periods': set}, ...]
        
        修复: 支持 "第5-6节" 和 "第5节" 格式
        """
        if not time_str:
            self._logger.debug(f"时间字符串为空")
            return []
        
        self._logger.debug(f"解析时间: {time_str}")
        
        slots = []
        # 按逗号、分号、斜杠分割多个时间段
        segments = re.split(r'[,;，；/]', time_str)
        
        day_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7,
            '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
        }
        
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            
            slot = {'weeks': set(), 'day': 0, 'periods': set()}
            
            # 解析周次: "1-18周" 或 "1-17周(单)" 或 "2-18周(双)" 或 "第1-18周"
            week_match = re.search(r'第?(\d+)-(\d+)周(?:\(([单双])\))?', segment)
            if week_match:
                start_week = int(week_match.group(1))
                end_week = int(week_match.group(2))
                odd_even = week_match.group(3)  # 单/双/None
                
                for w in range(start_week, end_week + 1):
                    if odd_even == '单' and w % 2 == 0:
                        continue
                    if odd_even == '双' and w % 2 == 1:
                        continue
                    slot['weeks'].add(w)
            else:
                # 尝试匹配单周: "第5周" 或 "5周"
                single_week = re.search(r'第?(\d+)周', segment)
                if single_week:
                    slot['weeks'].add(int(single_week.group(1)))
            
            # 解析星期: "星期二" 或 "周二" 或 "礼拜二"
            day_match = re.search(r'(?:星期|周|礼拜)([一二三四五六日天1-7])', segment)
            if day_match:
                day_char = day_match.group(1)
                slot['day'] = day_map.get(day_char, 0)
            
            # 解析节次: "5-6节" 或 "第5-6节" 或 "5,6节" 或 "第5节"
            # 修复: 正确处理"第"字前缀
            # 先尝试范围格式: "第5-6节" 或 "5-6节"
            period_match = re.search(r'第?(\d+)-(\d+)节', segment)
            if period_match:
                start_period = int(period_match.group(1))
                end_period = int(period_match.group(2))
                for p in range(start_period, end_period + 1):
                    slot['periods'].add(p)
            else:
                # 尝试单节格式: "第5节" 或 "5节"
                period_singles = re.findall(r'第(\d+)节', segment)
                if period_singles:
                    for p in period_singles:
                        slot['periods'].add(int(p))
                else:
                    # 尝试不带"第"字的格式: "5节" 或 "5,6节"
                    period_singles = re.findall(r'(\d+)节', segment)
                    for p in period_singles:
                        slot['periods'].add(int(p))
                    # 也尝试匹配逗号分隔: "5,6节"
                    comma_periods = re.search(r'(\d+(?:,\d+)+)节', segment)
                    if comma_periods:
                        for p in comma_periods.group(1).split(','):
                            if p.strip():
                                slot['periods'].add(int(p.strip()))
            
            # 只有解析出有效数据才添加
            if slot['weeks'] and slot['day'] and slot['periods']:
                self._logger.debug(f"解析成功: weeks={slot['weeks']}, day={slot['day']}, periods={slot['periods']}")
                slots.append(slot)
            elif slot['day'] and slot['periods']:
                # 如果没有周次信息，假设是全周
                slot['weeks'] = set(range(1, 19))
                self._logger.debug(f"解析成功(默认全周): day={slot['day']}, periods={slot['periods']}")
                slots.append(slot)
        
        if not slots:
            self._logger.warning(f"时间解析失败: {time_str}")
        
        return slots
    
    def _check_time_conflict(self, time_str1, time_str2):
        """
        检查两个时间字符串是否存在冲突
        返回: True 表示有冲突，False 表示无冲突
        """
        slots1 = self._parse_time_slots(time_str1)
        slots2 = self._parse_time_slots(time_str2)
        
        self._logger.debug(f"比对时间冲突: '{time_str1}' vs '{time_str2}'")
        self._logger.debug(f"slots1={len(slots1)}, slots2={len(slots2)}")
        
        if not slots1 or not slots2:
            self._logger.debug("无法解析时间，跳过时间比对")
            return False  # 无法解析时默认无冲突
        
        for s1 in slots1:
            for s2 in slots2:
                # 检查星期是否相同
                if s1['day'] != s2['day']:
                    continue
                
                # 检查周次是否有交集
                common_weeks = s1['weeks'] & s2['weeks']
                if not common_weeks:
                    continue
                
                # 检查节次是否有交集
                common_periods = s1['periods'] & s2['periods']
                if common_periods:
                    self._logger.info(f"发现时间冲突: day={s1['day']}, weeks={common_weeks}, periods={common_periods}")
                    return True  # 存在冲突
        
        return False
    
    def _find_conflict_course(self, target_course):
        """
        在已选课程中查找与目标课程时间冲突的课程
        策略：
        1. 优先通过 conflictDesc 文本匹配（最可靠）
        2. 其次通过时间比对
        3. 最后通过课程名模糊匹配
        返回: {'id': tc_id, 'name': name, ...} 或 None
        """
        target_name = target_course.get('KCM', '')
        target_time = target_course.get('SKSJ', '') or target_course.get('classTime', '')
        conflict_desc = target_course.get('conflictDesc', '')
        
        self._logger.info(f"查找冲突课程: target={target_name}, time={target_time}")
        self._logger.info(f"conflictDesc: {conflict_desc}")
        
        selected_courses = self._api_get_selected_courses_details()
        if not selected_courses:
            self._logger.warning("获取已选课程列表失败")
            return None
        
        self._logger.info(f"已选课程数量: {len(selected_courses)}")
        for sc in selected_courses:
            self._logger.debug(f"  - {sc['name']}: {sc['time']}")
        
        # 策略1: 通过 conflictDesc 文本匹配（最可靠）
        if conflict_desc:
            self._logger.info("尝试通过 conflictDesc 匹配...")
            
            # 提取方括号中的内容 [课程名][班号]
            bracket_matches = re.findall(r'\[([^\]]+)\]', conflict_desc)
            self._logger.debug(f"conflictDesc 提取: {bracket_matches}")
            
            for selected in selected_courses:
                selected_name = selected.get('name', '')
                
                # 检查课程名是否出现在 conflictDesc 中
                if selected_name and selected_name in conflict_desc:
                    self._logger.info(f"通过 conflictDesc 直接匹配: {selected_name}")
                    return selected
                
                # 检查方括号内容是否匹配
                for match in bracket_matches:
                    if match and selected_name and (match in selected_name or selected_name in match):
                        self._logger.info(f"通过 conflictDesc 方括号匹配: {selected_name} ~ {match}")
                        return selected
            
            # 尝试更宽松的匹配：取课程名前几个字
            for selected in selected_courses:
                selected_name = selected.get('name', '')
                if selected_name and len(selected_name) >= 2:
                    # 取前4个字符进行模糊匹配
                    prefix = selected_name[:4]
                    if prefix in conflict_desc:
                        self._logger.info(f"通过 conflictDesc 前缀匹配: {selected_name} (prefix={prefix})")
                        return selected
        
        # 策略2: 通过时间比对
        if target_time:
            self._logger.info("尝试通过时间比对匹配...")
            for selected in selected_courses:
                selected_time = selected.get('time', '')
                if selected_time and self._check_time_conflict(target_time, selected_time):
                    self._logger.info(f"通过时间比对发现冲突: {selected['name']}")
                    return selected
        
        # 策略3: 如果只有一门已选课程，直接返回（大概率就是它）
        if len(selected_courses) == 1:
            self._logger.info(f"只有一门已选课程，假定为冲突课程: {selected_courses[0]['name']}")
            return selected_courses[0]
        
        self._logger.warning(f"无法定位冲突课程")
        return None
    
    def _check_course_selected(self, tc_id):
        """检查课程是否已选中"""
        selected = self._api_get_selected_courses()
        if selected is None:
            return None  # 查询失败
        return tc_id in selected
    
    def _handle_conflict_rollback(self, course):
        """
        处理时间冲突的自动换课机制 - 亡命回滚版本
        Step 1: 智能定位冲突课程
        Step 2: 退掉冲突的旧课
        Step 3: 抢入目标课程
        Step 4: 核实是否成功
        Step 5: 失败则进入紧急救援模式 - 持续5分钟死磕回滚
        
        返回: (success: bool, conflict_course_info: dict or None)
        """
        tc_id = course.get('JXBID', '')
        course_name = course.get('KCM', '')
        course_type = course.get('type', 'recommend')
        target_time = course.get('SKSJ', '') or course.get('classTime', '')
        
        self.status.emit(f"[换课] 开始处理时间冲突: {course_name}")
        self._logger.info(f"开始换课流程: {course_name}, 时间: {target_time}")
        
        # Step 1: 智能定位冲突课程
        self.status.emit(f"[换课] Step 1: 定位冲突课程...")
        conflict_course = self._find_conflict_course(course)
        
        if not conflict_course:
            self.status.emit(f"[换课] 无法定位冲突课程，请手动处理")
            self._logger.warning(f"无法定位冲突课程: {course_name}")
            return False, None
        
        conflict_tc_id = conflict_course['id']
        conflict_name = conflict_course['name']
        conflict_type = conflict_course.get('type', course_type)
        
        self.status.emit(f"[换课] 发现冲突: {conflict_name}")
        self._logger.info(f"冲突课程: {conflict_name} (ID: {conflict_tc_id})")
        
        # Step 2: 退掉冲突的旧课
        self.status.emit(f"[换课] Step 2: 退选 {conflict_name}...")
        success, msg = self._api_delete_course(conflict_tc_id, conflict_type)
        
        if not success:
            self.status.emit(f"[换课] 退课失败: {msg}")
            self._logger.error(f"退课失败: {conflict_name}, 原因: {msg}")
            return False, conflict_course
        
        self._logger.info(f"退课成功: {conflict_name}")
        time.sleep(0.3)
        
        # Step 3: 抢入目标课程
        self.status.emit(f"[换课] Step 3: 选课 {course_name}...")
        success, msg, _ = self._api_select_course_fast(course)
        
        if success:
            # Step 4: 核实
            time.sleep(0.5)
            is_selected = self._check_course_selected(tc_id)
            
            if is_selected:
                self.status.emit(f"[换课] Step 4: ✓ 换课成功！{conflict_name} → {course_name}")
                self._logger.info(f"换课成功: {conflict_name} → {course_name}")
                return True, conflict_course
            elif is_selected is None:
                # 查询失败，但选课返回成功，认为成功
                self.status.emit(f"[换课] Step 4: 选课成功（核实查询失败）")
                self._logger.info(f"换课可能成功: {course_name}")
                return True, conflict_course
        
        # Step 5: 选课失败，进入紧急救援模式 - 亡命回滚
        self.status.emit(f"[换课] Step 5: 选课失败({msg})，进入紧急救援模式...")
        self._logger.warning(f"选课失败: {course_name}, 原因: {msg}, 开始亡命回滚")
        
        # 紧急救援参数
        DESPERATE_RECOVERY_DURATION = 300  # 5分钟 = 300秒
        RETRY_INTERVAL = 0.7  # 0.7秒间隔（高频但不过分）
        
        rollback_start_time = time.time()
        attempt_count = 0
        
        self.status.emit(f"[紧急救援] 🚨 开始死磕回滚 {conflict_name}，持续5分钟...")
        self._logger.error(f"进入紧急救援模式: 尝试抢回 {conflict_name}")
        
        while self._running:
            elapsed = time.time() - rollback_start_time
            
            # 超时检查
            if elapsed >= DESPERATE_RECOVERY_DURATION:
                self.status.emit(f"[紧急救援] ⚠️ 超时5分钟，停止回滚。请手动检查 {conflict_name}")
                self._logger.error(f"紧急救援超时: {conflict_name}, 尝试次数: {attempt_count}")
                return False, conflict_course
            
            attempt_count += 1
            remaining = int(DESPERATE_RECOVERY_DURATION - elapsed)
            
            # 每10次尝试更新一次状态（减少UI刷新）
            if attempt_count % 10 == 1:
                self.status.emit(
                    f"[紧急救援] 🔄 第{attempt_count}次尝试抢回 {conflict_name} "
                    f"(剩余{remaining}秒)"
                )
            
            # 尝试选回旧课
            rollback_success, rollback_msg, _ = self._api_select_course_fast({
                'JXBID': conflict_tc_id, 
                'type': conflict_type
            })
            
            # 心跳维持（防止UI假死）
            self._increment_request_count()
            
            if rollback_success:
                # 核实是否真的选上了
                time.sleep(0.3)
                is_selected = self._check_course_selected(conflict_tc_id)
                
                if is_selected or is_selected is None:
                    self.status.emit(f"[紧急救援] ✓ 成功抢回 {conflict_name}！(尝试{attempt_count}次)")
                    self._logger.info(f"紧急救援成功: {conflict_name}, 尝试次数: {attempt_count}")
                    return False, conflict_course
            
            # 检查是否因为"已选"而失败（说明已经抢回了）
            if rollback_msg and ('已选' in rollback_msg or '重复' in rollback_msg):
                self.status.emit(f"[紧急救援] ✓ {conflict_name} 已在课表中！")
                self._logger.info(f"紧急救援成功(已选): {conflict_name}")
                return False, conflict_course
            
            # 短暂休眠后继续
            time.sleep(RETRY_INTERVAL)
        
        # 被外部停止
        self.status.emit(f"[紧急救援] 监控已停止，请手动检查 {conflict_name}")
        self._logger.warning(f"紧急救援被中断: {conflict_name}")
        return False, conflict_course

    def _do_relogin(self):
        """
        执行单次重登尝试（内部方法）
        返回: (success: bool, token: str, cookies: str)
        """
        if not self.username or not self.password:
            self.status.emit("[自动重登] 缺少用户名或密码")
            self._relogin_failed_permanently = True
            return False, '', ''
        
        if not self.ocr:
            self.status.emit("[自动重登] OCR未初始化")
            self._relogin_failed_permanently = True
            return False, '', ''
        
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"{BASE_URL}/*default/index.do",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # 内部重试（主要针对验证码识别错误）
        max_captcha_retries = 5
        for captcha_attempt in range(max_captcha_retries):
            if not self._running:
                return False, '', ''
            
            try:
                # 获取首页
                resp = session.get(f"{BASE_URL}/*default/index.do", timeout=(3, 8), verify=False)
                if resp.status_code != 200:
                    continue
                
                # 获取 vtoken
                timestamp = str(int(time.time() * 1000))
                resp = session.get(
                    f"{BASE_URL}/student/4/vcode.do?timestamp={timestamp}",
                    headers={"Accept": "application/json"},
                    timeout=(3, 5),
                    verify=False
                )
                
                if resp.status_code != 200:
                    continue
                
                vtoken = resp.json().get('data', {}).get('token', '')
                if not vtoken:
                    continue
                
                # 获取验证码图片
                resp_img = session.get(
                    f"{BASE_URL}/student/vcode/image.do?vtoken={vtoken}",
                    timeout=(3, 8),
                    verify=False
                )
                
                if resp_img.status_code != 200 or len(resp_img.content) < 100:
                    continue
                
                # OCR 识别
                captcha_code = self.ocr.classification(resp_img.content)
                if not captcha_code:
                    continue
                
                captcha_code = ''.join(c for c in captcha_code if c.isalnum() and ord(c) < 128)[:4]
                if len(captcha_code) < 4:
                    continue
                
                # 登录
                login_params = {
                    "timestrap": str(int(time.time() * 1000)),
                    "loginName": self.username,
                    "loginPwd": self.password,
                    "verifyCode": captcha_code,
                    "vtoken": vtoken
                }
                
                login_resp = session.get(
                    f"{BASE_URL}/student/check/login.do",
                    params=login_params,
                    timeout=(3, 5),
                    verify=False
                )
                
                if login_resp.status_code != 200:
                    continue
                
                result = login_resp.json()
                
                if result.get('code') == '1':
                    data = result.get('data', {})
                    new_token = data.get('token', '')
                    new_cookies = '; '.join([f"{k}={v}" for k, v in session.cookies.get_dict().items()])
                    
                    if new_token:
                        self.token = new_token
                        self.cookies = new_cookies
                        self.session_updated.emit(new_token, new_cookies)
                        return True, new_token, new_cookies
                
                # 验证码错误，重试
                msg = result.get('msg', '')
                if '验证码' in msg:
                    time.sleep(0.2)
                    continue
                
                # 密码错误等致命错误
                if '密码' in msg or '用户名' in msg or '账号' in msg:
                    self.status.emit(f"[自动重登] 账号密码错误: {msg}")
                    self._relogin_failed_permanently = True
                    return False, '', ''
                
            except Exception as e:
                time.sleep(0.3)
                continue
        
        return False, '', ''
    
    def _api_relogin(self):
        """
        自动重登（线程安全封装）
        返回: (success: bool, token: str, cookies: str)
        """
        success = self._handle_session_expired()
        return success, self.token, self.cookies
    
    def _monitor_course_loop(self, course):
        """
        单门课程的独立监控循环 - 安全优先版本
        每门课程在自己的线程中独立运行，互不阻塞
        
        核心安全策略:
        1. 彻底删除盲抢逻辑 - 查询失败时直接跳过
        2. 最高优先级检查 isFull 字段 - 防止幽灵余量
        3. 仅当 isFull=False 且 remain>0 时才允许抢课
        """
        tc_id = course.get('JXBID', '')
        course_name = course.get('KCM', '')
        teacher = course.get('SKJS', '')
        
        # 初始化状态追踪
        self._course_states[tc_id] = {
            'last_remain': -999,
            'last_status': '',
        }
        
        while self._running:
            # 检查课程是否还在列表中
            courses_snapshot = self._get_courses_snapshot()
            if not any(c.get('JXBID') == tc_id for c in courses_snapshot):
                break
            
            # 查询余量
            remain, capacity, course_info = self._api_query_course_capacity(course)
            
            # 心跳：每次查询后增加计数
            self._increment_request_count()
            
            # Session 过期处理（已在 _api_query_course_capacity 内部自动重试）
            if remain == 'session_expired':
                # 自动重登已失败，通知 UI
                self.need_relogin.emit()
                break
            
            state = self._course_states.get(tc_id, {})
            
            # ========== 安全策略 1: 彻底删除盲抢逻辑 ==========
            # 查询失败 (remain is None) - 直接跳过，绝不盲抢
            if remain is None:
                if state.get('last_status') != 'query_failed':
                    self.status.emit(f"[SKIP] {course_name} 查询失败，跳过本次循环（安全模式）")
                    self._logger.warning(f"查询失败，跳过: {course_name}")
                    state['last_status'] = 'query_failed'
                
                # 休眠后继续下次查询
                time.sleep(1.5)
                continue
            
            # 成功查询到余量，打印状态日志
            is_full_flag = course_info.get('isFull', False) if course_info else False
            status_mark = "满" if is_full_flag or remain <= 0 else "有余量"
            self.status.emit(f"[查询] {course_name} 余量: {remain}/{capacity} ({status_mark})")
            
            # 状态变化检测（减少日志噪音）
            last_remain = state.get('last_remain', -999)
            
            # 检查是否已选
            if course_info and course_info.get('isChoose'):
                if state.get('last_status') != 'chosen':
                    self.status.emit(f"[INFO] {course_name} 已选中")
                    state['last_status'] = 'chosen'
                self._remove_course_safe(tc_id)
                break
            
            # ========== 安全策略 2: 最高优先级检查 isFull ==========
            # 必须首先检查 isFull 字段（系统标记）
            is_full_flag = course_info.get('isFull', False) if course_info else False
            
            # 幽灵余量防御：即使计算出 remain > 0，但 isFull=True 时，绝对禁止抢课
            if is_full_flag:
                if remain > 0:
                    # 发现幽灵余量！
                    if state.get('last_status') != 'ghost_capacity':
                        self.status.emit(
                            f"[GHOST] {course_name} 显示余量{remain}但isFull=True，"
                            f"跳过以防误退课（幽灵余量）"
                        )
                        self._logger.warning(
                            f"幽灵余量检测: {course_name}, remain={remain}, isFull=True"
                        )
                        state['last_status'] = 'ghost_capacity'
                else:
                    # 正常的已满状态
                    if last_remain > 0 or (last_remain == -999 and state.get('last_status') != 'full'):
                        state['last_status'] = 'full'
                
                state['last_remain'] = remain
                time.sleep(1.0)
                continue
            
            # ========== 安全策略 3: 行动条件 - isFull=False 且 remain>0 ==========
            if remain > 0:
                # 通过安全检查！可以进入抢课流程
                if last_remain <= 0 or state.get('last_status') != 'available':
                    self.status.emit(
                        f"[ALERT] 🎉 {course_name} 发现余量！余={remain}/{capacity} "
                        f"(isFull=False, 安全)"
                    )
                    self.course_available.emit(course_name, teacher, remain, capacity)
                    state['last_status'] = 'available'
                    
                    # Server酱通知：发现余量
                    if self.serverchan_key:
                        send_notification(
                            self.serverchan_key,
                            f"🎯 发现余量: {course_name}",
                            f"**课程**: {course_name}\n\n**教师**: {teacher}\n\n**余量**: {remain}/{capacity}\n\n正在尝试抢课..."
                        )
                
                state['last_remain'] = remain
                
                # ========== 主动出击策略 ==========
                # 检查查询结果中是否已标记冲突（isConflict）
                is_conflict_from_query = course_info and course_info.get('isConflict', False)
                
                if is_conflict_from_query:
                    # 查询已告知冲突，直接启动换课流程，不浪费请求
                    self.status.emit(f"[CONFLICT] {course_name} 检测到时间冲突，主动启动换课...")
                    self._logger.info(f"主动换课: {course_name}, isConflict=True from query")
                    
                    # 更新课程的 conflictDesc（从查询结果获取）
                    if course_info.get('conflictDesc'):
                        course['conflictDesc'] = course_info.get('conflictDesc')
                    
                    swap_success, conflict_info = self._handle_conflict_rollback(course)
                    
                    if swap_success:
                        conflict_name = conflict_info.get('name', '未知') if conflict_info else '未知'
                        self.success.emit(
                            f"🔄 换课成功: {conflict_name} → {course_name} - {teacher}", 
                            course
                        )
                        # Server酱通知：换课成功
                        if self.serverchan_key:
                            send_notification(
                                self.serverchan_key,
                                f"🎉 换课成功: {course_name}",
                                f"**新课程**: {course_name}\n\n**教师**: {teacher}\n\n**方式**: 换课成功\n\n**原课程**: {conflict_name}"
                            )
                        self._remove_course_safe(tc_id)
                        break
                    else:
                        self.status.emit(f"[CONFLICT] 换课失败，等待下次余量...")
                        time.sleep(2.0)
                        continue
                
                # 无冲突标记，直接尝试选课
                self.status.emit(f"[GRAB] 尝试选课: {course_name}...")
                success, msg, need_rollback = self._api_select_course_fast(course)
                
                self._logger.info(f"选课结果: {course_name}, success={success}, msg={msg}, need_rollback={need_rollback}")
                
                if success:
                    # 核实
                    time.sleep(0.3)
                    if self._check_course_selected(tc_id) is not False:
                        self.success.emit(f"🎉 抢课成功: {course_name} - {teacher}", course)
                        # Server酱通知：抢课成功
                        if self.serverchan_key:
                            send_notification(
                                self.serverchan_key,
                                f"🎉 抢课成功: {course_name}",
                                f"**课程**: {course_name}\n\n**教师**: {teacher}\n\n**方式**: 正常抢课"
                            )
                        self._remove_course_safe(tc_id)
                        break
                    else:
                        self.status.emit(f"[WARN] 选课返回成功但核实失败，继续监控...")
                
                elif msg == "session_expired":
                    self.need_relogin.emit()
                    break
                
                elif need_rollback:
                    # 服务器返回冲突（备用路径）
                    self.status.emit(f"[CONFLICT] {course_name} 服务器返回冲突，启动换课...")
                    state['last_status'] = 'conflict'
                    
                    swap_success, conflict_info = self._handle_conflict_rollback(course)
                    
                    if swap_success:
                        conflict_name = conflict_info.get('name', '未知') if conflict_info else '未知'
                        self.success.emit(
                            f"🔄 换课成功: {conflict_name} → {course_name} - {teacher}", 
                            course
                        )
                        # Server酱通知：换课成功（服务器返回冲突路径）
                        if self.serverchan_key:
                            send_notification(
                                self.serverchan_key,
                                f"🎉 换课成功: {course_name}",
                                f"**新课程**: {course_name}\n\n**教师**: {teacher}\n\n**方式**: 换课成功\n\n**原课程**: {conflict_name}"
                            )
                        self._remove_course_safe(tc_id)
                        break
                    else:
                        self.status.emit(f"[CONFLICT] 换课失败，等待下次余量...")
                        time.sleep(2.0)
                        continue
                
                else:
                    # 其他失败原因（已满、其他错误）
                    self.status.emit(f"[FAIL] {course_name} 选课失败: {msg}")
                
                # 快速重试
                time.sleep(0.3)
                continue
            
            else:
                # 无余量
                if last_remain > 0 or (last_remain == -999 and state.get('last_status') != 'full'):
                    # 状态从有余量变为无余量，或首次检测
                    state['last_status'] = 'full'
                
                state['last_remain'] = remain
            
            # 正常轮询间隔
            time.sleep(1.0)
        
        # 清理状态
        if tc_id in self._course_states:
            del self._course_states[tc_id]
    
    def run(self):
        """
        主运行方法
        为每门课程启动独立的监控线程，非阻塞
        """
        courses = self._get_courses_snapshot()
        
        if not courses:
            self.status.emit("[INFO] 没有待抢课程")
            return
        
        self.status.emit(f"[INFO] 启动监控: {len(courses)} 门课程")
        
        # 为每门课程创建独立监控线程
        threads = []
        for course in courses:
            t = threading.Thread(
                target=self._monitor_course_loop,
                args=(course,),
                daemon=True
            )
            t.start()
            threads.append(t)
        
        # 主线程等待所有监控线程结束或被停止
        while self._running:
            # 检查是否还有课程在监控
            if not self._get_courses_snapshot():
                self.status.emit("[INFO] 所有课程已处理完毕")
                break
            
            # 检查是否有新添加的课程需要启动监控
            current_courses = self._get_courses_snapshot()
            monitored_ids = set(self._course_states.keys())
            
            for course in current_courses:
                tc_id = course.get('JXBID', '')
                if tc_id and tc_id not in monitored_ids:
                    # 新课程，启动监控
                    t = threading.Thread(
                        target=self._monitor_course_loop,
                        args=(course,),
                        daemon=True
                    )
                    t.start()
                    threads.append(t)
            
            time.sleep(0.5)
        
        # 等待所有线程结束
        self._running = False
        for t in threads:
            t.join(timeout=2)
        
        self.status.emit("[INFO] 监控已停止")
