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
    BASE_URL
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
    
    def _normalize_version(self, version):
        """将版本号标准化为纯数字点号格式（例如 v2.1.0 -> 2.1.0）"""
        if version is None:
            return ''
        return str(version).strip().lstrip('vV')
    
    def run(self):
        try:
            with requests.Session() as session:
                resp = session.get(self.GITHUB_API_URL, timeout=(5, 10))
                
                if resp.status_code == 200:
                    data = resp.json()
                    latest_version = self._normalize_version(data.get('tag_name', ''))
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
            latest = self._normalize_version(latest)
            current = self._normalize_version(current)
            
            def version_tuple(v):
                return tuple(map(int, v.split('.')))
            return version_tuple(latest) > version_tuple(current)
        except:
            return latest != current


class CourseFetchWorker(QThread):
    """后台获取课程列表的 Worker"""
    finished = pyqtSignal(dict, str)  # (courses_grouped, error)
    
    def __init__(self, token, cookies, student_code, batch_code, 
                 course_type_code, internal_type, campus='02', search_keyword=''):
        super().__init__()
        self.token = token
        self.cookies = cookies
        self.student_code = student_code
        self.batch_code = batch_code
        self.course_type_code = course_type_code
        self.internal_type = internal_type
        self.campus = campus  # 校区代码
        self.search_keyword = search_keyword
    
    def run(self):
        try:
            api_endpoint = get_api_endpoint(self.course_type_code)
            
            query_param = {
                "data": {
                    "studentCode": self.student_code,
                    "campus": self.campus,  # 使用传入的校区代码
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
    success = pyqtSignal(str, str, str, str, str, str)  # cookies, token, batch_code, batch_name, student_code, campus
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
    
    def _as_true(self, value):
        """兼容多种布尔字段格式"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return False
    
    def _pick_first_text(self, data, keys):
        """从多个候选键中提取第一个非空字符串"""
        if not isinstance(data, dict):
            return ''
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ''
    
    def _pick_batch_from_item(self, batch_item):
        """从轮次对象中提取 code/name"""
        if not isinstance(batch_item, dict):
            return '', ''
        
        code = self._pick_first_text(
            batch_item, ('code', 'electiveBatchCode', 'batchCode', 'xklcdm')
        )
        name = self._pick_first_text(
            batch_item, ('name', 'electiveBatchName', 'batchName', 'typeName')
        )
        return code, name
    
    def _pick_batch_from_list(self, batch_list):
        """从轮次列表中选择当前可用轮次"""
        if not isinstance(batch_list, list):
            return '', ''
        
        items = [item for item in batch_list if isinstance(item, dict)]
        if not items:
            return '', ''
        
        # 优先：当前可选轮次
        for item in items:
            if self._as_true(item.get('canSelect')):
                code, name = self._pick_batch_from_item(item)
                if code:
                    return code, name
        
        # 次优：当前激活/选中轮次
        for item in items:
            if any(self._as_true(item.get(k)) for k in (
                'isCurrent', 'current', 'selected', 'isSelected', 'checked', 'active'
            )):
                code, name = self._pick_batch_from_item(item)
                if code:
                    return code, name
        
        return '', ''
    
    def _extract_batch_from_payload(self, payload):
        """从返回数据中提取轮次 code/name（兼容多种结构）"""
        if not isinstance(payload, dict):
            return '', ''
        
        # 结构1：直接字段
        direct_code = self._pick_first_text(
            payload, ('electiveBatchCode', 'batchCode', 'xklcdm', 'currentBatchCode')
        )
        direct_name = self._pick_first_text(
            payload, ('electiveBatchName', 'batchName', 'currentBatchName')
        )
        if direct_code:
            return direct_code, direct_name
        
        # 结构2：嵌套对象
        for key in ('electiveBatch', 'currentBatch'):
            batch_obj = payload.get(key)
            code, name = self._pick_batch_from_item(batch_obj)
            if code:
                return code, name
        
        # 结构3：轮次列表
        for key in ('electiveBatchList', 'batchList', 'dataList', 'electiveBatches'):
            code, name = self._pick_batch_from_list(payload.get(key))
            if code:
                return code, name
        
        return '', ''
    
    def _get_student_info(self, cookies, token, student_code):
        """获取学生详细信息，提取校区和轮次"""
        campus = "02"
        batch_code = ''
        batch_name = ''
        
        try:
            session = requests.Session()
            for key, value in cookies.items():
                session.cookies.set(key, value)
            
            timestamp = str(self._get_server_timestamp())
            resp = session.get(
                f"{BASE_URL}/student/{student_code}.do?timestamp={timestamp}",
                headers={
                    "Accept": "*/*",
                    "token": token,
                    "X-Requested-With": "XMLHttpRequest"
                },
                timeout=(3, 8),
                verify=False
            )
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get('code') == '1':
                    data = result.get('data', {})
                    campus = data.get('campus', '02')  # 默认呈贡校区
                    campus_name = data.get('campusName', '未知')
                    batch_code, batch_name = self._extract_batch_from_payload(data)
                    
                    self.status.emit(f"✓ 校区: {campus_name}")
                    if batch_code:
                        if batch_name and batch_name != batch_code:
                            self.status.emit(f"✓ 当前批次: {batch_name} ({batch_code})")
                        else:
                            self.status.emit(f"✓ 当前批次: {batch_code}")
                    return campus, batch_code, batch_name
        except Exception:
            self.status.emit("获取学生信息失败，稍后重试")
        
        return campus, batch_code, batch_name
    
    def _detect_batch_with_retry(
        self, cookies, token, student_code, max_attempts=5, retry_interval=0.6
    ):
        """
        自动识别选课批次（无默认值回退）
        识别顺序：student/{studentCode}.do -> elective/batch.do
        失败则重试，返回 (campus, batch_code, batch_name)
        """
        campus = "02"
        batch_code = ''
        batch_name = ''
        
        for attempt in range(max_attempts):
            self.status.emit(f"识别选课批次 ({attempt + 1}/{max_attempts})...")
            
            campus, batch_code, batch_name = self._get_student_info(
                cookies, token, student_code
            )
            if batch_code:
                return campus, batch_code, batch_name
            
            self.status.emit("学生信息未返回批次，尝试轮次接口识别...")
            batch_code, batch_name = self._get_batch_from_batch_api(cookies, token)
            if batch_code:
                return campus, batch_code, batch_name
            
            if attempt < max_attempts - 1:
                self.status.emit("批次自动识别失败，重试中...")
                time.sleep(retry_interval)
        
        return campus, '', ''
    
    def _get_batch_from_batch_api(self, cookies, token):
        """通过 /elective/batch.do 获取当前可用轮次"""
        try:
            session = requests.Session()
            for key, value in cookies.items():
                session.cookies.set(key, value)
            
            timestamp = str(self._get_server_timestamp())
            resp = session.post(
                f"{BASE_URL}/elective/batch.do?timestamp={timestamp}",
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "token": token,
                    "Referer": f"{BASE_URL}/*default/index.do",
                },
                data={},
                timeout=(3, 8),
                verify=False
            )
            
            if resp.status_code != 200:
                return '', ''
            
            result = resp.json()
            batch_code, batch_name = self._extract_batch_from_payload(result)
            if batch_code:
                if batch_name and batch_name != batch_code:
                    self.status.emit(f"✓ 轮次接口识别: {batch_name} ({batch_code})")
                else:
                    self.status.emit(f"✓ 轮次接口识别: {batch_code}")
            return batch_code, batch_name
        except Exception:
            return '', ''
    
    def _confirm_batch_selection(self, cookies, token, student_code, batch_code):
        """
        确认选课轮次（对应前端 student/xklcqr.do）
        某些轮次需要先确认，否则后续接口可能返回空列表或不可选。
        """
        if not student_code or not batch_code:
            return
        
        try:
            session = requests.Session()
            for key, value in cookies.items():
                session.cookies.set(key, value)
            
            resp = session.post(
                f"{BASE_URL}/student/xklcqr.do",
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "token": token,
                    "Origin": "https://xk.ynu.edu.cn",
                    "Referer": "https://xk.ynu.edu.cn/",
                },
                data={
                    "electiveBatchCode": batch_code,
                    "studentCode": student_code,
                },
                timeout=(3, 8),
                verify=False
            )
            
            if resp.status_code != 200:
                self.status.emit(f"⚠️ 轮次确认 HTTP {resp.status_code}，继续登录")
                return
            
            result = resp.json()
            code = str(result.get('code', ''))
            msg = str(result.get('msg', '') or '')
            
            if code == '1':
                self.status.emit("✓ 轮次确认成功")
            elif msg and any(k in msg for k in ("已确认", "无需确认", "已同意", "已选择")):
                self.status.emit("✓ 轮次已确认")
            elif msg:
                self.status.emit(f"⚠️ 轮次确认返回: {msg}")
        except Exception:
            # 轮次确认失败不阻断登录，后续课程查询仍可能成功
            self.status.emit("⚠️ 轮次确认失败，已继续登录")
    
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
                    student_code = login_data['number']
                    
                    # 自动识别当前批次（失败重试，不再回退默认值）
                    campus, batch_code, batch_name = self._detect_batch_with_retry(
                        login_data['cookies'], token, student_code
                    )
                    
                    if not batch_code:
                        self.failed.emit("批次自动识别失败，请稍后重试登录")
                        return
                    
                    # 与网页端一致：确认当前轮次（第三轮常见必需步骤）
                    self._confirm_batch_selection(
                        login_data['cookies'], token, student_code, batch_code
                    )
                    
                    self.success.emit(
                        cookies_str, token, batch_code, batch_name, student_code, campus
                    )
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
                 campus='02', username='', password='', max_workers=5, serverchan_key=''):
        super().__init__()
        self.student_code = student_code
        self.batch_code = batch_code
        self.token = token
        self.cookies = cookies
        self.campus = campus  # 校区代码
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
        self._login_check_in_progress = False  # 防止登录检测线程重复创建
        
        # 健康检查机制
        self._last_activity_time = time.time()
        self._health_check_interval = 120  # 2分钟检查一次健康状态
        
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
        self._last_activity_time = current_time  # 更新活动时间
        
        # 每 10 次请求或每 5 秒发送一次心跳信号到 UI（减少跨线程通信）
        if count % 10 == 0 or (current_time - self._last_heartbeat_time) >= 5:
            self._last_heartbeat_time = current_time
            try:
                self.heartbeat.emit(count)
            except Exception:
                # 忽略信号发送失败，避免阻塞
                pass
        
        # 每 60 次请求或每 30 秒发送一次保活日志
        if count % 60 == 0 or (current_time - self._last_heartbeat_time) >= 30:
            try:
                self.status.emit(f"[系统] 正在持续监控中... (已检测 {count} 次)")
                self._logger.info(f"心跳: 已检测 {count} 次")
            except Exception:
                # 忽略日志发送失败，避免阻塞
                pass
        
        # 每 60 秒检测一次登录状态（防止线程重复创建）
        if (current_time - self._last_login_check_time) >= 60 and not self._login_check_in_progress:
            self._last_login_check_time = current_time
            self._login_check_in_progress = True
            # 在单独线程中执行登录状态检测，避免阻塞主监控循环
            threading.Thread(target=self._check_login_status_safe, daemon=True).start()
    
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
    
    def _check_login_status_safe(self):
        """安全的登录状态检测 - 带超时和异常处理"""
        try:
            self._check_login_status()
        except Exception as e:
            # 登录状态检测失败不应该影响主监控循环
            self._logger.warning(f"登录状态检测异常: {str(e)[:50]}")
        finally:
            # 重置标志位，允许下次检测
            self._login_check_in_progress = False
    
    def _check_login_status(self):
        """检测登录状态 - 使用已选课程接口"""
        if not self._running:
            return
            
        try:
            self.status.emit("[登录] 正在检测登录状态...")
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
                timeout=(3, 8),  # 增加超时时间，避免卡住
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
            # 不要在这里抛出异常，避免影响主监控循环
    
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
                    "campus": self.campus,  # 使用传入的校区代码
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
                    "campus": self.campus,  # 使用传入的校区代码
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
        1. 优先通过 conflictDesc 严格全名匹配
        2. 其次通过时间比对
        3. 最后兜底：仅剩一门已选课程时返回该课程
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
        
        # 策略1: 通过 conflictDesc 严格全名匹配
        if conflict_desc:
            self._logger.info("尝试通过 conflictDesc 严格全名匹配...")
            normalized_desc = re.sub(r'\s+', '', str(conflict_desc))

            for selected in selected_courses:
                selected_name = str(selected.get('name', '') or '')
                normalized_name = re.sub(r'\s+', '', selected_name)
                if not normalized_name:
                    continue

                # 严格全名匹配：避免“计算机网络”误命中“计算机网络实践”
                pattern = rf'(?<![\u4e00-\u9fffA-Za-z0-9]){re.escape(normalized_name)}(?![\u4e00-\u9fffA-Za-z0-9])'
                if re.search(pattern, normalized_desc):
                    self._logger.info(f"通过 conflictDesc 严格全名匹配: {selected_name}")
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
    
    def _verify_course_selected(self, tc_id, max_attempts=3, retry_interval=0.3):
        """
        带重试的选中核实
        返回:
        - True: 核实已选中
        - False: 明确未选中
        - None: 连续查询失败，无法核实
        """
        has_false = False
        for i in range(max_attempts):
            result = self._check_course_selected(tc_id)
            if result is True:
                return True
            if result is False:
                has_false = True
            if i < max_attempts - 1:
                time.sleep(retry_interval)
        if has_false:
            return False
        return None
    
    def _handle_conflict_rollback(self, course):
        """
        处理时间冲突的自动换课机制 - 亡命回滚版本
        Step 1: 智能定位冲突课程
        Step 2: 退掉冲突的旧课
        Step 3: 抢入目标课程
        Step 4: 核实是否成功
        Step 5: 失败则进入紧急救援模式 - 未成功持续回滚直到成功
        
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
            is_selected = self._verify_course_selected(tc_id)
            
            if is_selected:
                self.status.emit(f"[换课] Step 4: ✓ 换课成功！{conflict_name} → {course_name}")
                self._logger.info(f"换课成功: {conflict_name} → {course_name}")
                return True, conflict_course
            elif is_selected is None:
                # 必须核实成功才视为成功，查询失败时不发成功通知，也不触发回滚
                self.status.emit(f"[换课] Step 4: 核实查询失败，暂不判定成功，继续监控")
                self._logger.warning(f"换课核实失败，暂不判定成功: {course_name}")
                return False, conflict_course
        
        # Step 5: 选课失败，进入紧急救援模式 - 亡命回滚（直到成功）
        self.status.emit(f"[换课] Step 5: 选课失败({msg})，进入紧急救援模式...")
        self._logger.warning(f"选课失败: {course_name}, 原因: {msg}, 开始亡命回滚")
        
        # 紧急救援参数
        RETRY_INTERVAL = 0.7  # 0.7秒间隔（高频但不过分）

        attempt_count = 0

        self.status.emit(f"[紧急救援] 🚨 开始死磕回滚 {conflict_name}，直到成功为止...")
        self._logger.error(f"进入紧急救援模式: 尝试抢回 {conflict_name}")
        
        while self._running:
            attempt_count += 1
            
            # 每10次尝试更新一次状态（减少UI刷新）
            if attempt_count % 10 == 1:
                self.status.emit(
                    f"[紧急救援] 🔄 第{attempt_count}次尝试抢回 {conflict_name}"
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
                is_selected = self._verify_course_selected(conflict_tc_id)
                
                if is_selected is True:
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
            'last_update_time': time.time(),  # 添加最后更新时间
        }
        
        while self._running:
            # 检查课程是否还在列表中
            courses_snapshot = self._get_courses_snapshot()
            if not any(c.get('JXBID') == tc_id for c in courses_snapshot):
                break
            
            # 查询余量
            remain, capacity, course_info = self._api_query_course_capacity(course)
            
            # 心跳：每次查询后增加计数并更新状态时间
            self._increment_request_count()
            
            # 更新课程状态的最后活动时间
            if tc_id in self._course_states:
                self._course_states[tc_id]['last_update_time'] = time.time()
            
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
                    is_selected = self._verify_course_selected(tc_id)
                    if is_selected is True:
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
                        if is_selected is None:
                            self.status.emit(f"[WARN] 选课返回成功但核实查询失败，暂不发送成功通知，继续监控...")
                        else:
                            self.status.emit(f"[WARN] 选课返回成功但核实未选中，继续监控...")
                
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
        
        # 启动健康检查线程
        health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        health_thread.start()
        
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
            
            # 定期清理已结束的线程引用，防止列表无限增长
            threads = [t for t in threads if t.is_alive()]
            
            time.sleep(0.5)
        
        # 等待所有线程结束
        self._running = False
        for t in threads:
            t.join(timeout=2)
        
        # 停止日志由 UI 统一输出，避免重复“监控已停止”
    
    def _health_check_loop(self):
        """
        增强版健康检查循环 - 多层检测 + 自动恢复
        检测指标：
        1. 活动时间检测（2分钟无活动报警，5分钟启动恢复）
        2. 线程状态检测（检测是否有死锁线程）
        3. 网络连接检测（检测是否有连接泄漏）
        4. 内存使用检测（检测是否有内存泄漏）
        """
        consecutive_warnings = 0  # 连续警告次数
        last_request_count = 0    # 上次的请求计数
        recovery_attempts = 0     # 恢复尝试次数
        max_recovery_attempts = 3 # 最大恢复尝试次数
        
        while self._running:
            try:
                time.sleep(self._health_check_interval)  # 120秒检查间隔
                
                if not self._running:
                    break
                
                current_time = time.time()
                inactive_duration = current_time - self._last_activity_time
                
                # 获取当前请求计数
                with self._request_count_lock:
                    current_request_count = self._request_count
                
                # ========== 第1层：活动时间检测 ==========
                if inactive_duration > 120:  # 2分钟无活动开始警告
                    consecutive_warnings += 1
                    
                    if inactive_duration < 300:  # 2-5分钟：警告阶段
                        self.status.emit(
                            f"[健康检查] ⚠️ 监控活动减少，已 {int(inactive_duration/60)} 分钟无活动 "
                            f"(警告 {consecutive_warnings}/3)"
                        )
                        self._logger.warning(f"健康检查: 监控活动减少 {int(inactive_duration)} 秒")
                    
                    elif inactive_duration >= 300:  # 5分钟以上：启动恢复
                        if recovery_attempts < max_recovery_attempts:
                            recovery_attempts += 1
                            self.status.emit(
                                f"[健康检查] 🚨 监控可能卡死！启动自动恢复 (尝试 {recovery_attempts}/{max_recovery_attempts})"
                            )
                            self._logger.error(f"健康检查: 启动自动恢复，无活动 {int(inactive_duration)} 秒")
                            
                            # 执行自动恢复
                            recovery_success = self._attempt_auto_recovery()
                            
                            if recovery_success:
                                self.status.emit("[健康检查] ✅ 自动恢复成功，监控已重启")
                                self._logger.info("健康检查: 自动恢复成功")
                                consecutive_warnings = 0
                                recovery_attempts = 0
                                self._last_activity_time = current_time
                            else:
                                self.status.emit(f"[健康检查] ❌ 自动恢复失败 (尝试 {recovery_attempts}/{max_recovery_attempts})")
                                
                                # 达到最大尝试次数，建议用户手动重启
                                if recovery_attempts >= max_recovery_attempts:
                                    self.status.emit(
                                        "[健康检查] 🆘 自动恢复失败，建议手动停止并重启监控"
                                    )
                                    self._logger.error("健康检查: 自动恢复失败，建议手动重启")
                                    # 发送需要重登信号，让UI处理
                                    self.need_relogin.emit()
                                    break
                        else:
                            # 已达最大尝试次数，等待用户干预
                            if consecutive_warnings % 5 == 0:  # 每5次提醒一次，避免刷屏
                                self.status.emit("[健康检查] 🆘 监控已卡死，请手动重启程序")
                else:
                    # 活动正常，重置计数器
                    if consecutive_warnings > 0:
                        self.status.emit("[健康检查] ✅ 监控活动已恢复正常")
                        consecutive_warnings = 0
                        recovery_attempts = 0
                
                # ========== 第2层：请求计数检测 ==========
                # 检测请求计数是否在增长（防止假活动）
                if current_request_count == last_request_count and inactive_duration > 180:
                    self.status.emit(
                        f"[健康检查] ⚠️ 请求计数未增长，可能存在死循环 "
                        f"(计数: {current_request_count})"
                    )
                    self._logger.warning(f"健康检查: 请求计数停滞 {current_request_count}")
                
                last_request_count = current_request_count
                
                # ========== 第3层：课程状态检测 ==========
                # 检测是否有课程监控线程卡死
                courses_snapshot = self._get_courses_snapshot()
                active_courses = len(self._course_states)
                expected_courses = len(courses_snapshot)
                
                if expected_courses > 0 and active_courses < expected_courses:
                    missing_courses = expected_courses - active_courses
                    self.status.emit(
                        f"[健康检查] ⚠️ 检测到 {missing_courses} 门课程监控线程可能已停止"
                    )
                    self._logger.warning(f"健康检查: 缺失监控线程 {missing_courses} 个")
                
                # ========== 第4层：定期健康报告 ==========
                # 每10分钟报告一次健康状态
                if int(current_time) % 600 == 0:  # 10分钟整点
                    self.status.emit(
                        f"[健康检查] 📊 状态正常 | 活跃课程: {active_courses} | "
                        f"总请求: {current_request_count} | 运行时长: {int((current_time - self._last_activity_time)/60)}分钟"
                    )
                
            except Exception as e:
                self._logger.error(f"健康检查异常: {str(e)[:50]}")
                time.sleep(60)  # 异常后等待1分钟再继续
    
    def _attempt_auto_recovery(self):
        """
        自动恢复机制
        尝试多种方式恢复监控状态
        返回: True=恢复成功, False=恢复失败
        """
        try:
            self.status.emit("[自动恢复] 🔧 开始诊断和修复...")
            
            # 步骤1: 检查网络连接
            self.status.emit("[自动恢复] Step 1: 检查网络连接...")
            if not self._test_network_connectivity():
                self.status.emit("[自动恢复] ❌ 网络连接异常，无法恢复")
                return False
            
            # 步骤2: 检查登录状态
            self.status.emit("[自动恢复] Step 2: 检查登录状态...")
            if not self._test_login_status():
                self.status.emit("[自动恢复] 🔄 登录状态异常，尝试重新登录...")
                if not self._handle_session_expired():
                    self.status.emit("[自动恢复] ❌ 重新登录失败")
                    return False
                self.status.emit("[自动恢复] ✅ 重新登录成功")
            
            # 步骤3: 重置监控状态
            self.status.emit("[自动恢复] Step 3: 重置监控状态...")
            self._reset_monitoring_state()
            
            # 步骤4: 测试课程查询
            self.status.emit("[自动恢复] Step 4: 测试课程查询...")
            courses_snapshot = self._get_courses_snapshot()
            if courses_snapshot:
                test_course = courses_snapshot[0]
                remain, capacity, _ = self._api_query_course_capacity(test_course)
                if remain is not None or remain == 'session_expired':
                    self.status.emit("[自动恢复] ✅ 课程查询测试通过")
                    return True
                else:
                    self.status.emit("[自动恢复] ❌ 课程查询测试失败")
                    return False
            else:
                self.status.emit("[自动恢复] ⚠️ 无待监控课程，恢复完成")
                return True
            
        except Exception as e:
            self.status.emit(f"[自动恢复] ❌ 恢复过程异常: {str(e)[:50]}")
            self._logger.error(f"自动恢复异常: {str(e)}")
            return False
    
    def _test_network_connectivity(self):
        """测试网络连接"""
        try:
            import socket
            socket.create_connection(("xk.ynu.edu.cn", 443), timeout=5)
            return True
        except:
            return False
    
    def _test_login_status(self):
        """快速测试登录状态"""
        try:
            timestamp = str(int(time.time() * 1000))
            url = f"{BASE_URL}/elective/courseResult.do"
            
            resp = self.http_session.get(
                url,
                headers=self._get_headers(),
                cookies=self._parse_cookies(self.cookies),
                params={"timestamp": timestamp, "studentCode": self.student_code, "electiveBatchCode": self.batch_code},
                timeout=(3, 5),
                verify=False
            )
            
            return resp.status_code == 200 and not self._is_session_expired(response=resp)
        except:
            return False
    
    def _reset_monitoring_state(self):
        """重置监控状态"""
        try:
            # 重置活动时间
            self._last_activity_time = time.time()
            
            # 清理可能卡死的课程状态
            dead_courses = []
            current_time = time.time()
            
            for tc_id, state in self._course_states.items():
                # 如果某个课程状态超过10分钟没更新，认为可能卡死
                last_update = state.get('last_update_time', current_time)
                if current_time - last_update > 600:  # 10分钟
                    dead_courses.append(tc_id)
            
            # 清理卡死的课程状态，让它们重新启动监控
            for tc_id in dead_courses:
                if tc_id in self._course_states:
                    del self._course_states[tc_id]
                    self._logger.info(f"清理可能卡死的课程状态: {tc_id}")
            
            if dead_courses:
                self.status.emit(f"[自动恢复] 🧹 清理了 {len(dead_courses)} 个可能卡死的监控状态")
            
        except Exception as e:
            self._logger.error(f"重置监控状态异常: {str(e)}")
            raise
