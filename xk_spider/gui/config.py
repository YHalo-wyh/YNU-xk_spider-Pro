"""
配置与常量模块
存放所有全局常量和纯逻辑辅助函数
"""

# ========== 课程类型映射 ==========
# 内部类型标识 -> 服务器代码
COURSE_TYPE_MAP = {
    'public': 'XGXK',       # 通识教育选修课程
    'recommend': 'TJKC',    # 推荐课程
    'major': 'FANKC',       # 主修课程（服务器代码保持 FANKC）
    'sport': 'TYKC',        # 体育课程
}

# 服务器代码 -> API 端点
API_ENDPOINT_MAP = {
    'TJKC': 'recommendedCourse.do',
    'FANKC': 'programCourse.do',
    'XGXK': 'publicCourse.do',
    'TYKC': 'programCourse.do',
}

# UI 显示名称 -> 服务器代码
COURSE_TYPES = {
    '推荐课程': 'TJKC',
    '主修课程': 'FANKC',
    '通识教育选修课程': 'XGXK',
    '体育课程': 'TYKC',
}

# UI 显示名称 -> 内部类型标识
COURSE_NAME_TO_TYPE = {
    '推荐课程': 'recommend',
    '主修课程': 'major',
    '通识教育选修课程': 'public',
    '体育课程': 'sport',
}

# 默认批次代码
DEFAULT_BATCH_CODE = "3d7ef3d38d4440a09b1ae65d3d7a04bc"

# API 基础 URL
BASE_URL = "https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp"

# 监控状态文件路径（用于闪退恢复）
MONITOR_STATE_FILE = "xk_spider/monitor_state.json"


def get_api_endpoint(course_type):
    """获取课程类型对应的 API 端点"""
    code = COURSE_TYPE_MAP.get(course_type, course_type)
    return API_ENDPOINT_MAP.get(code, 'recommendedCourse.do')


def get_course_type_code(internal_type):
    """获取内部类型标识对应的课程类型代码"""
    if internal_type in API_ENDPOINT_MAP:
        return internal_type
    return COURSE_TYPE_MAP.get(internal_type, 'TJKC')


def parse_int(value, default=0):
    """安全解析整数"""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        import re
        match = re.search(r'\d+', value)
        if match:
            return int(match.group())
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
