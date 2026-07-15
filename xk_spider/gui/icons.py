"""Small embedded SVG icon set used by the native Qt interface.

Each icon is rendered at the common Windows device-pixel ratios.  Keeping
those high-resolution variants inside the QIcon prevents Qt from stretching a
single 1x pixmap when a window is moved to a high-DPI monitor.
"""
from functools import lru_cache

from PyQt5.QtCore import QByteArray, Qt, QSize, QRectF
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QWidget


_PATHS = {
    "user": '<circle cx="12" cy="7.5" r="4.2" fill="__COLOR__" stroke="none"/><path d="M3.8 21c.5-5 3.3-7.6 8.2-7.6s7.7 2.6 8.2 7.6Z" fill="__COLOR__" stroke="none"/>',
    "lock": '<path d="M8 10V7.2a4 4 0 0 1 8 0V10" fill="none" stroke="__COLOR__" stroke-width="2.7"/><rect x="4.5" y="9.5" width="15" height="12" rx="2.5" fill="__COLOR__" stroke="none"/><circle cx="12" cy="15" r="1.4" fill="white" stroke="none"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="m3 3 18 18"/><path d="M10.6 5.2A10.8 10.8 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-2.2 3.2M6.6 6.6C3.7 8.5 2 12 2 12s3.5 7 10 7a10.6 10.6 0 0 0 4.1-.8"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
    "calendar-days": '<rect x="3" y="4.5" width="18" height="17" rx="3"/><path d="M8 2.5v4M16 2.5v4M3 9.5h18"/><path d="M7 13h2M11 13h2M15 13h2M7 17h2M11 17h2M15 17h2"/>',
    "circle-check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.6 2.6L16.5 9"/>',
    "list-check": '<path d="m4 6 1.5 1.5L8.5 4.5M11 6h9M4 12l1.5 1.5 3-3M11 12h9M4 18l1.5 1.5 3-3M11 18h9"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "star": '<path d="m12 2.5 2.9 5.9 6.5.9-4.7 4.6 1.1 6.5-5.8-3.1-5.8 3.1 1.1-6.5-4.7-4.6 6.5-.9Z"/>',
    "alert-triangle": '<path d="M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    "activity": '<path d="M3 12h4l2-7 4 14 2-7h6"/>',
    "play": '<path d="m8 5 11 7-11 7Z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
    "bell": '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 1 1 5.8 1c0 2-3 2-3 4M12 18h.01"/>',
    "logout": '<path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/>',
    "refresh": '<path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.5 9A7 7 0 0 0 6 6.5L4 9M5.5 15A7 7 0 0 0 18 17.5l2-2.5"/>',
    "code": '<path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "trash": '<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6"/>',
    "github": '<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3.3-.4 6.8-1.6 6.8-7A5.5 5.5 0 0 0 19.3 4 5.1 5.1 0 0 0 19.1.5S17.9.1 15 2a13.4 13.4 0 0 0-6 0C6.1.1 4.9.5 4.9.5A5.1 5.1 0 0 0 4.7 4a5.5 5.5 0 0 0-1.5 3.8c0 5.4 3.5 6.6 6.8 7A4.8 4.8 0 0 0 9 18v4"/>',
}


def _svg_bytes(name, color):
    body = _PATHS.get(name, _PATHS["info"]).replace("__COLOR__", color)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" stroke="%s" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">%s</svg>' % (color, body)
    )
    return QByteArray(svg.encode("utf-8"))


class VectorIconWidget(QWidget):
    """Paint an SVG directly onto the widget's device for crisp HiDPI output."""

    def __init__(self, name, color="#667085", size=20, parent=None):
        super().__init__(parent)
        self._renderer = QSvgRenderer(_svg_bytes(name, color), self)
        self.setFixedSize(QSize(size, size))
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_icon(self, name, color="#667085"):
        self._renderer.load(_svg_bytes(name, color))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Python 3.13's PyQt5 build requires the documented QRectF overload.
        self._renderer.render(painter, QRectF(self.rect()))


@lru_cache(maxsize=256)
def icon(name, color="#667085", size=20):
    renderer = QSvgRenderer(_svg_bytes(name, color))
    result = QIcon()
    for device_ratio in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0):
        physical_size = max(1, round(size * device_ratio))
        pixmap = QPixmap(physical_size, physical_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(device_ratio)
        result.addPixmap(pixmap)
    return result
