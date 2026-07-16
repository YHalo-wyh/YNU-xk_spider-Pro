"""Isolated captcha OCR entry point for the frozen Windows application.

Qt and ONNX Runtime can load incompatible native runtime DLLs in the same
process.  This helper intentionally imports no PyQt modules.  It supports the
legacy one-shot stdin mode plus a length-prefixed persistent server mode.
"""
import base64
import re
import struct
import sys


def _create_ocr():
    import ddddocr
    try:
        return ddddocr.DdddOcr(show_ad=False)
    except TypeError:
        return ddddocr.DdddOcr()


def _classify(ocr, image_bytes):
    result = str(ocr.classification(image_bytes) or '')
    captcha = ''.join(re.findall(r'[A-Za-z0-9]', result))[:4]
    return captcha if len(captcha) == 4 else ''


def _read_exact(stream, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            return b''
        chunks.extend(chunk)
    return bytes(chunks)


def _run_server():
    """Keep one ONNX model warm and exchange length-prefixed images."""
    try:
        ocr = _create_ocr()
        # Prime the first ONNX inference while the login page is idle.  This
        # avoids moving the model's one-time setup cost onto the login click.
        warmup_image = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAHgAAAAoCAIAAAC6iKlyAAAAc0lEQVR4nO3S'
            'QQ0AMAwDsW78OXcodi+bQKRTzu4O/91gA6E7Hh0ROiJ0ROiI0BGhI0JHhI4IHRE6I'
            'nRE6IjQEaEjQkeEjggdEToidEToiNARoSNCR4SOCB0ROiJ0ROiI0BGhI0JHhI4IHRE'
            '6InRE6IjQ03ib1QNNPACv/gAAAABJRU5ErkJggg=='
        )
        try:
            ocr.classification(warmup_image)
        except Exception:
            pass
        sys.stdout.buffer.write(b"READY\n")
        sys.stdout.buffer.flush()
        while True:
            header = _read_exact(sys.stdin.buffer, 4)
            if not header:
                return 0
            image_size = struct.unpack("!I", header)[0]
            if image_size <= 0 or image_size > 10 * 1024 * 1024:
                return 4
            image_bytes = _read_exact(sys.stdin.buffer, image_size)
            if not image_bytes:
                return 0
            try:
                result = _classify(ocr, image_bytes)
            except Exception:
                result = ''
            sys.stdout.buffer.write(result.encode('ascii', errors='ignore') + b"\n")
            sys.stdout.buffer.flush()
    except Exception as error:
        sys.stderr.write(f"{type(error).__name__}: {error}")
        return 1


def main():
    if '--server' in sys.argv[1:]:
        return _run_server()

    image_bytes = sys.stdin.buffer.read()
    if not image_bytes:
        return 2
    try:
        captcha = _classify(_create_ocr(), image_bytes)
        if not captcha:
            return 3
        sys.stdout.write(captcha)
        sys.stdout.flush()
        return 0
    except Exception as error:
        sys.stderr.write(f"{type(error).__name__}: {error}")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
