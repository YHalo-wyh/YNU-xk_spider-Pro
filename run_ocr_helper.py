"""Isolated captcha OCR entry point for the frozen Windows application.

Qt and ONNX Runtime can load incompatible native runtime DLLs in the same
process.  This helper intentionally imports no PyQt modules.  It accepts raw
image bytes on stdin and writes only the recognised ASCII captcha to stdout.
"""
import re
import sys


def main():
    image_bytes = sys.stdin.buffer.read()
    if not image_bytes:
        return 2

    try:
        import ddddocr

        try:
            ocr = ddddocr.DdddOcr(show_ad=False)
        except TypeError:
            ocr = ddddocr.DdddOcr()
        result = str(ocr.classification(image_bytes) or '')
        captcha = ''.join(re.findall(r'[A-Za-z0-9]', result))[:4]
        if len(captcha) != 4:
            return 3
        sys.stdout.write(captcha)
        sys.stdout.flush()
        return 0
    except Exception as error:
        sys.stderr.write(f"{type(error).__name__}: {error}")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
