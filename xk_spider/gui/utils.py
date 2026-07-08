"""
工具与补丁模块
环境检查、SSL修复、OCR检测、Server酱通知推送
"""
import os
import threading
import copy
import requests
import urllib.parse

# ========== SSL 证书修复 ==========
def fix_ssl_cert():
    """修复 PyInstaller 打包后 SSL 证书问题"""
    try:
        import certifi
        os.environ['SSL_CERT_FILE'] = certifi.where()
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    except ImportError:
        pass


# 初始化时执行 SSL 修复
fix_ssl_cert()


# ========== PIL 兼容性补丁 ==========
def fix_pil_antialias():
    """修复 PIL ANTIALIAS 兼容性"""
    try:
        from PIL import Image
        if not hasattr(Image, 'ANTIALIAS'):
            Image.ANTIALIAS = Image.Resampling.LANCZOS
    except ImportError:
        pass


fix_pil_antialias()


# ========== OCR 可用性检测 ==========
OCR_AVAILABLE = False
_ocr_instance = None

try:
    import ddddocr
    OCR_AVAILABLE = True
except ImportError:
    pass


def get_ocr_instance():
    """获取 OCR 实例（单例模式）"""
    global _ocr_instance
    if not OCR_AVAILABLE:
        return None
    if _ocr_instance is None:
        try:
            import ddddocr
            _ocr_instance = ddddocr.DdddOcr()
        except:
            return None
    return _ocr_instance


def create_ocr_instance():
    """创建新的 OCR 实例"""
    if not OCR_AVAILABLE:
        return None
    try:
        import ddddocr
        return ddddocr.DdddOcr()
    except:
        return None


# ========== Server酱微信通知 ==========
def send_notification(sendkey, title, content=''):
    """
    发送 Server酱微信通知（异步，不阻塞主线程）
    
    Args:
        sendkey: Server酱的 SendKey
        title: 通知标题（最大32字符）
        content: 通知内容（可选，支持Markdown，最大32KB）
    
    Returns:
        None（异步发送，不返回结果）
    """
    if not sendkey or not sendkey.strip():
        return
    
    def _send():
        try:
            url = f"https://sctapi.ftqq.com/{sendkey.strip()}.send"
            data = {
                'title': title[:32],  # Server酱标题限制32字
                'desp': content[:5000] if content else '',  # 内容适当限制
                'noip': '1',  # 隐藏调用IP
            }
            resp = requests.post(url, data=data, timeout=(5, 10))
            if resp.status_code == 200:
                result = resp.json()
                if result.get('code') != 0:
                    print(f"[Server酱] 发送失败: {result.get('message', '未知错误')}")
                else:
                    print(f"[Server酱] 发送成功: {title}")
            else:
                print(f"[Server酱] HTTP错误: {resp.status_code}")
        except Exception as e:
            print(f"[Server酱] 发送异常: {e}")
    
    # 在独立线程中发送，避免阻塞主线程
    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


# ========== 开发者模式：自定义 Feedback Webhook ==========
WEBHOOK_SUPPORTED_EVENTS = {
    'test',
    'course_available',
    'select_success',
    'swap_success',
    'rollback_success',
    'rollback_failed',
    'conflict_target_retired',
}


def default_webhook_config():
    """返回开发者模式 Webhook 配置示例。"""
    return {
        "webhooks": [
            {
                "name": "自定义通知通道",
                "enabled": False,
                "events": [
                    "test",
                    "course_available",
                    "select_success",
                    "swap_success",
                    "conflict_target_retired",
                ],
                "method": "POST",
                "url": "https://example.com/webhook",
                "headers": {
                    "Content-Type": "application/json"
                },
                "body_type": "json",
                "params": {},
                "body": {
                    "event": "{event}",
                    "title": "{title}",
                    "content": "{content}",
                    "course_name": "{course_name}",
                    "teacher": "{teacher}",
                    "remain": "{remain}",
                    "capacity": "{capacity}",
                    "old_course": "{old_course_name}",
                    "new_course": "{new_course_name}",
                    "message": "{message}",
                    "timestamp": "{timestamp}"
                },
                "timeout": 8,
                "retries": 1
            }
        ]
    }


def make_legacy_feedback_channel(url_template):
    """把旧版 GET Feedback URL 模板迁移成新版 Webhook 通道。"""
    template = str(url_template or '').strip()
    if not template:
        return None
    return {
        "name": "旧版 Feedback 迁移",
        "enabled": True,
        "events": ["course_available", "select_success", "swap_success"],
        "method": "GET",
        "url": template,
        "headers": {},
        "body_type": "none",
        "params": {},
        "body": None,
        "timeout": 8,
        "retries": 0
    }


def normalize_webhook_channels(config):
    """兼容 {'webhooks': [...]} 和直接 [...] 两种配置形态。"""
    if not config:
        return []
    if isinstance(config, dict):
        channels = config.get('webhooks', [])
    else:
        channels = config
    if not isinstance(channels, list):
        return []
    return copy.deepcopy(channels)


def validate_webhook_channels(config):
    """校验开发者模式 Webhook 通道配置，返回 (是否有效, 错误信息)。"""
    channels = normalize_webhook_channels(config)
    if not channels:
        return True, ''

    for index, channel in enumerate(channels, start=1):
        prefix = f"第 {index} 个 Webhook"
        if not isinstance(channel, dict):
            return False, f"{prefix} 必须是对象"

        if not channel.get('enabled', True):
            continue

        url = str(channel.get('url', '') or '').strip()
        if not url:
            return False, f"{prefix} 缺少 url"
        try:
            parsed = urllib.parse.urlsplit(url)
        except ValueError:
            return False, f"{prefix} 的 URL 格式不正确"
        if parsed.scheme.lower() not in ('http', 'https'):
            return False, f"{prefix} 仅支持 http:// 或 https://"
        if not parsed.netloc:
            return False, f"{prefix} 缺少有效主机名"

        method = str(channel.get('method', 'POST') or 'POST').upper()
        if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
            return False, f"{prefix} 的 method 仅支持 GET/POST/PUT/PATCH/DELETE"

        events = channel.get('events', ['*'])
        if isinstance(events, str):
            events = [events]
        if not isinstance(events, list) or not events:
            return False, f"{prefix} 的 events 必须是非空数组"
        for event in events:
            if event != '*' and str(event) not in WEBHOOK_SUPPORTED_EVENTS:
                return False, f"{prefix} 包含未知事件: {event}"

        headers = channel.get('headers', {})
        if headers is not None and not isinstance(headers, dict):
            return False, f"{prefix} 的 headers 必须是对象"

        params = channel.get('params', {})
        if params is not None and not isinstance(params, dict):
            return False, f"{prefix} 的 params 必须是对象"

        body_type = str(channel.get('body_type', 'json') or 'json').lower()
        if body_type not in {'json', 'form', 'raw', 'none'}:
            return False, f"{prefix} 的 body_type 仅支持 json/form/raw/none"

        try:
            timeout = int(channel.get('timeout', 8))
            retries = int(channel.get('retries', 0))
        except (TypeError, ValueError):
            return False, f"{prefix} 的 timeout/retries 必须是数字"
        if timeout < 1 or timeout > 60:
            return False, f"{prefix} 的 timeout 建议在 1-60 秒"
        if retries < 0 or retries > 5:
            return False, f"{prefix} 的 retries 建议在 0-5 次"

    return True, ''


def _stringify_context_value(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    return str(value)


def _render_template(value, context, url_encode=False):
    """递归替换模板占位符。URL 中替换值会自动编码。"""
    if isinstance(value, str):
        rendered = value
        for key, raw_value in context.items():
            replacement = _stringify_context_value(raw_value)
            if url_encode:
                replacement = urllib.parse.quote(replacement, safe='')
            rendered = rendered.replace('{' + key + '}', replacement)
        return rendered
    if isinstance(value, dict):
        return {
            _render_template(k, context, url_encode=False):
            _render_template(v, context, url_encode=False)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_render_template(item, context, url_encode=False) for item in value]
    return value


def send_custom_webhooks(config, event, title, content='', context=None):
    """异步分发开发者模式 Webhook。支持多端点、事件筛选、Headers、Body。"""
    channels = normalize_webhook_channels(config)
    if not channels:
        return

    valid, error = validate_webhook_channels(channels)
    if not valid:
        print(f"[Webhook] 配置无效: {error}")
        return

    payload_context = {
        'event': str(event or ''),
        'title': str(title or ''),
        'content': str(content or ''),
        'message': str(content or title or ''),
    }
    if context:
        payload_context.update(context)
    payload_context.setdefault('timestamp', '')

    def _send_all():
        for channel in channels:
            try:
                if not channel.get('enabled', True):
                    continue
                events = channel.get('events', ['*'])
                if isinstance(events, str):
                    events = [events]
                if '*' not in events and event not in events:
                    continue

                method = str(channel.get('method', 'POST') or 'POST').upper()
                url = _render_template(
                    str(channel.get('url', '') or '').strip(),
                    payload_context,
                    url_encode=True
                )
                host = urllib.parse.urlsplit(url).netloc
                headers = _render_template(channel.get('headers') or {}, payload_context)
                params = _render_template(channel.get('params') or {}, payload_context)
                body_type = str(channel.get('body_type', 'json') or 'json').lower()
                body_template = channel.get('body')
                timeout = max(1, min(60, int(channel.get('timeout', 8))))
                retries = max(0, min(5, int(channel.get('retries', 0))))

                request_kwargs = {
                    'headers': headers,
                    'params': params,
                    'timeout': (5, timeout),
                }
                if method != 'GET' and body_type != 'none':
                    body = _render_template(body_template, payload_context)
                    if body_type == 'json':
                        request_kwargs['json'] = body
                    elif body_type == 'form':
                        request_kwargs['data'] = body if isinstance(body, dict) else {'body': body}
                    elif body_type == 'raw':
                        request_kwargs['data'] = _stringify_context_value(body)

                last_error = None
                for attempt in range(retries + 1):
                    try:
                        response = requests.request(method, url, **request_kwargs)
                        if 200 <= response.status_code < 300:
                            print(f"[Webhook] 发送成功: {channel.get('name', host)}")
                            last_error = None
                            break
                        last_error = f"HTTP {response.status_code}"
                    except Exception as error:
                        last_error = type(error).__name__
                    if attempt < retries:
                        continue
                if last_error:
                    print(f"[Webhook] 发送失败: {channel.get('name', host)} ({last_error})")
            except Exception as error:
                print(f"[Webhook] 发送异常: {type(error).__name__}")

    threading.Thread(target=_send_all, daemon=True).start()


def validate_feedback_template(url_template):
    """校验自定义 Feedback URL 模板，返回 (是否有效, 错误信息)。"""
    template = str(url_template or '').strip()
    if not template:
        return False, "Feedback URL 不能为空"
    if '{title}' not in template or '{content}' not in template:
        return False, "URL 必须同时包含 {title} 和 {content}"

    try:
        parsed = urllib.parse.urlsplit(template)
    except ValueError:
        return False, "URL 格式不正确"
    if parsed.scheme.lower() not in ('http', 'https'):
        return False, "仅支持 http:// 或 https:// URL"
    if not parsed.netloc:
        return False, "URL 缺少有效主机名"
    return True, ''


def build_feedback_url(url_template, title, content=''):
    """将通知内容安全编码后填入 URL 模板。"""
    valid, error = validate_feedback_template(url_template)
    if not valid:
        raise ValueError(error)

    encoded_title = urllib.parse.quote(str(title or '')[:200], safe='')
    # GET URL 长度有限，开发者接口内容保留最有用的前 1200 字符。
    encoded_content = urllib.parse.quote(str(content or '')[:1200], safe='')
    return (
        str(url_template).strip()
        .replace('{title}', encoded_title)
        .replace('{content}', encoded_content)
    )


def send_custom_feedback(url_template, title, content=''):
    """异步调用开发者自定义 Feedback GET Webhook。"""
    valid, error = validate_feedback_template(url_template)
    if not valid:
        print(f"[Feedback] 配置无效: {error}")
        return

    def _send():
        try:
            url = build_feedback_url(url_template, title, content)
            host = urllib.parse.urlsplit(url).netloc
            with requests.get(url, timeout=(5, 10)) as response:
                if 200 <= response.status_code < 300:
                    print(f"[Feedback] 发送成功: {host}")
                else:
                    print(f"[Feedback] HTTP错误: {response.status_code} ({host})")
        except Exception as error:
            print(f"[Feedback] 发送异常: {type(error).__name__}")

    threading.Thread(target=_send, daemon=True).start()
