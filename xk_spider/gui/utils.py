"""
工具与补丁模块
环境检查、SSL修复、OCR检测、Server酱通知推送
"""
import os
import threading
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
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except:
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
