"""Isolated captcha OCR entry point for the frozen Windows application.

Qt and ONNX Runtime can load incompatible native runtime DLLs in the same
process. This helper keeps the existing default ddddocr classifier's model,
charset, preprocessing, and CTC decoding path without bundling unused OCR
features such as detection, sliders, APIs, and OpenCV.
"""
import ast
import base64
import io
import os
import re
import struct
import sys

import numpy as np
import onnxruntime
from PIL import Image


def _resource_path(filename):
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "ocr_helper_data", filename)


def _load_old_charset():
    charset_path = _resource_path("charsets.py")
    with open(charset_path, "r", encoding="utf-8") as source_file:
        module = ast.parse(source_file.read(), filename=charset_path)
    for statement in module.body:
        if (
            isinstance(statement, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "CHARSET_OLD"
                for target in statement.targets
            )
        ):
            return ast.literal_eval(statement.value)
    raise RuntimeError("CHARSET_OLD is missing from the bundled charset data")


class CaptchaClassifier:
    """Minimal equivalent of ddddocr's default classification path."""

    def __init__(self):
        onnxruntime.set_default_logger_severity(3)
        self.charset = _load_old_charset()
        self.session = onnxruntime.InferenceSession(
            _resource_path("common_old.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    @staticmethod
    def _preprocess(image_bytes):
        image = Image.open(io.BytesIO(image_bytes))
        target_height = 64
        target_width = int(image.size[0] * (target_height / image.size[1]))
        image = image.resize((target_width, target_height), Image.LANCZOS)
        image = image.convert("L")
        image_array = np.array(image).astype(np.float32) / 255.0
        image_array = np.expand_dims(image_array, axis=0)
        return np.expand_dims(image_array, axis=0)

    def classification(self, image_bytes):
        output = self.session.run(None, {
            self.input_name: self._preprocess(image_bytes),
        })[0]
        if len(output.shape) == 3:
            if output.shape[1] == 1:
                predicted_indices = np.argmax(output[:, 0, :], axis=1)
            else:
                predicted_indices = np.argmax(output[0, :, :], axis=1)
        else:
            predicted_indices = np.argmax(output, axis=-1)
            if predicted_indices.ndim == 0:
                predicted_indices = np.array([predicted_indices])

        result = []
        previous_index = None
        for index in predicted_indices:
            index = int(index)
            if index != previous_index and index != 0 and index < len(self.charset):
                result.append(self.charset[index])
            previous_index = index
        return "".join(result)


def _create_ocr():
    return CaptchaClassifier()


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
