"""
用户界面模块 - View
Modern Dark Dashboard 风格 (Catppuccin Mocha 配色)
"""
import os
import time
import sys
import subprocess
import json
import re
import math

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QTextEdit, QProgressBar, QMessageBox, QFrame, QGridLayout, QSizePolicy,
    QSpinBox, QAbstractSpinBox, QScrollArea, QCheckBox, QSplitter, QApplication, QMenu,
    QGraphicsOpacityEffect, QAction,
    QDialog, QDialogButtonBox, QProgressDialog, QStackedWidget, QToolButton,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QAbstractItemView,
    QAbstractButton
)
from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QUrl, QSize, QPoint, QRect, QEvent,
    QPersistentModelIndex,
    QPropertyAnimation, QParallelAnimationGroup, QVariantAnimation, QEasingCurve,
)
from PyQt5.QtGui import (
    QFont, QPainter, QColor, QBrush, QTextCursor, QDesktopServices, QIcon,
    QTextCharFormat, QRadialGradient, QPainterPath, QRegion, QPen,
)

from .config import COURSE_TYPES, COURSE_NAME_TO_TYPE, parse_int, MONITOR_STATE_FILE, WATCHDOG_SIGNAL_FILE
from .workers import (
    LoginWorker, MultiGrabWorker, CourseFetchWorker, CurriculumFetchWorker,
    SelectedCoursesWorker, WithdrawCourseWorker,
    UpdateCheckWorker, DownloadUpdateWorker,
)
from .logger import get_logger
from .utils import (
    default_webhook_config, make_legacy_feedback_channel,
    normalize_webhook_channels, send_custom_webhooks,
    validate_webhook_channels,
)
from xk_spider.storage import (
    CONFIG_FILE, migrate_legacy_data, read_json, write_json_atomic,
)
from .icons import icon, VectorIconWidget
from .theme import (
    Colors as ThemeColors, apply_palette, build_stylesheet,
    build_tooltip_stylesheet,
)


Colors = ThemeColors


class AmbientLoginPage(QWidget):
    """Low-cost animated background used only while the login page is visible."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loginPage")
        self._phase = 0.0
        self._timer = QTimer(self)
        # The light field moves very slowly; a low repaint cadence keeps the
        # effect alive without burning CPU on a full-window software gradient.
        # and avoids repainting a full-screen gradient at video frame rates.
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def _advance(self):
        if self.isVisible():
            self._phase = (self._phase + 0.07) % (math.pi * 2)
            self.update()

    def set_active(self, active):
        if active and not self._timer.isActive():
            self._timer.start()
        elif not active:
            self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(Colors.BASE))

        # Two large, very soft colour fields provide the subtle motion seen in
        # modern macOS-style authentication screens.  The timer is stopped as
        # soon as the workbench is shown.
        width = max(1, self.width())
        height = max(1, self.height())
        shift_x = math.sin(self._phase) * width * 0.035
        shift_y = math.cos(self._phase * 0.8) * height * 0.035
        for cx, cy, radius, color in (
            (width * 0.24 + shift_x, height * 0.28 + shift_y, width * 0.42, Colors.BLUE),
            (width * 0.78 - shift_x, height * 0.72 - shift_y, width * 0.36, Colors.LAVENDER),
        ):
            gradient = QRadialGradient(cx, cy, radius)
            tint = QColor(color)
            tint.setAlpha(24 if Colors.MODE == "light" else 18)
            transparent = QColor(color)
            transparent.setAlpha(0)
            gradient.setColorAt(0.0, tint)
            gradient.setColorAt(1.0, transparent)
            painter.fillRect(self.rect(), gradient)


class MotionButton(QPushButton):
    """Primary button whose motion never rasterises its text."""

    # Hover/pressed feedback is handled by QSS.  A QGraphicsEffect on the
    # entire button turns its text into a cached bitmap and looks soft at
    # fractional Windows scale factors.
    pass


class AnimatedScheduleCard(QFrame):
    """Rounded course card with a subtle colour/border hover transition."""

    def __init__(self, accent, parent=None):
        super().__init__(parent)
        self.setObjectName("scheduleCourseCard")
        # The global theme gives QWidget a solid base colour.  Keep the
        # custom-painted margin transparent so its rounded shadow cannot
        # reveal a square dark strip in the unarranged-course grid.
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._accent = QColor(accent)
        self._hover = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._set_hover_progress)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)

    @staticmethod
    def _mix(start, end, progress):
        return QColor(
            round(start.red() + (end.red() - start.red()) * progress),
            round(start.green() + (end.green() - start.green()) * progress),
            round(start.blue() + (end.blue() - start.blue()) * progress),
            round(start.alpha() + (end.alpha() - start.alpha()) * progress),
        )

    def _animate_to(self, target):
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(float(target))
        self._animation.start()

    def _set_hover_progress(self, value):
        self._hover = float(value)
        self.update()

    def enterEvent(self, event):
        self._animate_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        shadow_rect = self.rect().adjusted(2, 3, -2, -1)
        shadow_alpha = (28 if Colors.MODE == 'light' else 72) + round(self._hover * 18)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, shadow_alpha))
        painter.drawRoundedRect(shadow_rect, 12, 12)

        rect = self.rect().adjusted(1, 1, -1, -4)
        background = self._mix(
            QColor(Colors.SURFACE1), QColor(Colors.SURFACE2), self._hover
        )
        border = self._mix(
            QColor(Colors.BORDER), self._accent, self._hover * 0.82
        )
        painter.setBrush(background)
        painter.setPen(QPen(border, 1.0 + self._hover * 0.5))
        painter.drawRoundedRect(rect, 12, 12)


class GrabListWidget(QListWidget):
    """v2.5 native item rendering plus a real remove button on the right."""

    remove_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("grabList")
        self._remove_buttons = {}
        self.verticalScrollBar().valueChanged.connect(self._queue_button_layout)
        self.horizontalScrollBar().valueChanged.connect(self._queue_button_layout)
        self.model().rowsRemoved.connect(self._queue_button_layout)
        self.model().rowsInserted.connect(self._queue_button_layout)

    def ensure_remove_button(self, item):
        if item is None:
            return
        for button, persistent in self._remove_buttons.items():
            if persistent.isValid() and self.item(persistent.row()) is item:
                button.setIcon(icon("trash", Colors.SUBTEXT0, 16))
                self._queue_button_layout()
                return

        persistent = QPersistentModelIndex(self.indexFromItem(item))
        button = QToolButton(self.viewport())
        button.setObjectName("grabRemoveButton")
        button.setFixedSize(30, 30)
        button.setIconSize(QSize(16, 16))
        button.setIcon(icon("trash", Colors.SUBTEXT0, 16))
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip("从待抢列表移除")
        button.clicked.connect(
            lambda _checked=False, control=button: self._request_remove(control)
        )
        self._remove_buttons[button] = persistent
        button.show()
        self._queue_button_layout()

    def _request_remove(self, button):
        persistent = self._remove_buttons.get(button)
        if persistent is None or not persistent.isValid():
            return
        item = self.item(persistent.row())
        if item is not None:
            self.remove_requested.emit(item)

    def _queue_button_layout(self, *_args):
        QTimer.singleShot(0, self._layout_remove_buttons)

    def _layout_remove_buttons(self):
        viewport_rect = self.viewport().rect()
        stale = []
        for button, persistent in self._remove_buttons.items():
            if not persistent.isValid():
                stale.append(button)
                continue
            item = self.item(persistent.row())
            if item is None:
                stale.append(button)
                continue
            rect = self.visualItemRect(item)
            visible = rect.isValid() and viewport_rect.intersects(rect)
            button.setVisible(visible)
            if visible:
                button.move(
                    rect.right() - button.width() - 6,
                    rect.top() + max(0, (rect.height() - button.height()) // 2),
                )
                button.raise_()
        for button in stale:
            self._remove_buttons.pop(button, None)
            button.deleteLater()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_button_layout()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._queue_button_layout()


class FocusLineEdit(QLineEdit):
    focusChanged = pyqtSignal(bool)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focusChanged.emit(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focusChanged.emit(False)


class LoginInputFrame(QFrame):
    """AstrBot-like login field with a large solid icon and focus motion."""

    def __init__(self, icon_name, label, password=False, parent=None):
        super().__init__(parent)
        self.setObjectName("loginInputFrame")
        self.setProperty("focused", False)
        self.setFixedHeight(64)
        self._icon_name = icon_name
        self._label_text = label
        self._focused = False
        self._password = bool(password)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(17, 9, 10 if password else 17, 9)
        layout.setSpacing(13)

        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self._icon_opacity = QGraphicsOpacityEffect(self.icon_label)
        self._icon_opacity.setOpacity(0.76)
        self.icon_label.setGraphicsEffect(self._icon_opacity)
        layout.addWidget(self.icon_label)

        self.line_edit = FocusLineEdit(self)
        self.line_edit.setObjectName("loginLineEdit")
        self.line_edit.setPlaceholderText(label)
        self.line_edit.setFrame(False)
        if password:
            self.line_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.line_edit, 1)

        self.eye_button = None
        if password:
            self.eye_button = QToolButton(self)
            self.eye_button.setObjectName("loginEyeButton")
            self.eye_button.setFixedSize(40, 40)
            self.eye_button.setIconSize(QSize(26, 26))
            self.eye_button.setCursor(Qt.PointingHandCursor)
            layout.addWidget(self.eye_button)

        self.floating_label = QLabel(label, self)
        self.floating_label.setObjectName("loginFloatingLabel")
        self.floating_label.adjustSize()
        self.floating_label.hide()
        self.floating_label.raise_()

        self.line_edit.focusChanged.connect(self._set_focused)
        self.line_edit.textChanged.connect(self._sync_floating_label)
        self._apply_icon()
        if self._password:
            QTimer.singleShot(0, self._apply_password_spacing)

    def _apply_icon(self):
        color = Colors.BLUE if self._focused else Colors.OVERLAY0
        self.icon_label.setPixmap(icon(self._icon_name, color, 26).pixmap(26, 26))

    def _set_focused(self, focused):
        self._focused = bool(focused)
        self.setProperty("focused", self._focused)
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_icon()
        self._sync_floating_label()

        if hasattr(self, '_focus_animation'):
            self._focus_animation.stop()
        self._focus_animation = QPropertyAnimation(
            self._icon_opacity, b"opacity", self
        )
        self._focus_animation.setDuration(150)
        self._focus_animation.setEndValue(1.0 if self._focused else 0.76)
        self._focus_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._focus_animation.start()

    def _sync_floating_label(self, *_args):
        floating = self._focused or bool(self.line_edit.text())
        self.floating_label.setVisible(floating)
        self.line_edit.setPlaceholderText("" if floating else self._label_text)
        if floating:
            self.floating_label.adjustSize()
            self.floating_label.raise_()

    def apply_theme(self):
        self._apply_icon()
        self.style().unpolish(self)
        self.style().polish(self)
        if self._password:
            QTimer.singleShot(0, self._apply_password_spacing)

    def _apply_password_spacing(self):
        password_font = self.line_edit.font()
        spacing = (
            0.0 if self.line_edit.echoMode() == QLineEdit.Normal else -6.0
        )
        password_font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        self.line_edit.setFont(password_font)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.floating_label.move(52, 0)

    def mousePressEvent(self, event):
        if self.eye_button is None or not self.eye_button.geometry().contains(event.pos()):
            self.line_edit.setFocus(Qt.MouseFocusReason)
        super().mousePressEvent(event)


class RoundedComboDelegate(QStyledItemDelegate):
    """Draw rounded, inset hover and selection states for combo popups."""

    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        item_rect = styled.rect.adjusted(5, 3, -5, -3)
        selected = bool(styled.state & QStyle.State_Selected)
        hovered = bool(styled.state & QStyle.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(Colors.BLUE if selected else Colors.SURFACE1))
            painter.drawRoundedRect(item_rect, 10, 10)

        text_rect = item_rect.adjusted(13, 0, -10, 0)
        painter.setPen(QColor("#FFFFFF" if selected else Colors.TEXT))
        text = styled.fontMetrics.elidedText(
            styled.text, Qt.ElideRight, max(1, text_rect.width())
        )
        painter.setFont(styled.font)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(44)
        return size


class FullyVisibleItemDelegate(QStyledItemDelegate):
    """Avoid drawing the clipped fragment of the next course at list edges."""

    def paint(self, painter, option, index):
        view = option.widget
        if view is not None:
            viewport_rect = view.viewport().rect()
            visible_rect = option.rect.intersected(viewport_rect)
            if visible_rect.height() < option.rect.height():
                return
        super().paint(painter, option, index)


class SpaciousComboBox(QComboBox):
    """Combo box with a roomy popup aligned directly below its field."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_animation = None
        self._popup_closing = False
        self._popup_delegate = RoundedComboDelegate(self.view())
        self.view().setItemDelegate(self._popup_delegate)
        self.view().setMouseTracking(True)

    @staticmethod
    def _apply_popup_mask(popup, visible_height=None):
        path = QPainterPath()
        rect = popup.rect()
        height = rect.height() if visible_height is None else max(
            1, min(rect.height(), int(visible_height))
        )
        path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(height), 15.0, 15.0
        )
        popup.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def showPopup(self):
        view = self.view()
        popup_width = self.width()
        popup_height = min(max(self.count(), 1) * 44 + 24, 360)
        popup = view.window()
        popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        popup.setStyleSheet(f"background-color: {Colors.SURFACE0}; border: none;")
        view.setObjectName("spaciousComboPopup")
        view.setFrameShape(QFrame.NoFrame)
        view.setAttribute(Qt.WA_StyledBackground, True)
        view.setStyleSheet(f"""
            QAbstractItemView#spaciousComboPopup {{
                background-color: {Colors.SURFACE0};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 15px;
                padding: 7px;
                outline: none;
            }}
            QAbstractItemView#spaciousComboPopup::item {{
                min-height: 36px;
                background-color: transparent;
                color: transparent;
            }}
            QAbstractItemView#spaciousComboPopup::item:hover {{
                background-color: transparent;
            }}
            QAbstractItemView#spaciousComboPopup::item:selected {{
                background-color: transparent;
                color: transparent;
            }}
        """)
        view.setMinimumWidth(0)
        view.setFixedWidth(popup_width)
        view.setMinimumHeight(popup_height)
        super().showPopup()
        parent_handle = self.window().windowHandle()
        popup_handle = popup.windowHandle()
        if parent_handle is not None and popup_handle is not None:
            popup_handle.setScreen(parent_handle.screen())
        popup.setMinimumWidth(popup_width)
        popup.setMaximumWidth(popup_width)
        anchor = self.mapToGlobal(QPoint(0, self.height() + 6))
        target_geometry = QRect(anchor.x(), anchor.y(), popup_width, popup_height)

        if self._popup_animation is not None:
            self._popup_animation.stop()
        self._popup_closing = False
        popup.setGeometry(target_geometry)
        popup.setWindowOpacity(0.0)
        self._apply_popup_mask(popup, 24)
        popup.show()
        popup.raise_()

        reveal_animation = QVariantAnimation(self)
        reveal_animation.setDuration(380)
        reveal_animation.setStartValue(24)
        reveal_animation.setEndValue(popup_height)
        reveal_animation.setEasingCurve(QEasingCurve.OutQuart)
        reveal_animation.valueChanged.connect(
            lambda value, target=popup: self._apply_popup_mask(target, value)
        )

        opacity_animation = QPropertyAnimation(popup, b"windowOpacity", self)
        opacity_animation.setDuration(280)
        opacity_animation.setStartValue(0.0)
        opacity_animation.setEndValue(1.0)
        opacity_animation.setEasingCurve(QEasingCurve.OutCubic)

        self._popup_animation = QParallelAnimationGroup(self)
        self._popup_animation.addAnimation(reveal_animation)
        self._popup_animation.addAnimation(opacity_animation)
        self._popup_animation.finished.connect(
            lambda target=popup: (
                target.setWindowOpacity(1.0), self._apply_popup_mask(target)
            )
        )
        self._popup_animation.start()

    def hidePopup(self):
        popup = self.view().window()
        if (QApplication.closingDown() or not self.isVisible()
                or not popup.isVisible() or self._popup_closing):
            super().hidePopup()
            return

        if self._popup_animation is not None:
            self._popup_animation.stop()
        self._popup_closing = True
        current_height = popup.mask().boundingRect().height() or popup.height()
        reveal_animation = QVariantAnimation(self)
        reveal_animation.setDuration(220)
        reveal_animation.setStartValue(current_height)
        reveal_animation.setEndValue(24)
        reveal_animation.setEasingCurve(QEasingCurve.InOutCubic)
        reveal_animation.valueChanged.connect(
            lambda value, target=popup: self._apply_popup_mask(target, value)
        )

        opacity_animation = QPropertyAnimation(popup, b"windowOpacity", self)
        opacity_animation.setDuration(190)
        opacity_animation.setStartValue(popup.windowOpacity())
        opacity_animation.setEndValue(0.0)
        opacity_animation.setEasingCurve(QEasingCurve.InCubic)

        self._popup_animation = QParallelAnimationGroup(self)
        self._popup_animation.addAnimation(reveal_animation)
        self._popup_animation.addAnimation(opacity_animation)
        self._popup_animation.finished.connect(
            lambda target=popup: self._finish_popup_hide(target)
        )
        self._popup_animation.start()

    def _finish_popup_hide(self, popup):
        popup.setWindowOpacity(1.0)
        self._popup_closing = False
        super().hidePopup()


class InlineSpinBox(QFrame):
    """Compact stepper whose controls sit inside one rounded input surface."""

    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inlineSpinBox")
        self.setFocusPolicy(Qt.ClickFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._minus_button = QToolButton(self)
        self._minus_button.setObjectName("spinStepButton")
        self._minus_button.setText("−")
        self._minus_button.setCursor(Qt.PointingHandCursor)
        self._minus_button.setAutoRepeat(True)
        self._minus_button.setFixedSize(30, 30)
        self._minus_button.setToolTip("减少并发数")
        layout.addWidget(self._minus_button)

        self._spin_box = QSpinBox(self)
        self._spin_box.setObjectName("inlineSpinValue")
        self._spin_box.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._spin_box.setAlignment(Qt.AlignCenter)
        self._spin_box.setFrame(False)
        self._spin_box.setMinimumWidth(32)
        self._spin_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._spin_box, 1)

        self._plus_button = QToolButton(self)
        self._plus_button.setObjectName("spinStepButton")
        self._plus_button.setText("+")
        self._plus_button.setCursor(Qt.PointingHandCursor)
        self._plus_button.setAutoRepeat(True)
        self._plus_button.setFixedSize(30, 30)
        self._plus_button.setToolTip("增加并发数")
        layout.addWidget(self._plus_button)

        self._minus_button.clicked.connect(self._spin_box.stepDown)
        self._plus_button.clicked.connect(self._spin_box.stepUp)
        self._spin_box.valueChanged.connect(self.valueChanged)
        self._spin_box.valueChanged.connect(self._update_button_states)
        self.setFocusProxy(self._spin_box)
        self._update_button_states(self._spin_box.value())

    def setRange(self, minimum, maximum):
        self._spin_box.setRange(minimum, maximum)
        self._update_button_states(self._spin_box.value())

    def setValue(self, value):
        self._spin_box.setValue(value)

    def value(self):
        return self._spin_box.value()

    def _update_button_states(self, value):
        self._minus_button.setEnabled(value > self._spin_box.minimum())
        self._plus_button.setEnabled(value < self._spin_box.maximum())


class CourseCard(QFrame):
    """课程卡片 - 现代宽卡片设计"""
    grab_clicked = pyqtSignal(dict)
    
    def __init__(self, course_data, parent=None):
        super().__init__(parent)
        self.course_data = course_data
        self.init_ui()
        
    def init_ui(self):
        self.setObjectName("courseCard")
        self.setMinimumWidth(290)
        self.setMaximumWidth(520)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 17, 18, 17)
        is_conflict = bool(self.course_data.get('isConflict', False))
        is_chosen = bool(self.course_data.get('isChosen', False))
        is_full = bool(self.course_data.get('isFull', False))

        status_row = QHBoxLayout()
        status_row.setSpacing(7)
        if is_chosen:
            status_row.addWidget(self._make_badge("已选", Colors.GREEN))
        else:
            if is_full:
                status_row.addWidget(self._make_badge("已满", Colors.RED))
            if is_conflict:
                status_row.addWidget(self._make_badge("时间冲突", Colors.YELLOW))
            if not is_full:
                status_row.addWidget(self._make_badge("可选", Colors.GREEN))
        status_row.addStretch()
        layout.addLayout(status_row)

        teacher = str(self.course_data.get('SKJS', '未知') or '未知')
        teacher_label = QLabel(teacher)
        teacher_label.setWordWrap(True)
        teacher_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Colors.TEXT};")
        self._teacher_label = teacher_label
        layout.addWidget(teacher_label)

        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        time_icon = QLabel()
        time_icon.setPixmap(icon("calendar", Colors.SUBTEXT0, 17).pixmap(17, 17))
        time_icon.setFixedSize(18, 18)
        time_row.addWidget(time_icon, 0, Qt.AlignTop)
        time_label = QLabel(str(self.course_data.get('SKSJ', '') or '时间待定'))
        time_label.setWordWrap(True)
        time_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        time_label.setStyleSheet(f"color: {Colors.SUBTEXT0}; font-size: 13px;")
        self._time_label = time_label
        time_row.addWidget(time_label, 1)
        layout.addLayout(time_row)

        selected = parse_int(self.course_data.get('YXRS', 0))
        capacity = parse_int(self.course_data.get('KRL', 0))
        remain = max(0, capacity - selected)
        metrics = QFrame()
        metrics.setObjectName("softCard")
        metrics_layout = QHBoxLayout(metrics)
        metrics_layout.setContentsMargins(12, 9, 12, 9)
        metrics_layout.setSpacing(10)
        for name, value, color in (
            ("已选", selected, Colors.SUBTEXT1),
            ("容量", capacity, Colors.SUBTEXT1),
            ("余量", remain, Colors.GREEN if remain > 0 else Colors.RED),
        ):
            metric = QLabel(f"{name}  {value}")
            metric.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
            metrics_layout.addWidget(metric)
        metrics_layout.addStretch()
        layout.addWidget(metrics)

        progress = QProgressBar()
        progress.setMaximum(capacity if capacity > 0 else 1)
        progress.setValue(selected)
        progress.setTextVisible(False)
        layout.addWidget(progress)

        self.grab_btn = QPushButton()
        self.grab_btn.setFixedHeight(40)
        self.grab_btn.setCursor(Qt.PointingHandCursor)
        if is_chosen:
            self.grab_btn.setText("已选中")
            self.grab_btn.setObjectName("secondaryButton")
            self.grab_btn.setEnabled(False)
        elif is_full:
            self.grab_btn.setText("加入待抢")
            self.grab_btn.setObjectName("dangerButton")
            self.grab_btn.clicked.connect(lambda: self.grab_clicked.emit(self.course_data))
        elif is_conflict:
            self.grab_btn.setText("加入待抢（存在冲突）")
            self.grab_btn.setObjectName("secondaryButton")
            self.grab_btn.clicked.connect(lambda: self.grab_clicked.emit(self.course_data))
        else:
            self.grab_btn.setText("加入待抢")
            self.grab_btn.setObjectName("primaryButton")
            self.grab_btn.clicked.connect(lambda: self.grab_clicked.emit(self.course_data))
        layout.addWidget(self.grab_btn)
        self.apply_theme()
        QTimer.singleShot(0, self._sync_wrapped_label_heights)

    def _sync_wrapped_label_heights(self):
        """Keep long teacher/time text visible after responsive relayouts."""
        for label in (
            getattr(self, '_teacher_label', None),
            getattr(self, '_time_label', None),
        ):
            if not label or label.width() <= 0:
                continue
            bounds = label.fontMetrics().boundingRect(
                QRect(0, 0, max(1, label.contentsRect().width()), 1000),
                Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
                label.text(),
            )
            target = max(label.fontMetrics().height() + 2, bounds.height() + 4)
            if label.minimumHeight() != target:
                label.setMinimumHeight(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_wrapped_label_heights)

    def _make_badge(self, text, color):
        badge = QLabel(text)
        badge.setStyleSheet(
            f"color: {color}; background-color: {Colors.SURFACE1}; border: 1px solid {Colors.BORDER}; "
            "border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 650;"
        )
        return badge

    def apply_theme(self):
        if self.course_data.get('isChosen', False):
            border = Colors.GREEN
        elif self.course_data.get('isConflict', False):
            border = Colors.YELLOW
        else:
            border = Colors.BORDER
        self.setStyleSheet(f"""
            QFrame#courseCard {{
                background-color: {Colors.SURFACE0};
                border: 1px solid {border};
                border-radius: 20px;
            }}
            QFrame#courseCard:hover {{ border-color: {Colors.BLUE}; }}
        """)

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)


class MainWindow(QMainWindow):
    """主窗口 - Modern Dark Dashboard"""

    curriculum_updated = pyqtSignal(list, list, str)
    
    # 版本信息
    VERSION = "v2.6.0"
    GITHUB_URL = "https://github.com/YHalo-wyh/YNU-xk_spider-Pro"
    
    def __init__(self):
        super().__init__()
        self.is_logged_in = False
        self.token = ''
        self.batch_code = ''
        self.batch_name = ''
        self.student_code = ''
        self.campus = '02'  # 默认呈贡校区
        self.cookies = ''
        self.multi_grab_worker = None
        self._api_courses_grouped = {}
        self._pending_monitor_courses = []
        self._is_searching = False
        self._current_search_keyword = ''
        self._showing_search_empty_state = False
        self._is_manual_login_attempt = False
        self._manual_login_fail_count = 0
        self._auto_relogin_retry_count = 0
        self._installing_update = False
        self._update_resume_monitoring = False
        self._active_conflict_policy = None
        self._pending_resume_conflict_policy = None
        self._swap_risk_confirmed = False
        self._pending_resume_swap_risk_confirmed = False
        config_snapshot = read_json(CONFIG_FILE, {})
        self.theme_mode = str(config_snapshot.get('theme_mode', 'light')).lower()
        if self.theme_mode not in ('light', 'dark'):
            self.theme_mode = 'light'
        apply_palette(self.theme_mode)
        
        # Server酱配置
        self.serverchan_enabled = False
        self.serverchan_key = ''

        # 开发者模式配置
        self.developer_mode_enabled = False
        self.feedback_url = ''
        self.developer_webhooks = []
        
        # 日志系统
        self._logger = get_logger()
        self._heartbeat_count = 0
        migrated = migrate_legacy_data()
        if migrated:
            self._logger.info(f"已迁移 {len(migrated)} 个旧版用户数据文件到独立数据目录")
        
        # 自动轮询 Timer
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._on_poll_timer)
        self._poll_interval = 4000
        
        # 课程获取 Worker
        self._course_fetch_worker = None
        self._curriculum_worker = None
        self._curriculum_dialog = None
        self._curriculum_arranged = []
        self._curriculum_unarranged = []
        self._curriculum_loaded = False
        self._curriculum_error = ''
        self._curriculum_refresh_pending = False
        self._curriculum_prefetch_waiting = False
        self._selected_courses_worker = None
        self._withdraw_course_worker = None
        self._selected_courses_dialog = None
        self._fetch_silent = False
        self._responsive_timer = QTimer(self)
        self._responsive_timer.setSingleShot(True)
        self._responsive_timer.setInterval(90)
        self._responsive_timer.timeout.connect(self._apply_responsive_layout)
        
        self.init_ui()
        self.init_menu()
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
        QTimer.singleShot(0, self._apply_crisp_fonts)
        self.load_config()
        self.adjust_for_screen()
        
        # 检查是否需要恢复监控（闪退恢复）
        self._pending_restore_state = None
        state = self.load_monitor_state()
        if state and state.get('courses'):
            self._restore_saved_watchlist(state)
            if state.get('is_monitoring'):
                self._pending_restore_state = state
                self._logger.info(f"检测到上次监控未正常结束，待恢复 {len(state['courses'])} 门课程")
                # 延迟自动登录（等待窗口显示后）
                QTimer.singleShot(500, self._auto_login_for_restore)
            else:
                self._logger.info(f"已恢复 {len(state['courses'])} 门待选课程")
    
    def adjust_for_screen(self):
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        screen_width = screen_geo.width()
        screen_height = screen_geo.height()
        min_width = min(960, max(860, screen_width - 32))
        min_height = min(640, max(560, screen_height - 32))
        self.setMinimumSize(min_width, min_height)
        # AstrBot-style scaling: widgets keep stable logical sizes while the
        # content area grows.  Start at a comfortable desktop size instead of
        # opening at almost the full monitor on every resolution.
        width = min(1500, max(min_width, int(screen_width * 0.80)))
        height = min(920, max(min_height, int(screen_height * 0.84)))
        width = min(width, screen_width)
        height = min(height, screen_height)
        self.resize(width, height)
        x = screen_geo.x() + (screen_geo.width() - width) // 2
        y = screen_geo.y() + (screen_geo.height() - height) // 2
        self.move(x, y)
        QTimer.singleShot(0, self._apply_responsive_layout)
    
    def init_ui(self):
        self.setWindowTitle('YNU选课助手 Pro')
        icon_path = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setMinimumSize(900, 600)
        shared_stylesheet = build_stylesheet(self.theme_mode)
        self.setStyleSheet(shared_stylesheet)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_tooltip_stylesheet(self.theme_mode))
        self.app_stack = QStackedWidget()
        self.app_stack.setObjectName("appRoot")
        self.setCentralWidget(self.app_stack)

        self._build_login_page(icon_path)
        self._build_workspace_page()
        self._build_notification_dialog()

        self.app_stack.addWidget(self.login_page)
        self.app_stack.addWidget(self.workspace_page)
        self.app_stack.setCurrentWidget(self.login_page)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.run_indicator = QLabel("待机")
        self.run_indicator.setObjectName("runPill")
        self.statusBar().addPermanentWidget(self.run_indicator)
        self.statusBar().setVisible(False)

    @staticmethod
    def _prepare_dialog(dialog):
        dialog.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        return dialog

    def _show_standard_message(self, parent, message_icon, title, text):
        box = QMessageBox(message_icon, title, str(text), QMessageBox.Ok, parent)
        self._prepare_dialog(box)
        ok_button = box.button(QMessageBox.Ok)
        if ok_button:
            ok_button.setText("确定")
        box.exec_()

    def _build_login_page(self, icon_path):
        self.login_page = AmbientLoginPage()
        page_layout = QVBoxLayout(self.login_page)
        page_layout.setContentsMargins(24, 18, 24, 18)

        self.login_shell = QWidget()
        self.login_shell.setObjectName("loginShell")
        self.login_shell.setStyleSheet("QWidget#loginShell { background-color: transparent; }")
        self.login_shell.setFixedWidth(530)
        shell_layout = QVBoxLayout(self.login_shell)
        shell_layout.setContentsMargins(12, 12, 12, 12)

        self.login_frame = QFrame()
        self.login_frame.setObjectName("loginCard")
        login_layout = QVBoxLayout(self.login_frame)
        login_layout.setContentsMargins(38, 32, 38, 34)
        login_layout.setSpacing(16)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo_label = QLabel()
        if os.path.exists(icon_path):
            logo_label.setPixmap(QIcon(icon_path).pixmap(78, 78))
        logo_label.setFixedSize(82, 82)
        logo_label.setAlignment(Qt.AlignCenter)
        brand_row.addWidget(logo_label)
        brand_row.addStretch()

        self.login_theme_btn = QToolButton()
        self.login_theme_btn.setFixedSize(38, 38)
        self.login_theme_btn.setIconSize(QSize(19, 19))
        self.login_theme_btn.setCursor(Qt.PointingHandCursor)
        self.login_theme_btn.setToolTip("切换浅色或深色主题")
        self.login_theme_btn.clicked.connect(self._toggle_theme)
        brand_row.addWidget(self.login_theme_btn, 0, Qt.AlignTop)
        login_layout.addLayout(brand_row)

        self.login_title = QLabel("YNU 选课助手 Pro")
        self.login_title.setObjectName("brandTitle")
        login_layout.addWidget(self.login_title)
        self.login_subtitle = QLabel("云南大学选课辅助工具")
        self.login_subtitle.setObjectName("brandSubtitle")
        login_layout.addWidget(self.login_subtitle)
        login_layout.addSpacing(12)

        self.username_field = LoginInputFrame("user", "学号")
        self.username_input = self.username_field.line_edit
        self.username_input.returnPressed.connect(lambda: self.password_input.setFocus())
        login_layout.addWidget(self.username_field)

        self.password_field = LoginInputFrame("lock", "密码", password=True)
        self.password_input = self.password_field.line_edit
        self.password_eye_action = self.password_field.eye_button
        self.password_eye_action.setIcon(icon("eye-off", Colors.OVERLAY0, 26))
        self.password_eye_action.clicked.connect(self._toggle_password_visibility)
        self.password_input.returnPressed.connect(self.on_manual_login_clicked)
        login_layout.addWidget(self.password_field)

        self.login_feedback_label = QLabel("")
        self.login_feedback_label.setObjectName("loginFeedback")
        self.login_feedback_label.setWordWrap(True)
        login_layout.addWidget(self.login_feedback_label)

        self.login_btn = MotionButton("登录")
        self.login_btn.setObjectName("primaryButton")
        self.login_btn.setFixedHeight(52)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self.on_manual_login_clicked)
        login_layout.addWidget(self.login_btn)

        self.login_progress = QProgressBar()
        self.login_progress.setTextVisible(False)
        self.login_progress.setVisible(False)
        login_layout.addWidget(self.login_progress)

        version_label = QLabel(f"YNU选课助手 Pro  {self.VERSION}")
        version_label.setObjectName("mutedLabel")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("font-size: 11px;")
        login_layout.addSpacing(5)
        login_layout.addWidget(version_label)

        shell_layout.addWidget(self.login_frame)
        page_layout.addStretch(1)
        page_layout.addWidget(self.login_shell, 0, Qt.AlignHCenter)
        page_layout.addStretch(1)

    def _build_workspace_page(self):
        self.workspace_page = QWidget()
        self.workspace_page.setObjectName("workspacePage")
        root_layout = QVBoxLayout(self.workspace_page)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("topBar")
        header.setFixedHeight(68)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 14, 10)
        header_layout.setSpacing(9)

        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        app_title = QLabel("YNU 选课助手 Pro")
        app_title.setObjectName("homeTitle")
        title_column.addWidget(app_title)
        self.app_subtitle = QLabel("课程监控工作台")
        self.app_subtitle.setObjectName("mutedLabel")
        self.app_subtitle.setStyleSheet("font-size: 12px;")
        title_column.addWidget(self.app_subtitle)
        header_layout.addLayout(title_column)
        header_layout.addStretch()

        self.batch_label = QLabel("选课批次：自动识别")
        self.batch_label.setObjectName("batchPill")
        header_layout.addWidget(self.batch_label)

        self.status_label = QLabel("未登录")
        self.status_label.setObjectName("statusPill")
        header_layout.addWidget(self.status_label)

        self.curriculum_btn = self._tool_button(
            "calendar-days", "查看我的课表", self._show_curriculum
        )
        self.curriculum_btn.setEnabled(False)
        header_layout.addWidget(self.curriculum_btn)
        self.selected_courses_btn = self._tool_button(
            "list-check", "查看已选课程", self._show_selected_courses
        )
        self.selected_courses_btn.setEnabled(False)
        header_layout.addWidget(self.selected_courses_btn)
        self.workspace_theme_btn = self._tool_button("sun", "切换主题", self._toggle_theme)
        header_layout.addWidget(self.workspace_theme_btn)
        self.notification_btn = self._tool_button("bell", "通知设置", self._show_notification_settings)
        header_layout.addWidget(self.notification_btn)
        self.help_btn = self._tool_button("help", "帮助", self._show_help_popup)
        header_layout.addWidget(self.help_btn)

        self.logout_btn = QPushButton("退出")
        self.logout_btn.setObjectName("secondaryButton")
        self.logout_btn.setIcon(icon("logout", Colors.SUBTEXT0, 17))
        self.logout_btn.setIconSize(QSize(17, 17))
        self.logout_btn.setFixedHeight(38)
        self.logout_btn.setCursor(Qt.PointingHandCursor)
        self.logout_btn.clicked.connect(self.logout)
        self.logout_btn.setEnabled(False)
        header_layout.addWidget(self.logout_btn)
        root_layout.addWidget(header)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)

        self.left_panel = QFrame()
        self.left_panel.setObjectName("panelCard")
        self.left_panel.setMinimumWidth(205)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(16, 16, 16, 14)
        left_layout.setSpacing(10)
        left_layout.addLayout(self._section_header("book", "课程浏览"))

        type_label = QLabel("课程类型")
        type_label.setObjectName("fieldLabel")
        left_layout.addWidget(type_label)
        self.course_type_combo = SpaciousComboBox()
        self.course_type_combo.setFixedHeight(42)
        self.course_type_combo.addItems(list(COURSE_TYPES.keys()))
        self.course_type_combo.currentTextChanged.connect(self.on_course_type_changed)
        left_layout.addWidget(self.course_type_combo)

        search_label = QLabel("搜索课程")
        search_label.setObjectName("fieldLabel")
        left_layout.addWidget(search_label)
        search_layout = QHBoxLayout()
        search_layout.setSpacing(7)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("课程名或教师名")
        self.search_input.setFixedHeight(42)
        self.search_input.addAction(icon("search", Colors.OVERLAY0, 17), QLineEdit.LeadingPosition)
        self.search_input.returnPressed.connect(self.on_search)
        search_layout.addWidget(self.search_input, 1)
        self.search_btn = QPushButton("搜索")
        self.search_btn.setFixedSize(66, 42)
        self.search_btn.clicked.connect(self.on_search)
        search_layout.addWidget(self.search_btn)
        left_layout.addLayout(search_layout)

        self.course_list = QListWidget()
        self._course_list_delegate = FullyVisibleItemDelegate(self.course_list)
        self.course_list.setItemDelegate(self._course_list_delegate)
        self.course_list.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        self.course_list.setUniformItemSizes(True)
        self.course_list.itemClicked.connect(self.on_course_selected)
        left_layout.addWidget(self.course_list, 1)
        self.course_count_label = QLabel("共 0 门课程")
        self.course_count_label.setObjectName("mutedLabel")
        left_layout.addWidget(self.course_count_label)
        self.main_splitter.addWidget(self.left_panel)

        self.middle_panel = QFrame()
        self.middle_panel.setObjectName("panelCard")
        self.middle_panel.setMinimumWidth(310)
        middle_layout = QVBoxLayout(self.middle_panel)
        middle_layout.setContentsMargins(18, 16, 18, 16)
        middle_layout.setSpacing(12)
        self.schedule_title = QLabel("选择课程查看教学班")
        self.schedule_title.setObjectName("sectionTitle")
        middle_layout.addWidget(self.schedule_title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.cards_widget = QWidget()
        self.cards_widget.setObjectName("courseCardsCanvas")
        self.cards_layout = QGridLayout(self.cards_widget)
        self.cards_layout.setSpacing(14)
        self.cards_layout.setContentsMargins(4, 4, 4, 8)
        self.cards_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.cards_widget)
        middle_layout.addWidget(scroll, 1)
        self.main_splitter.addWidget(self.middle_panel)

        self.right_panel = QFrame()
        self.right_panel.setObjectName("panelCard")
        self.right_panel.setMinimumWidth(310)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(16, 16, 16, 14)
        right_layout.setSpacing(9)
        right_layout.addLayout(self._section_header("target", "待抢与监控"))

        self.grab_list = GrabListWidget()
        self.grab_list.setMinimumHeight(160)
        self.grab_list.setMaximumHeight(300)
        self.grab_list.setContextMenuPolicy(Qt.NoContextMenu)
        self.grab_list.model().rowsInserted.connect(
            lambda *_args: QTimer.singleShot(0, self._update_grab_list_height)
        )
        self.grab_list.model().rowsRemoved.connect(
            lambda *_args: QTimer.singleShot(0, self._update_grab_list_height)
        )
        self.grab_list.remove_requested.connect(self._remove_grab_item)
        right_layout.addWidget(self.grab_list)
        self.grab_count_label = QLabel("待抢 0 门")
        self.grab_count_label.setObjectName("mutedLabel")
        right_layout.addWidget(self.grab_count_label)

        concurrency_frame = QFrame()
        concurrency_frame.setObjectName("softCard")
        concurrency_layout = QHBoxLayout(concurrency_frame)
        concurrency_layout.setContentsMargins(12, 8, 10, 8)
        concurrency_label = QLabel("HTTP 并发数")
        concurrency_label.setObjectName("fieldLabel")
        concurrency_layout.addWidget(concurrency_label)
        concurrency_layout.addStretch()
        self.concurrency_spin = InlineSpinBox()
        self.concurrency_spin.setRange(1, 20)
        self.concurrency_spin.setValue(5)
        self.concurrency_spin.setFixedSize(116, 38)
        self.concurrency_spin.setToolTip("同时进行的网络请求数量，建议 3 到 10")
        concurrency_layout.addWidget(self.concurrency_spin)
        right_layout.addWidget(concurrency_frame)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.start_grab_btn = MotionButton("开始监控")
        self.start_grab_btn.setObjectName("successButton")
        self.start_grab_btn.setIcon(icon("play", "#FFFFFF", 17))
        self.start_grab_btn.setFixedHeight(42)
        self.start_grab_btn.clicked.connect(lambda _=False: self.start_monitoring())
        buttons.addWidget(self.start_grab_btn)
        self.stop_grab_btn = QPushButton("停止")
        self.stop_grab_btn.setObjectName("dangerButton")
        self.stop_grab_btn.setIcon(icon("stop", "#FFFFFF", 16))
        self.stop_grab_btn.setFixedHeight(42)
        self.stop_grab_btn.clicked.connect(lambda _=False: self.stop_monitoring())
        self.stop_grab_btn.setEnabled(False)
        buttons.addWidget(self.stop_grab_btn)
        right_layout.addLayout(buttons)

        log_header = QHBoxLayout()
        log_icon = QLabel()
        log_icon.setPixmap(icon("terminal", Colors.SUBTEXT0, 18).pixmap(18, 18))
        log_header.addWidget(log_icon)
        log_title = QLabel("运行日志")
        log_title.setObjectName("sectionTitle")
        log_header.addWidget(log_title)
        log_header.addStretch()
        self.clear_log_btn = self._tool_button("trash", "清空日志", self._clear_log)
        self.clear_log_btn.setFixedSize(32, 32)
        log_header.addWidget(self.clear_log_btn)
        right_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setObjectName("logConsole")
        self.log_text.setReadOnly(True)
        self.log_text.document().setMaximumBlockCount(600)
        right_layout.addWidget(self.log_text, 1)
        self.main_splitter.addWidget(self.right_panel)

        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([270, 620, 350])
        root_layout.addWidget(self.main_splitter, 1)

    def _build_notification_dialog(self):
        self._notification_dialog = self._prepare_dialog(QDialog(self))
        self._notification_dialog.setWindowTitle("通知设置")
        self._notification_dialog.setFixedWidth(480)
        layout = QVBoxLayout(self._notification_dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        title = QLabel("通知设置")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        hint = QLabel("配置 Server酱后，发现余量和选课结果可发送到微信。")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addSpacing(6)
        self.serverchan_checkbox = QCheckBox("启用微信通知（Server酱）")
        self.serverchan_checkbox.stateChanged.connect(self._on_serverchan_toggled)
        layout.addWidget(self.serverchan_checkbox)
        self.serverchan_key_input = QLineEdit()
        self.serverchan_key_input.setPlaceholderText("SendKey")
        self.serverchan_key_input.setEchoMode(QLineEdit.Password)
        self.serverchan_key_input.setFixedHeight(42)
        self.serverchan_key_input.setVisible(False)
        layout.addWidget(self.serverchan_key_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._save_notification_settings)
        buttons.rejected.connect(self._notification_dialog.reject)
        layout.addWidget(buttons)

    def _section_header(self, icon_name, title):
        layout = QHBoxLayout()
        layout.setSpacing(8)
        icon_label = QLabel()
        icon_label.setPixmap(icon(icon_name, Colors.BLUE, 19).pixmap(19, 19))
        icon_label.setFixedSize(20, 20)
        layout.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(title_label)
        layout.addStretch()
        return layout

    def _tool_button(self, icon_name, tooltip, callback):
        button = QToolButton()
        button.setIcon(icon(icon_name, Colors.SUBTEXT0, 18))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(36, 36)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        button.setProperty("icon_name", icon_name)
        return button

    def _fade_in_workspace(self):
        if self.app_stack.currentWidget() is self.workspace_page:
            self.login_page.set_active(False)
            self.statusBar().setVisible(True)
            return

        overlay = QFrame(self.app_stack)
        overlay.setObjectName("pageTransitionOverlay")
        overlay.setGeometry(self.app_stack.rect())
        overlay.setStyleSheet(f"background-color: {Colors.BASE}; border: none;")
        overlay.show()
        overlay.raise_()

        self.app_stack.setUpdatesEnabled(False)
        self.app_stack.setCurrentWidget(self.workspace_page)
        self.app_stack.setUpdatesEnabled(True)
        self.login_page.set_active(False)
        self.statusBar().setVisible(False)

        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        effect.setOpacity(1.0)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(320)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda: self._finish_transition_overlay(overlay))
        self._transition_overlay = overlay
        self._workspace_animation = animation
        animation.start()

    def _finish_transition_overlay(self, overlay):
        if getattr(self, '_transition_overlay', None) is overlay:
            self._transition_overlay = None
        self.statusBar().setVisible(True)
        overlay.deleteLater()

    def _show_login_page(self):
        self.app_stack.setCurrentWidget(self.login_page)
        self.login_page.set_active(True)
        self.statusBar().setVisible(False)
        self.login_feedback_label.clear()

    def _toggle_password_visibility(self):
        visible = self.password_input.echoMode() == QLineEdit.Normal
        self.password_input.setEchoMode(QLineEdit.Password if visible else QLineEdit.Normal)
        now_visible = self.password_input.echoMode() == QLineEdit.Normal
        self.password_field._apply_password_spacing()
        self.password_eye_action.setIcon(
            icon("eye" if now_visible else "eye-off", Colors.OVERLAY0, 26)
        )

    def _toggle_theme(self):
        self.theme_mode = 'dark' if self.theme_mode == 'light' else 'light'
        apply_palette(self.theme_mode)
        shared_stylesheet = build_stylesheet(self.theme_mode)
        self.setStyleSheet(shared_stylesheet)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_tooltip_stylesheet(self.theme_mode))
        QTimer.singleShot(0, self._apply_crisp_fonts)
        self._refresh_icons()
        for field in (
            getattr(self, 'username_field', None),
            getattr(self, 'password_field', None),
        ):
            if field:
                field.apply_theme()
        selected_item = self.course_list.currentItem() if hasattr(self, 'course_list') else None
        if selected_item and selected_item.data(Qt.UserRole) in self._api_courses_grouped:
            self.on_course_selected(selected_item)
        else:
            for card in self.findChildren(CourseCard):
                card.apply_theme()
        if self.is_logged_in:
            self.status_label.setStyleSheet(
                f"color: {Colors.GREEN}; background-color: {Colors.SURFACE1}; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 16px; "
                "padding: 7px 13px; font-size: 13px; font-weight: 700;"
            )
        elif hasattr(self, 'status_label'):
            self.status_label.setStyleSheet("")
        self._refresh_grab_item_visuals()
        self.save_config()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        overlay = getattr(self, '_transition_overlay', None)
        if overlay is not None and overlay.isVisible():
            overlay.setGeometry(self.app_stack.rect())
        if hasattr(self, '_responsive_timer'):
            self._responsive_timer.start()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Show and isinstance(watched, QWidget):
            self._polish_widget_font(watched)
        if event.type() in (QEvent.Show, QEvent.Enter) and isinstance(
            watched, QAbstractButton
        ):
            if not watched.toolTip():
                text = str(watched.text() or '').replace('&', '').strip()
                if not text and watched.objectName() == 'loginEyeButton':
                    text = "显示或隐藏密码"
                watched.setToolTip(text or "执行此操作")
        return super().eventFilter(watched, event)

    @staticmethod
    def _polish_widget_font(widget):
        """Restore the real font face and hinting after Qt applies QSS."""
        app = QApplication.instance()
        # Empty Qt item views evaluate to False, so use an identity check.
        if app is None or widget is None:
            return
        base = app.font()
        current = widget.font()
        if isinstance(widget, QAbstractItemView):
            current.setFamily(base.family())
            current.setPixelSize(base.pixelSize())
            current.setWeight(base.weight())
        current.setHintingPreference(QFont.PreferFullHinting)
        widget.setFont(current)

    def _apply_crisp_fonts(self):
        self._polish_widget_font(self)
        for widget in self.findChildren(QWidget):
            self._polish_widget_font(widget)

    def _apply_responsive_layout(self):
        if not hasattr(self, 'main_splitter'):
            return

        window_width = max(1, self.width())
        shell_width = max(490, min(560, int(window_width * 0.43)))
        self.login_shell.setFixedWidth(shell_width)

        compact_header = window_width < 1180
        self.batch_label.setVisible(not compact_header)
        self.app_subtitle.setVisible(window_width >= 1060)

        if window_width < 1080:
            layout_band = "compact"
            left_width, right_width = 210, 330
        elif window_width < 1480:
            layout_band = "regular"
            left_width, right_width = 250, 420
        else:
            layout_band = "wide"
            left_width, right_width = 270, 470

        # Only reset panel widths when crossing a responsive breakpoint.  A
        # maximized window therefore expands the centre workspace rather than
        # making every side control look oversized, and manual splitter
        # adjustments are preserved within the current breakpoint.
        if getattr(self, '_responsive_layout_band', None) != layout_band:
            available = max(1, self.main_splitter.width() - 20)
            middle_width = max(300, available - left_width - right_width)
            self.main_splitter.setSizes([left_width, middle_width, right_width])
            self._responsive_layout_band = layout_band
        self._update_grab_list_height()
        self._relayout_course_cards()

    def _update_grab_list_height(self):
        """Show as much of the watch list as the current window can afford."""
        if not hasattr(self, 'grab_list'):
            return
        available_height = max(190, min(320, int(self.height() * 0.36)))
        content_height = max(160, min(320, 16 + self.grab_list.count() * 54))
        target_height = min(available_height, content_height)
        self.grab_list.setMinimumHeight(target_height)
        self.grab_list.setMaximumHeight(available_height)

    def _course_card_columns(self):
        return 2 if getattr(self, 'middle_panel', None) and self.middle_panel.width() >= 660 else 1

    def _relayout_course_cards(self):
        if not hasattr(self, 'cards_layout') or self.cards_layout.count() == 0:
            return
        widgets = []
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widgets.append(widget)
        columns = self._course_card_columns()
        for index, widget in enumerate(widgets):
            self.cards_layout.addWidget(widget, index // columns, index % columns)

    def _refresh_icons(self):
        theme_icon = "sun" if self.theme_mode == "dark" else "moon"
        for button in (getattr(self, 'login_theme_btn', None), getattr(self, 'workspace_theme_btn', None)):
            if button:
                button.setIcon(icon(theme_icon, Colors.BLUE, 19))
        for button in self.findChildren(QToolButton):
            icon_name = button.property("icon_name")
            if icon_name and button not in (self.login_theme_btn, self.workspace_theme_btn):
                button.setIcon(icon(icon_name, Colors.SUBTEXT0, 18))
        if hasattr(self, 'logout_btn'):
            self.logout_btn.setIcon(icon("logout", Colors.SUBTEXT0, 17))
        if hasattr(self, 'password_eye_action'):
            visible = self.password_input.echoMode() == QLineEdit.Normal
            self.password_eye_action.setIcon(icon("eye" if visible else "eye-off", Colors.OVERLAY0, 26))
        for attr, name in (
            ('update_action', 'refresh'),
            ('developer_action', 'code'),
            ('about_action', 'info'),
        ):
            action = getattr(self, attr, None)
            if action:
                action.setIcon(icon(name, Colors.SUBTEXT0, 17))

    def _show_notification_settings(self):
        previous_enabled = self.serverchan_enabled
        previous_key = self.serverchan_key
        self.serverchan_checkbox.setChecked(previous_enabled)
        self.serverchan_key_input.setText(self.serverchan_key)
        self.serverchan_key_input.setVisible(self.serverchan_checkbox.isChecked())
        result = self._notification_dialog.exec_()
        if result != QDialog.Accepted:
            self.serverchan_enabled = previous_enabled
            self.serverchan_key = previous_key
            self.serverchan_checkbox.blockSignals(True)
            self.serverchan_checkbox.setChecked(previous_enabled)
            self.serverchan_checkbox.blockSignals(False)
            self.serverchan_key_input.setText(previous_key)
            self.serverchan_key_input.setVisible(previous_enabled)

    def _prefetch_curriculum(self, force=False):
        """Warm or refresh the curriculum cache without blocking the UI."""
        if not self.is_logged_in or not all(
            (self.token, self.cookies, self.student_code, self.batch_code)
        ):
            return False
        if self._curriculum_worker and self._curriculum_worker.isRunning():
            if force:
                self._curriculum_refresh_pending = True
            return False

        self._curriculum_refresh_pending = False
        token_snapshot = self.token
        cookies_snapshot = self.cookies
        worker = CurriculumFetchWorker(
            token_snapshot, cookies_snapshot, self.student_code, self.batch_code
        )
        self._curriculum_worker = worker

        def loaded(arranged, unarranged, error):
            # Ignore a response belonging to a session that has since changed.
            if (
                not self.is_logged_in
                or self.token != token_snapshot
                or self.cookies != cookies_snapshot
            ):
                return
            if not error:
                self._curriculum_arranged = list(arranged)
                self._curriculum_unarranged = list(unarranged)
                self._curriculum_loaded = True
                self._curriculum_error = ''
            else:
                self._curriculum_error = str(error)
            self.curriculum_updated.emit(
                list(self._curriculum_arranged),
                list(self._curriculum_unarranged),
                str(error or ''),
            )

        def thread_finished():
            if self._curriculum_worker is worker:
                self._curriculum_worker = None
            if self._curriculum_refresh_pending and self.is_logged_in:
                self._curriculum_refresh_pending = False
                QTimer.singleShot(80, lambda: self._prefetch_curriculum(force=True))

        worker.result.connect(loaded)
        worker.finished.connect(thread_finished)
        worker.start()
        return True

    def _start_pending_curriculum_prefetch(self):
        """Warm the timetable only after the login page's first course request."""
        if not self._curriculum_prefetch_waiting:
            return
        self._curriculum_prefetch_waiting = False
        self._prefetch_curriculum(force=True)

    @staticmethod
    def _curriculum_unique_count(arranged, unarranged):
        identities = set()
        for course in list(arranged) + list(unarranged):
            identity = (
                course.get('teachingClassID')
                or course.get('courseNumber')
                or course.get('courseName')
                or id(course)
            )
            identities.add(str(identity))
        return len(identities)

    def _show_curriculum(self):
        """Open the themed curriculum view, using the login-time cache first."""
        if not self.is_logged_in or not all(
            (self.token, self.cookies, self.student_code, self.batch_code)
        ):
            self._show_centered_message(
                QMessageBox.Information,
                "查看课表",
                "请先登录后再查看课表。",
            )
            return

        dialog = self._prepare_dialog(QDialog(self))
        dialog.setWindowTitle("我的课表")
        dialog.setModal(True)
        dialog.setStyleSheet(build_stylesheet(self.theme_mode))
        screen = QApplication.primaryScreen().availableGeometry()
        dialog.setMinimumSize(
            min(900, screen.width() - 70), min(620, screen.height() - 70)
        )
        dialog.resize(min(1320, screen.width() - 70), min(820, screen.height() - 70))

        root = QVBoxLayout(dialog)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
        mark = VectorIconWidget("calendar", Colors.BLUE, 36)
        header.addWidget(mark, 0, Qt.AlignTop)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        title = QLabel("我的课表")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        subtitle = QLabel(self.batch_name or "当前选课批次")
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.setIcon(icon("refresh", Colors.SUBTEXT0, 16))
        refresh_button.setFixedHeight(38)
        header.addWidget(refresh_button, 0, Qt.AlignTop)
        close_button = QPushButton("关闭")
        close_button.setObjectName("secondaryButton")
        close_button.setFixedHeight(38)
        close_button.clicked.connect(dialog.accept)
        header.addWidget(close_button, 0, Qt.AlignTop)
        root.addLayout(header)

        state_card = QFrame()
        state_card.setObjectName("softCard")
        state_layout = QVBoxLayout(state_card)
        state_layout.setContentsMargins(22, 32, 22, 32)
        state_layout.setSpacing(12)
        state_icon = VectorIconWidget("calendar-days", Colors.BLUE, 42)
        state_layout.addWidget(state_icon, 0, Qt.AlignHCenter)
        state_text = QLabel("正在从选课系统同步课表…")
        state_text.setAlignment(Qt.AlignCenter)
        state_text.setObjectName("sectionTitle")
        state_layout.addWidget(state_text)
        root.addWidget(state_card, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVisible(False)
        root.addWidget(scroll, 1)

        def render(arranged, unarranged, error=''):
            has_cache = self._curriculum_loaded
            if has_cache:
                scroll.setWidget(self._build_curriculum_canvas(arranged, unarranged))
                state_card.setVisible(False)
                scroll.setVisible(True)
                suffix = " · 刷新失败，正在显示已缓存课表" if error else ""
                subtitle.setText(
                    f"{self.batch_name or '当前选课批次'} · "
                    f"共 {self._curriculum_unique_count(arranged, unarranged)} 门课程{suffix}"
                )
            elif error:
                state_icon.set_icon("alert-triangle", Colors.RED)
                state_text.setStyleSheet(f"color: {Colors.RED};")
                state_text.setText(error)
                state_card.setVisible(True)
                scroll.setVisible(False)
            refresh_button.setEnabled(True)

        def refresh():
            refresh_button.setEnabled(False)
            if not self._curriculum_loaded:
                state_icon.set_icon("refresh", Colors.BLUE)
                state_text.setStyleSheet("")
                state_text.setText("正在从选课系统同步课表…")
                state_card.setVisible(True)
                scroll.setVisible(False)
            self._prefetch_curriculum(force=True)

        refresh_button.clicked.connect(refresh)
        self.curriculum_updated.connect(render)
        self._curriculum_dialog = dialog
        if self._curriculum_loaded:
            render(self._curriculum_arranged, self._curriculum_unarranged)
        else:
            refresh_button.setEnabled(False)
            self._prefetch_curriculum()
        try:
            dialog.exec_()
        finally:
            try:
                self.curriculum_updated.disconnect(render)
            except (TypeError, RuntimeError):
                pass
            self._curriculum_dialog = None

    def _build_curriculum_canvas(self, arranged, unarranged):
        canvas = QWidget()
        canvas.setObjectName("curriculumCanvas")
        canvas.setMinimumWidth(0)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(2, 2, 8, 8)
        layout.setSpacing(16)

        overview = QLabel(
            f"已排时间课程 {len(arranged)} 条"
            + (f" · 未安排时间 {len(unarranged)} 门" if unarranged else "")
        )
        overview.setObjectName("mutedLabel")
        layout.addWidget(overview)

        grid_frame = QFrame()
        grid_frame.setObjectName("scheduleGrid")
        grid_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(7)

        headers = ["节次", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("scheduleHeader")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedHeight(40)
            if column == 0:
                label.setFixedWidth(68)
            else:
                label.setMinimumWidth(0)
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                grid.setColumnStretch(column, 1)
            grid.addWidget(label, 0, column)

        grouped = {}
        for course in arranged:
            try:
                day = min(7, max(1, int(course.get('dayOfWeek', 0))))
                begin = min(12, max(1, int(course.get('beginSection', 1))))
            except (TypeError, ValueError):
                continue
            row = min(5, (begin - 1) // 2)
            grouped.setdefault((row, day), []).append(course)

        section_names = ["1–2节", "3–4节", "5–6节", "7–8节", "9–10节", "11–12节"]
        for row, section_name in enumerate(section_names, start=1):
            section = QLabel(section_name)
            section.setObjectName("scheduleSection")
            section.setAlignment(Qt.AlignCenter)
            section.setFixedHeight(134)
            grid.addWidget(section, row, 0)
            for day in range(1, 8):
                cell = QFrame()
                cell.setObjectName("scheduleCell")
                cell.setFixedHeight(134)
                cell.setMinimumWidth(0)
                cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                cell_layout = QVBoxLayout(cell)
                cell_layout.setContentsMargins(5, 5, 5, 5)
                cell_layout.setSpacing(4)
                courses = grouped.get((row - 1, day), [])
                for index, course in enumerate(courses):
                    cell_layout.addWidget(
                        self._curriculum_course_card(course, index), 1
                    )
                if not courses:
                    cell_layout.addStretch(1)
                grid.addWidget(cell, row, day)
        layout.addWidget(grid_frame)

        if unarranged:
            unarranged_title = self._section_header("calendar-days", "未安排时间课程")
            layout.addLayout(unarranged_title)
            unarranged_frame = QFrame()
            unarranged_frame.setObjectName("softCard")
            unarranged_grid = QGridLayout(unarranged_frame)
            unarranged_grid.setContentsMargins(12, 12, 12, 12)
            unarranged_grid.setSpacing(10)
            for index, course in enumerate(unarranged):
                unarranged_grid.setColumnStretch(index % 3, 1)
                unarranged_grid.addWidget(
                    self._curriculum_course_card(course, index), index // 3, index % 3
                )
            layout.addWidget(unarranged_frame)
        layout.addStretch(1)
        return canvas

    def _curriculum_course_card(self, course, color_index=0):
        accents = [Colors.BLUE, Colors.GREEN, Colors.MAUVE, Colors.YELLOW, Colors.RED]
        accent = accents[color_index % len(accents)]
        card = AnimatedScheduleCard(accent)
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.setToolTip("\n".join(filter(None, (
            str(course.get('courseName') or ''),
            str(course.get('teacherName') or ''),
            str(course.get('teachingPlace') or ''),
            str(course.get('weekName') or ''),
        ))))
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(9, 7, 9, 10)
        card_layout.setSpacing(3)
        name = str(course.get('courseName') or '未命名课程')
        sport_name = str(course.get('sportName') or '').strip()
        if sport_name:
            name = f"{name} · {sport_name}"
        name_label = QLabel(name)
        name_label.setWordWrap(True)
        name_label.setMinimumWidth(0)
        name_label.setStyleSheet("font-size: 12px; font-weight: 750;")
        card_layout.addWidget(name_label)
        teacher = str(course.get('teacherName') or '').strip()
        place = str(course.get('teachingPlace') or '').strip()
        detail = " · ".join(value for value in (teacher, place) if value)
        if detail:
            detail_label = QLabel(detail)
            detail_label.setWordWrap(True)
            detail_label.setMinimumWidth(0)
            detail_label.setStyleSheet(
                f"color: {Colors.SUBTEXT0}; font-size: 10px; font-weight: 550;"
            )
            card_layout.addWidget(detail_label)
        begin = str(course.get('beginSection') or '').strip()
        end = str(course.get('endSection') or '').strip()
        week = str(course.get('weekName') or '').strip()
        timing = " · ".join(
            value for value in ((f"{begin}–{end}节" if begin and end else ""), week) if value
        )
        if timing:
            timing_label = QLabel(timing)
            timing_label.setWordWrap(True)
            timing_label.setMinimumWidth(0)
            timing_label.setStyleSheet(f"color: {accent}; font-size: 10px; font-weight: 650;")
            card_layout.addWidget(timing_label)
        return card

    @staticmethod
    def _selected_course_id(course):
        return str(
            course.get('teachingClassID')
            or course.get('JXBID')
            or course.get('tcId')
            or ''
        )

    def _selected_course_schedule(self, course):
        tc_id = self._selected_course_id(course)
        day_names = {'1': '周一', '2': '周二', '3': '周三', '4': '周四',
                     '5': '周五', '6': '周六', '7': '周日'}
        entries = []
        for item in self._curriculum_arranged:
            if self._selected_course_id(item) != tc_id:
                continue
            day = day_names.get(str(item.get('dayOfWeek') or ''), '')
            begin = str(item.get('beginSection') or '')
            end = str(item.get('endSection') or '')
            week = str(item.get('weekName') or '')
            place = str(item.get('teachingPlace') or '')
            text = ' · '.join(filter(None, (
                day,
                f"{begin}–{end}节" if begin and end else '',
                week,
                place,
            )))
            if text and text not in entries:
                entries.append(text)
        return '；'.join(entries)

    def _show_selected_courses(self):
        if self._selected_courses_worker and self._selected_courses_worker.isRunning():
            self._show_centered_message(
                QMessageBox.Information, "已选课程", "已选课程正在加载，请稍候。"
            )
            return
        if not self.is_logged_in or not all(
            (self.token, self.cookies, self.student_code, self.batch_code)
        ):
            self._show_centered_message(
                QMessageBox.Information, "已选课程", "请先登录后再查看已选课程。"
            )
            return

        dialog = self._prepare_dialog(QDialog(self))
        dialog.setWindowTitle("已选课程")
        dialog.setModal(True)
        dialog.setStyleSheet(build_stylesheet(self.theme_mode))
        dialog.setMinimumSize(720, 520)
        screen = QApplication.primaryScreen().availableGeometry()
        dialog.resize(min(920, screen.width() - 70), min(720, screen.height() - 70))
        root = QVBoxLayout(dialog)
        root.setContentsMargins(22, 18, 22, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(11)
        marker = VectorIconWidget("list-check", Colors.BLUE, 36)
        header.addWidget(marker, 0, Qt.AlignTop)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel("已选课程")
        title.setObjectName("pageTitle")
        title_row.addWidget(title)
        total_credit_label = QLabel("总学分 --")
        total_credit_label.setObjectName("creditBadge")
        total_credit_label.setToolTip("正在统计当前已选课程学分")
        title_row.addWidget(total_credit_label)
        title_row.addStretch(1)
        heading.addLayout(title_row)
        subtitle = QLabel("查看当前批次已选结果；手动退选不可自动回滚")
        subtitle.setObjectName("mutedLabel")
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        refresh_button = QPushButton("刷新")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.setIcon(icon("refresh", Colors.SUBTEXT0, 16))
        refresh_button.setFixedHeight(38)
        header.addWidget(refresh_button, 0, Qt.AlignTop)
        close_button = QPushButton("关闭")
        close_button.setObjectName("secondaryButton")
        close_button.setFixedHeight(38)
        close_button.clicked.connect(dialog.accept)
        header.addWidget(close_button, 0, Qt.AlignTop)
        root.addLayout(header)

        state_card = QFrame()
        state_card.setObjectName("softCard")
        state_layout = QVBoxLayout(state_card)
        state_layout.setContentsMargins(20, 34, 20, 34)
        state_icon = VectorIconWidget("refresh", Colors.BLUE, 40)
        state_layout.addWidget(state_icon, 0, Qt.AlignHCenter)
        state_text = QLabel("正在获取已选课程…")
        state_text.setObjectName("sectionTitle")
        state_text.setAlignment(Qt.AlignCenter)
        state_layout.addWidget(state_text)
        root.addWidget(state_card, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVisible(False)
        root.addWidget(scroll, 1)

        def load():
            if self._selected_courses_worker and self._selected_courses_worker.isRunning():
                return
            refresh_button.setEnabled(False)
            state_icon.set_icon("refresh", Colors.BLUE)
            state_text.setStyleSheet("")
            state_text.setText("正在获取已选课程…")
            state_card.setVisible(True)
            scroll.setVisible(False)
            worker = SelectedCoursesWorker(
                self.token, self.cookies, self.student_code, self.batch_code
            )
            self._selected_courses_worker = worker

            def loaded(courses, error):
                refresh_button.setEnabled(True)
                if error:
                    state_icon.set_icon("alert-triangle", Colors.RED)
                    state_text.setStyleSheet(f"color: {Colors.RED};")
                    state_text.setText(error)
                    return
                total_credit, missing_credit = self._selected_courses_credit_total(courses)
                if missing_credit:
                    total_credit_label.setText(
                        f"已识别 {self._format_credit(total_credit)} 学分"
                    )
                    total_credit_label.setToolTip(
                        f"有 {missing_credit} 门课程未返回学分，未计入当前合计"
                    )
                else:
                    total_credit_label.setText(
                        f"总学分 {self._format_credit(total_credit)}"
                    )
                    total_credit_label.setToolTip(
                        f"当前 {len(courses)} 门已选课程的学分合计"
                    )
                subtitle.setText(f"当前共 {len(courses)} 门已选课程 · 手动退选不可自动回滚")
                scroll.setWidget(self._build_selected_courses_canvas(courses, load))
                state_card.setVisible(False)
                scroll.setVisible(True)

            def finished():
                if self._selected_courses_worker is worker:
                    self._selected_courses_worker = None

            worker.result.connect(loaded)
            worker.finished.connect(finished)
            worker.start()

        refresh_button.clicked.connect(load)
        self._selected_courses_dialog = dialog
        load()
        dialog.exec_()
        self._selected_courses_dialog = None

    @staticmethod
    def _selected_course_credit(course):
        """Return a credit value without treating a missing field as zero."""
        if not isinstance(course, dict):
            return None
        sources = [course]
        for key in ('course', 'courseInfo', 'teachingClass', 'teachingClassInfo'):
            nested = course.get(key)
            if isinstance(nested, dict):
                sources.append(nested)
        keys = {
            'coursecredit', 'coursecredits', 'credit', 'credits',
            'xf', 'kcxf', 'xuefen', 'courseunit',
        }
        for source in sources:
            # The same endpoint has used differently-cased field names across
            # deployments, so match keys case-insensitively without guessing
            # from unrelated numeric fields such as scores or class hours.
            for key, value in source.items():
                if str(key).replace('_', '').lower() not in keys:
                    continue
                if value is None or isinstance(value, bool):
                    continue
                match = re.search(r'\d+(?:\.\d+)?', str(value).strip())
                if not match:
                    continue
                number = float(match.group())
                if 0 <= number <= 30:
                    return number
        return None

    @staticmethod
    def _format_credit(value):
        number = float(value or 0)
        return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip('0')

    def _selected_courses_credit_total(self, courses):
        credits = [self._selected_course_credit(course) for course in courses]
        known = [value for value in credits if value is not None]
        return sum(known), len(credits) - len(known)

    def _build_selected_courses_canvas(self, courses, reload_callback):
        canvas = QWidget()
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(2, 2, 8, 8)
        layout.setSpacing(10)
        if not courses:
            empty = QLabel("当前批次没有已选课程")
            empty.setObjectName("mutedLabel")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(180)
            layout.addWidget(empty)
            return canvas

        for course in courses:
            card = QFrame()
            card.setObjectName("selectedCourseCard")
            card.setAttribute(Qt.WA_Hover, True)
            row = QHBoxLayout(card)
            row.setContentsMargins(16, 13, 12, 13)
            row.setSpacing(14)
            info = QVBoxLayout()
            info.setSpacing(4)
            name = str(course.get('courseName') or course.get('KCM') or '未知课程')
            name_row = QHBoxLayout()
            name_row.setSpacing(9)
            name_label = QLabel(name)
            name_label.setWordWrap(True)
            name_label.setStyleSheet("font-size: 15px; font-weight: 750;")
            name_row.addWidget(name_label)
            credit = self._selected_course_credit(course)
            credit_badge = QLabel(
                f"学分 {self._format_credit(credit)}" if credit is not None else "学分 --"
            )
            credit_badge.setObjectName("courseCreditBadge")
            credit_badge.setToolTip(
                "该课程学分" if credit is not None else "服务器未返回该课程的学分字段"
            )
            name_row.addWidget(credit_badge, 0, Qt.AlignVCenter)
            name_row.addStretch(1)
            info.addLayout(name_row)
            teacher = str(course.get('teacherName') or course.get('SKJS') or '').strip()
            course_type = str(
                course.get('courseTypeName') or course.get('courseNatureName') or ''
            ).strip()
            number = str(course.get('courseNumber') or '').strip()
            meta = ' · '.join(filter(None, (teacher, course_type, number)))
            if meta:
                meta_label = QLabel(meta)
                meta_label.setWordWrap(True)
                meta_label.setStyleSheet(
                    f"color: {Colors.SUBTEXT0}; font-size: 12px; font-weight: 550;"
                )
                info.addWidget(meta_label)
            schedule = self._selected_course_schedule(course)
            if schedule:
                schedule_label = QLabel(schedule)
                schedule_label.setWordWrap(True)
                schedule_label.setStyleSheet(
                    f"color: {Colors.SUBTEXT1}; font-size: 12px; font-weight: 550;"
                )
                info.addWidget(schedule_label)
            row.addLayout(info, 1)
            withdraw = QPushButton("退选")
            withdraw.setObjectName("dangerButton")
            withdraw.setIcon(icon("trash", "#FFFFFF", 15))
            withdraw.setFixedSize(92, 38)
            withdraw.setCursor(Qt.PointingHandCursor)
            withdraw.setToolTip("退选此课程（操作不可自动回滚）")
            withdraw.clicked.connect(
                lambda _checked=False, selected=course, button=withdraw:
                self._withdraw_selected_course(selected, button, reload_callback)
            )
            row.addWidget(withdraw, 0, Qt.AlignVCenter)
            layout.addWidget(card)
        layout.addStretch(1)
        return canvas

    def _withdraw_selected_course(self, course, button, reload_callback):
        if self.multi_grab_worker and self.multi_grab_worker.isRunning():
            self._show_centered_message(
                QMessageBox.Warning,
                "监控运行中",
                "为避免与换课或回滚请求发生竞态，请先停止监控，再手动退选。",
            )
            return
        if self._withdraw_course_worker and self._withdraw_course_worker.isRunning():
            self._show_centered_message(
                QMessageBox.Information, "正在退选", "已有一项退选操作正在核实，请稍候。"
            )
            return

        name = str(course.get('courseName') or course.get('KCM') or '未知课程')
        reply = self._show_centered_message(
            QMessageBox.Warning,
            "确认退选",
            f"确定退选“{name}”吗？\n\n"
            "这是主动退选操作，成功后不会自动回滚，也不能保证课程仍有名额可重新选回。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
            yes_text="确认退选",
            no_text="取消",
        )
        if reply != QMessageBox.Yes:
            self.log(f"[退选] 用户取消：{name}")
            return

        button.setEnabled(False)
        button.setText("核实中…")
        self.log(f"[退选] 用户确认退选：{name}")
        worker = WithdrawCourseWorker(
            self.token, self.cookies, self.student_code, self.batch_code, course
        )
        self._withdraw_course_worker = worker
        worker.status.connect(self.log)

        def completed(success, message, selected):
            button.setEnabled(True)
            button.setText("退选")
            tc_id = self._selected_course_id(selected)
            if success:
                self.log(f"[SUCCESS] 退选成功并完成核实：{name}（{tc_id}）")
                self._curriculum_arranged = [
                    item for item in self._curriculum_arranged
                    if self._selected_course_id(item) != tc_id
                ]
                self._curriculum_unarranged = [
                    item for item in self._curriculum_unarranged
                    if self._selected_course_id(item) != tc_id
                ]
                self.curriculum_updated.emit(
                    self._curriculum_arranged, self._curriculum_unarranged, ''
                )
                self._show_centered_message(
                    QMessageBox.Information,
                    "退选成功",
                    f"{name}\n\n已从服务器已选列表中核实移除。",
                    icon_name_override="circle-check",
                    icon_color_override=Colors.GREEN,
                )
                QTimer.singleShot(100, lambda: self._prefetch_curriculum(force=True))
                QTimer.singleShot(350, lambda: self.refresh_courses(silent=True, force=True))
            else:
                self.log(f"[ERROR] 退选未确认成功：{name}；{message}")
                self._show_centered_message(
                    QMessageBox.Warning, "退选结果", f"{name}\n\n{message}"
                )
            if self._selected_courses_dialog and self._selected_courses_dialog.isVisible():
                QTimer.singleShot(120, reload_callback)

        def finished():
            if self._withdraw_course_worker is worker:
                self._withdraw_course_worker = None

        worker.result.connect(completed)
        worker.finished.connect(finished)
        worker.start()

    def _save_notification_settings(self):
        self.serverchan_enabled = self.serverchan_checkbox.isChecked()
        self.serverchan_key = self.serverchan_key_input.text().strip() if self.serverchan_enabled else ''
        self.save_config()
        self._notification_dialog.accept()

    def _show_help_popup(self):
        if hasattr(self, 'help_menu'):
            self.help_menu.exec_(self.help_btn.mapToGlobal(QPoint(0, self.help_btn.height() + 4)))

    def _clear_log(self):
        self.log_text.clear()
        self._log_count = 0

    def init_menu(self):
        """初始化菜单栏"""
        menubar = self.menuBar()
        menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {Colors.MANTLE};
                color: {Colors.TEXT};
                padding: 4px 8px;
                border-bottom: 1px solid {Colors.SURFACE2};
            }}
            QMenuBar::item {{
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QMenuBar::item:selected {{
                background-color: {Colors.SURFACE1};
            }}
        """)
        
        # 帮助菜单
        self.help_menu = menubar.addMenu("帮助(&H)")
        help_menu = self.help_menu
        
        # 检查更新
        self.update_action = QAction(icon("refresh", Colors.SUBTEXT0, 17), "检查更新", self)
        self.update_action.triggered.connect(self._check_update)
        help_menu.addAction(self.update_action)

        self.developer_action = QAction(icon("code", Colors.SUBTEXT0, 17), "开发者模式", self)
        self.developer_action.triggered.connect(self._show_developer_mode_dialog)
        help_menu.addAction(self.developer_action)
        
        help_menu.addSeparator()
        
        # 关于
        self.about_action = QAction(icon("info", Colors.SUBTEXT0, 17), "关于", self)
        self.about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(self.about_action)
        menubar.setVisible(False)
        self._refresh_icons()
    
    def _open_github(self):
        """打开 GitHub 仓库"""
        QDesktopServices.openUrl(QUrl(self.GITHUB_URL))

    def _show_developer_mode_dialog(self):
        """Configure custom Webhook channels in the refreshed dialog."""
        dialog = self._prepare_dialog(QDialog(self))
        dialog.setWindowTitle("开发者模式")
        dialog.setMinimumSize(820, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel("开发者模式")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        description = QLabel(
            "通过完整 Webhook 配置接入自定义通知服务，支持多个端点、事件筛选、"
            "请求方法、Headers、URL 参数和 Body 模板。"
        )
        description.setObjectName("mutedLabel")
        description.setWordWrap(True)
        layout.addWidget(description)

        enable_frame = QFrame()
        enable_frame.setObjectName("softCard")
        enable_layout = QVBoxLayout(enable_frame)
        enable_layout.setContentsMargins(16, 13, 16, 13)
        enabled_checkbox = QCheckBox("启用开发者模式和自定义 Webhook 通知")
        enabled_checkbox.setChecked(self.developer_mode_enabled)
        enable_layout.addWidget(enabled_checkbox)
        enable_hint = QLabel("启用后才会按照下方 JSON 配置发送事件通知。")
        enable_hint.setObjectName("mutedLabel")
        enable_layout.addWidget(enable_hint)
        layout.addWidget(enable_frame)

        current_config = {"webhooks": self.developer_webhooks}
        if not self.developer_webhooks and self.feedback_url:
            migrated = make_legacy_feedback_channel(self.feedback_url)
            current_config = {"webhooks": [migrated] if migrated else []}
        if not current_config.get("webhooks"):
            current_config = default_webhook_config()

        config_label = QLabel("Webhook 配置 JSON")
        config_label.setObjectName("fieldLabel")
        layout.addWidget(config_label)
        config_editor = QTextEdit()
        config_editor.setAcceptRichText(False)
        config_editor.setPlainText(json.dumps(current_config, ensure_ascii=False, indent=2))
        config_editor.setEnabled(enabled_checkbox.isChecked())
        layout.addWidget(config_editor, 1)

        hint = QLabel(
            "事件：test、course_available、select_success、swap_success、rollback_success、"
            "rollback_failed、conflict_target_retired，使用 * 可接收全部事件。\n"
            "常用占位符：{event}、{title}、{content}、{course_name}、{teacher}、{remain}、"
            "{capacity}、{old_course_name}、{new_course_name}、{message}、{timestamp}、"
            "{username_masked}。配置中可能含访问密钥，请勿对外分享。"
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        enabled_checkbox.toggled.connect(config_editor.setEnabled)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        test_button = buttons.addButton("测试发送", QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)

        def parse_editor():
            text = config_editor.toPlainText().strip()
            if not text:
                return {"webhooks": []}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"JSON 格式错误：第 {error.lineno} 行第 {error.colno} 列，{error.msg}"
                )
            channels = normalize_webhook_channels(parsed)
            valid, error = validate_webhook_channels(channels)
            if not valid:
                raise ValueError(error)
            return {"webhooks": channels}

        def save_config():
            try:
                parsed = parse_editor()
            except ValueError as error:
                self._show_standard_message(
                    dialog, QMessageBox.Warning, "Webhook 配置无效", str(error)
                )
                return
            self.developer_mode_enabled = enabled_checkbox.isChecked()
            self.developer_webhooks = parsed.get("webhooks", [])
            self.feedback_url = ''
            self.save_config()
            state = "已启用" if self.developer_mode_enabled else "已关闭"
            self.log(f"[INFO] 开发者模式自定义 Webhook {state}，通道数: {len(self.developer_webhooks)}")
            dialog.accept()

        def test_config():
            try:
                parsed = parse_editor()
            except ValueError as error:
                self._show_standard_message(
                    dialog, QMessageBox.Warning, "Webhook 配置无效", str(error)
                )
                return
            send_custom_webhooks(
                parsed, 'test', 'YNU选课助手 Webhook 测试',
                '这是一条开发者模式测试通知。',
                {
                    'course_name': '测试课程', 'teacher': '测试教师',
                    'remain': 1, 'capacity': 30, 'message': '开发者模式测试通知',
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'username_masked': self.username_input.text()[:2] + '****'
                    if self.username_input.text() else '',
                },
            )
            self._show_standard_message(
                dialog, QMessageBox.Information, "测试已发送", "已触发 test 事件。"
            )

        buttons.accepted.connect(save_config)
        buttons.rejected.connect(dialog.reject)
        test_button.clicked.connect(test_config)
        dialog.exec_()

    def _check_update(self):
        """检查更新 - 使用 UpdateCheckWorker"""
        # 显示检查中的提示
        self._update_check_dialog = self._prepare_dialog(
            QProgressDialog("正在检查更新，请稍候...", "取消", 0, 0, self)
        )
        self._update_check_dialog.setWindowTitle("检查更新")
        self._update_check_dialog.setWindowModality(Qt.WindowModal)
        self._update_check_dialog.setMinimumWidth(430)
        self._update_check_dialog.setMinimumHeight(150)
        self._update_check_dialog.setMinimumDuration(0)
        self._update_check_dialog.setAutoClose(False)
        self._update_check_dialog.setStyleSheet(f"""
            QProgressDialog {{
                background-color: {Colors.BASE};
            }}
            QLabel {{
                color: {Colors.TEXT};
                font-size: 14px;
            }}
            QPushButton {{
                background-color: {Colors.SURFACE0};
                color: {Colors.TEXT};
                border: 1px solid {Colors.SURFACE2};
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE1};
            }}
        """)
        self._update_check_dialog.canceled.connect(self._on_update_check_canceled)
        self._update_check_dialog.show()
        self._center_progress_dialog_label(self._update_check_dialog)
        
        self.statusBar().showMessage("正在检查更新...")
        
        # 启动后台 Worker
        self._update_check_worker = UpdateCheckWorker(self.VERSION)
        self._update_check_worker.finished.connect(self._on_update_checked)
        self._update_check_worker.start()
    
    def _on_update_check_canceled(self):
        """用户取消检查更新"""
        if hasattr(self, '_update_check_worker') and self._update_check_worker:
            try:
                self._update_check_worker.finished.disconnect()
            except TypeError:
                pass
        self.statusBar().showMessage("", 0)
    
    def _format_version(self, version):
        """统一版本号展示格式，避免出现 vv2.0.0"""
        normalized = str(version or '').strip().lstrip('vV')
        return f"v{normalized}" if normalized else "未知"
    
    def _on_update_checked(self, has_update, latest_version, download_url, error):
        """更新检查完成回调"""
        # 关闭进度对话框
        if hasattr(self, '_update_check_dialog') and self._update_check_dialog:
            self._update_check_dialog.close()
        self.statusBar().showMessage("", 0)

        if error:
            self._show_update_message(
                QMessageBox.Warning, "检查更新", f"检查更新失败\n\n{error}"
            )
            return

        if not latest_version:
            self._show_update_message(
                QMessageBox.Information, "检查更新", "暂无发布版本信息"
            )
            return

        current_text = self._format_version(self.VERSION)
        latest_text = self._format_version(latest_version)

        if has_update:
            # 检查是否是直接下载链接（.exe）
            is_direct_download = str(download_url or '').lower().split('?', 1)[0].endswith('.exe')

            if is_direct_download:
                msg = f"发现新版本！\n\n当前版本: {current_text}\n最新版本: {latest_text}"
                reply = self._show_update_message(
                    QMessageBox.Question, "发现新版本",
                    msg + "\n\n是否立即下载并安装？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._start_download_update(download_url, latest_version)
            else:
                # 没有找到 .exe，回退到打开浏览器
                msg = f"发现新版本！\n\n当前版本: {current_text}\n最新版本: {latest_text}"
                reply = self._show_update_message(
                    QMessageBox.Question, "发现新版本",
                    msg + "\n\n是否前往下载页面？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    QDesktopServices.openUrl(QUrl(download_url))
        else:
            self._show_update_message(
                QMessageBox.Information, "检查更新", f"当前已是最新版本 {current_text}"
            )

    def _show_update_message(
        self,
        message_icon,
        title,
        text,
        buttons=QMessageBox.Ok,
        default_button=QMessageBox.NoButton,
    ):
        return self._show_centered_message(
            message_icon, title, text, buttons, default_button
        )

    def _show_centered_message(
        self,
        message_icon,
        title,
        text,
        buttons=QMessageBox.Ok,
        default_button=QMessageBox.NoButton,
        yes_text=None,
        no_text=None,
        icon_name_override=None,
        icon_color_override=None,
    ):
        """Native-looking card dialog with genuinely centred icon and copy."""
        dialog = self._prepare_dialog(QDialog(self))
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setStyleSheet(build_stylesheet(self.theme_mode))
        dialog.setMinimumWidth(540)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(34, 28, 34, 26)
        layout.setSpacing(16)

        icon_name, icon_color = {
            QMessageBox.Warning: ('alert-triangle', Colors.YELLOW),
            QMessageBox.Critical: ('alert-triangle', Colors.RED),
            QMessageBox.Question: ('help', Colors.BLUE),
            QMessageBox.Information: ('info', Colors.BLUE),
        }.get(message_icon, ('info', Colors.BLUE))
        if icon_name_override:
            icon_name = icon_name_override
        if icon_color_override:
            icon_color = icon_color_override
        icon_label = QLabel()
        icon_label.setPixmap(icon(icon_name, icon_color, 38).pixmap(38, 38))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        message_label = QLabel(text)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setMinimumWidth(460)
        message_label.setMaximumWidth(590)
        message_label.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 14px; line-height: 1.55; padding: 2px 8px;"
        )
        layout.addWidget(message_label, 0, Qt.AlignHCenter)

        dialog_buttons = QDialogButtonBox.StandardButtons(int(buttons))
        button_box = QDialogButtonBox(dialog_buttons)
        button_box.setCenterButtons(True)

        def button_for(message_button):
            return button_box.button(QDialogButtonBox.StandardButton(int(message_button)))

        if button_for(QMessageBox.Ok):
            button_for(QMessageBox.Ok).setText("确定")
            button_for(QMessageBox.Ok).setObjectName("primaryButton")
        if button_for(QMessageBox.Yes):
            button_for(QMessageBox.Yes).setText(yes_text or "确定")
            button_for(QMessageBox.Yes).setObjectName("primaryButton")
        if button_for(QMessageBox.No):
            button_for(QMessageBox.No).setText(no_text or "取消")
            button_for(QMessageBox.No).setObjectName("secondaryButton")
        if button_for(QMessageBox.Cancel):
            button_for(QMessageBox.Cancel).setText("取消")
            button_for(QMessageBox.Cancel).setObjectName("secondaryButton")
        if default_button != QMessageBox.NoButton:
            default_widget = button_for(default_button)
            if default_widget:
                default_widget.setDefault(True)

        result = {'button': QMessageBox.NoButton}

        def finish(button):
            result['button'] = QMessageBox.StandardButton(
                int(button_box.standardButton(button))
            )
            dialog.accept()

        button_box.clicked.connect(finish)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(button_box)
        button_row.addStretch()
        layout.addLayout(button_row)
        dialog.exec_()
        return result['button']

    def _start_download_update(self, download_url, version):
        """开始下载更新"""
        # 确定保存路径
        normalized_version = str(version or '').strip().lstrip('vV') or 'latest'
        filename = f"YNU.Pro_v{normalized_version}_Setup.exe"
        save_path = os.path.join(os.path.expanduser("~"), "Downloads", filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # 创建进度对话框
        self._download_dialog = self._prepare_dialog(QProgressDialog(self))
        self._download_dialog.setWindowTitle("下载更新")
        self._download_dialog.setLabelText(f"正在下载 {filename}...\n0 MB / 0 MB (0%)")
        self._download_dialog.setMinimum(0)
        self._download_dialog.setMaximum(100)
        self._download_dialog.setValue(0)
        self._download_dialog.setWindowModality(Qt.WindowModal)
        self._download_dialog.setMinimumSize(480, 170)
        self._download_dialog.setAutoClose(False)
        self._download_dialog.setAutoReset(False)
        self._download_dialog.setStyleSheet(f"""
            QProgressDialog {{
                background-color: {Colors.BASE};
                color: {Colors.TEXT};
            }}
            QLabel {{
                color: {Colors.TEXT};
            }}
            QPushButton {{
                background-color: {Colors.SURFACE0};
                color: {Colors.TEXT};
                border: none;
                padding: 5px 15px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SURFACE1};
            }}
            QProgressBar {{
                border: 2px solid {Colors.SURFACE0};
                border-radius: 5px;
                text-align: center;
                background-color: {Colors.SURFACE0};
                color: {Colors.TEXT};
            }}
            QProgressBar::chunk {{
                background-color: {Colors.BLUE};
                border-radius: 3px;
            }}
        """)
        self._download_dialog.canceled.connect(self._on_download_canceled)
        self._download_dialog.show()
        self._center_progress_dialog_label(self._download_dialog)

        # 启动下载 Worker
        self._download_worker = DownloadUpdateWorker(download_url, save_path)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.start()

    def _on_download_progress(self, downloaded, total, percentage):
        """下载进度更新"""
        if hasattr(self, '_download_dialog') and self._download_dialog:
            downloaded_mb = downloaded / (1024 * 1024)
            if total and total > 0:
                total_mb = total / (1024 * 1024)
                label_text = f"正在下载更新...\n{downloaded_mb:.1f} MB / {total_mb:.1f} MB ({percentage}%)"
                self._download_dialog.setRange(0, 100)
                self._download_dialog.setValue(percentage)
            else:
                label_text = f"正在下载更新...\n已下载 {downloaded_mb:.1f} MB（服务器未返回总大小）"
                self._download_dialog.setRange(0, 0)
            self._download_dialog.setLabelText(label_text)
            self._center_progress_dialog_label(self._download_dialog)

    def _center_progress_dialog_label(self, dialog):
        """Keep update progress copy visually centred at every label refresh."""
        if not dialog:
            return
        for label in dialog.findChildren(QLabel):
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)

    def _on_download_finished(self, file_path, error):
        """下载完成回调"""
        # 关闭进度对话框
        if hasattr(self, '_download_dialog') and self._download_dialog:
            self._download_dialog.close()

        if error:
            self._show_update_message(
                QMessageBox.Warning, "下载失败", f"更新下载失败\n\n{error}"
            )
            return

        if not file_path or not os.path.exists(file_path):
            self._show_update_message(
                QMessageBox.Warning, "下载失败", "文件下载失败，请稍后重试"
            )
            return

        # 下载成功，询问是否立即安装
        reply = self._show_centered_message(
            QMessageBox.Question, "下载完成",
            f"更新已下载完成！\n\n文件位置: {file_path}\n\n是否立即打开安装程序？\n"
            "程序会先保存账号和待选课程，然后停止监控并自动退出。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
            yes_text="立即安装",
            no_text="稍后",
        )

        if reply == QMessageBox.Yes:
            try:
                # 更新前持久化账号配置和待选课程，并停止守护进程。
                self._installing_update = True
                self._update_resume_monitoring = (
                    self.multi_grab_worker is not None
                    and self.multi_grab_worker.isRunning()
                )
                self.save_config()
                self.save_monitor_state(is_monitoring=self._update_resume_monitoring)
                self.write_watchdog_signal('stop')
                if self.multi_grab_worker:
                    if not self.stop_monitoring(clear_state=False, reason='update'):
                        raise RuntimeError("监控线程尚未完全停止，请稍后重试安装")

                # 打开安装程序
                if sys.platform == 'win32':
                    os.startfile(file_path)
                else:
                    subprocess.Popen(['xdg-open', file_path])
                QTimer.singleShot(500, QApplication.instance().quit)
            except Exception as e:
                self._installing_update = False
                self._show_update_message(
                    QMessageBox.Warning,
                    "打开失败",
                    f"无法打开安装程序\n\n{str(e)}\n\n请手动打开: {file_path}",
                )

    def _on_download_canceled(self):
        """用户取消下载"""
        if hasattr(self, '_download_worker') and self._download_worker:
            self._download_worker.cancel()
            try:
                self._download_worker.finished.disconnect()
            except TypeError:
                pass
    
    def _show_about_dialog(self):
        """显示关于对话框"""
        dialog = self._prepare_dialog(QDialog(self))
        dialog.setWindowTitle("关于 YNU选课助手 Pro")
        dialog.setFixedSize(570, 620)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(34, 28, 34, 24)
        
        # Logo/标题
        title_label = QLabel("YNU 选课助手 Pro")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"""
            font-size: 29px;
            font-weight: 800;
            color: {Colors.BLUE};
            padding: 6px 0;
        """)
        layout.addWidget(title_label)
        
        # 版本
        version_label = QLabel(f"版本 {self.VERSION}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet(f"""
            font-size: 14px;
            color: {Colors.SUBTEXT0};
            margin-bottom: 6px;
        """)
        layout.addWidget(version_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {Colors.SURFACE2}; max-height: 1px;")
        layout.addWidget(line)
        
        # 简介
        intro_label = QLabel("云南大学教务系统选课辅助工具")
        intro_label.setAlignment(Qt.AlignCenter)
        intro_label.setStyleSheet(f"""
            font-size: 13px;
            color: {Colors.SUBTEXT1};
            padding: 4px 0;
        """)
        layout.addWidget(intro_label)
        
        # 功能描述（使用滚动区域）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)
        
        features_widget = QWidget()
        features_layout = QVBoxLayout(features_widget)
        features_layout.setSpacing(8)
        features_layout.setContentsMargins(4, 4, 4, 4)
        
        # 主要功能
        features_text = QLabel(
            "<b>主要功能</b><br>"
            "　• 纯 API 模式，无需浏览器<br>"
            "　• 自动 OCR 验证码识别<br>"
            "　• 多课程并发监控抢课<br>"
            "　• 智能换课（自动退旧选新）<br>"
            "　• Server酱微信通知推送<br>"
            "　• Session 过期自动重登<br><br>"
            
            "<b>使用方法</b><br>"
            "1. 输入学号密码，点击「一键登录」<br>"
            "2. 选择课程类型，浏览或搜索课程<br>"
            "3. 点击「加入待抢」添加到列表<br>"
            "4. 设置并发数，点击「开始监控」<br><br>"
            
            "<b>Server酱配置</b><br>"
            "1. 访问 <a href='https://sct.ftqq.com/' style='color: #89b4fa;'>https://sct.ftqq.com/</a><br>"
            "2. 微信扫码登录获取 SendKey<br>"
            "3. 勾选「微信通知」并填入 SendKey<br>"
            "4. 发现余量和抢课成功时自动推送"
        )
        features_text.setWordWrap(True)
        features_text.setOpenExternalLinks(True)
        features_text.setTextFormat(Qt.RichText)
        features_text.setStyleSheet(f"""
            font-size: 12px;
            color: {Colors.SUBTEXT1};
            line-height: 1.5;
            padding: 6px;
        """)
        features_layout.addWidget(features_text)
        
        scroll.setWidget(features_widget)
        scroll.setFixedHeight(285)
        layout.addWidget(scroll)
        
        layout.addStretch()
        
        # 作者信息框
        author_frame = QFrame()
        author_frame.setObjectName("softCard")
        author_layout = QVBoxLayout(author_frame)
        author_layout.setSpacing(4)
        author_layout.setContentsMargins(16, 10, 16, 10)
        
        original_label = QLabel(
            f"原项目：<a href='https://github.com/starwingChen/YNU-xk_spider' "
            f"style='color:{Colors.BLUE}; text-decoration:none;'>"
            "starwingChen/YNU-xk_spider</a>"
        )
        original_label.setTextFormat(Qt.RichText)
        original_label.setOpenExternalLinks(True)
        original_label.setStyleSheet(f"font-size: 12px; color: {Colors.SUBTEXT0};")
        author_layout.addWidget(original_label)
        
        dev_label = QLabel("作者：YHalo-wyh")
        dev_label.setStyleSheet(f"font-size: 12px; color: {Colors.LAVENDER}; font-weight: bold;")
        author_layout.addWidget(dev_label)

        layout.addWidget(author_frame)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        github_btn = QPushButton("打开 GitHub 仓库")
        github_btn.setObjectName("primaryButton")
        github_btn.setIcon(icon("github", "#FFFFFF", 18))
        github_btn.setIconSize(QSize(18, 18))
        github_btn.setCursor(Qt.PointingHandCursor)
        github_btn.setFixedHeight(44)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.GITHUB_URL)))
        btn_layout.addWidget(github_btn)
        
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(44)
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def _on_serverchan_toggled(self, state):
        """Server酱复选框状态变化"""
        self.serverchan_enabled = bool(state)
        self.serverchan_key_input.setVisible(self.serverchan_enabled)
        if not self.serverchan_enabled:
            self.serverchan_key = ''
    
    def log(self, msg):
        """
        日志方法：UI 滚动清理 + 文件持久化
        优化：减少 UI 操作频率，避免长时间运行后卡顿
        """
        try:
            # 写入文件日志
            self._logger.info(msg)
            
            # 计数器：每 50 条日志才检查一次是否需要清理
            if not hasattr(self, '_log_count'):
                self._log_count = 0
            self._log_count += 1
            
            # 每 50 条检查一次，超过 500 行时清空到 200 行
            if self._log_count % 50 == 0 and self.log_text.document().maximumBlockCount() <= 0:
                try:
                    doc = self.log_text.document()
                    block_count = doc.blockCount()
                    if block_count > 500:
                        # 直接截取最后 200 行，比逐行删除快得多
                        text = self.log_text.toPlainText()
                        lines = text.split('\n')
                        if len(lines) > 200:
                            self.log_text.setPlainText('\n'.join(lines[-200:]))
                except Exception:
                    # 日志清理失败不应该影响程序运行
                    pass
            
            # 使用字符格式追加分级日志，接口响应中的尖括号不会被当作 HTML。
            try:
                self._append_colored_log(str(msg))
            except Exception:
                try:
                    self.log_text.append(f"[{time.strftime('%H:%M:%S')}] 日志输出异常")
                except Exception:
                    pass
            
            # 每 10 条才滚动一次，减少 UI 刷新
            if self._log_count % 10 == 0:
                try:
                    scrollbar = self.log_text.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())
                except Exception:
                    # 滚动失败不影响程序运行
                    pass
        except Exception as e:
            # 整个日志方法失败，写入系统日志
            try:
                self._logger.error(f"日志输出异常: {str(e)[:50]}")
            except Exception:
                # 连系统日志都失败，完全忽略
                pass

    def _append_colored_log(self, message):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self.log_text.toPlainText():
            cursor.insertBlock()

        timestamp_format = QTextCharFormat()
        timestamp_format.setForeground(QColor(Colors.OVERLAY0))
        cursor.insertText(f"[{time.strftime('%H:%M:%S')}] ", timestamp_format)

        match = re.match(r"^\[([A-Za-z]+)\]\s*", message)
        level = match.group(1).upper() if match else "INFO"
        palette = {
            "SUCCESS": Colors.GREEN,
            "INFO": Colors.BLUE,
            "WARN": Colors.YELLOW,
            "WARNING": Colors.YELLOW,
            "ERROR": Colors.RED,
            "API": Colors.LAVENDER,
            "ALERT": Colors.PEACH,
        }
        if match:
            level_format = QTextCharFormat()
            level_format.setForeground(QColor(palette.get(level, Colors.BLUE)))
            level_format.setFontWeight(QFont.DemiBold)
            cursor.insertText(f"{level:<7}", level_format)
            message = message[match.end():]

        body_format = QTextCharFormat()
        if not match and any(word in message for word in ("失败", "异常", "错误")):
            body_format.setForeground(QColor(Colors.RED))
        else:
            body_format.setForeground(QColor(Colors.TERMINAL_TEXT))
        cursor.insertText(message, body_format)
        self.log_text.setTextCursor(cursor)
    
    def update_heartbeat(self, count):
        """更新心跳指示器 - 只更新文本，避免频繁设置样式"""
        try:
            self._heartbeat_count = count
            # 只更新文本，不频繁切换样式（避免内存泄漏和卡顿）
            self.run_indicator.setText(f"监控中 · 已扫描 {count} 次")
        except Exception as e:
            # 心跳更新失败不应该影响程序运行
            try:
                self._logger.warning(f"心跳更新失败: {str(e)[:50]}")
            except Exception:
                pass
    
    def load_config(self):
        try:
            config = read_json(CONFIG_FILE, {})
            if config:
                self.username_input.setText(config.get('username', ''))
                self.password_input.setText(config.get('password', ''))
                
                # Server酱配置
                self.serverchan_enabled = config.get('serverchan_enabled', False)
                self.serverchan_key = config.get('serverchan_key', '')
                self.serverchan_checkbox.setChecked(self.serverchan_enabled)
                self.serverchan_key_input.setText(self.serverchan_key)
                self.serverchan_key_input.setVisible(self.serverchan_enabled)

                self.developer_mode_enabled = config.get('developer_mode_enabled', False)
                self.feedback_url = str(config.get('feedback_url', '') or '').strip()
                self.developer_webhooks = normalize_webhook_channels(
                    config.get('developer_webhooks', [])
                )
                if not self.developer_webhooks and self.feedback_url:
                    migrated = make_legacy_feedback_channel(self.feedback_url)
                    if migrated:
                        self.developer_webhooks = [migrated]
        except:
            pass
    
    def save_config(self):
        # 更新 Server酱 key
        if self.serverchan_enabled:
            self.serverchan_key = self.serverchan_key_input.text().strip()
        
        config = {
            'username': self.username_input.text(),
            'password': self.password_input.text(),
            'theme_mode': self.theme_mode,
            'serverchan_enabled': self.serverchan_enabled,
            'serverchan_key': self.serverchan_key if self.serverchan_enabled else '',
            'developer_mode_enabled': self.developer_mode_enabled,
            'feedback_url': self.feedback_url,
            'developer_webhooks': self.developer_webhooks,
        }
        try:
            write_json_atomic(CONFIG_FILE, config)
        except Exception as e:
            self._logger.error(f"保存账号配置失败: {e}")

    def save_monitor_state(self, is_monitoring=False):
        """保存监控状态到文件（用于闪退恢复）"""
        state = {
            'is_monitoring': is_monitoring,
            'courses': [],
            'course_type': self.course_type_combo.currentText(),
            'concurrency': self.concurrency_spin.value(),
            'conflict_policy': self._active_conflict_policy if is_monitoring else None,
            'swap_risk_confirmed': self._swap_risk_confirmed if is_monitoring else False,
            'timestamp': time.time(),
        }
        
        # 无论是否正在监控，都保存待选课程列表。
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            course = item.data(Qt.UserRole)
            if course:
                state['courses'].append(course)
        
        try:
            write_json_atomic(MONITOR_STATE_FILE, state)
        except Exception as e:
            self._logger.error(f"保存监控状态失败: {e}")

    def load_monitor_state(self):
        """加载监控状态文件"""
        return read_json(MONITOR_STATE_FILE)

    def _restore_saved_watchlist(self, state):
        """恢复上次保存的待选课程和界面设置，但不自动开始监控。"""
        self._swap_risk_confirmed = bool(
            state.get('swap_risk_confirmed', state.get('is_monitoring', False))
        )
        course_type = state.get('course_type', '')
        index = self.course_type_combo.findText(course_type)
        if index >= 0:
            self.course_type_combo.blockSignals(True)
            self.course_type_combo.setCurrentIndex(index)
            self.course_type_combo.blockSignals(False)

        if 'concurrency' in state:
            self.concurrency_spin.setValue(state['concurrency'])

        existing_ids = {
            self.grab_list.item(i).data(Qt.UserRole).get('JXBID', '')
            for i in range(self.grab_list.count())
            if self.grab_list.item(i).data(Qt.UserRole)
        }
        for course in state.get('courses', []):
            if not isinstance(course, dict):
                continue
            tc_id = course.get('JXBID', '')
            if not tc_id or tc_id in existing_ids:
                continue
            item = QListWidgetItem(self._build_grab_item_text(course))
            item.setData(Qt.UserRole, course)
            self.grab_list.addItem(item)
            self._apply_grab_item_visual(item, course)
            existing_ids.add(tc_id)
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")

    def clear_monitor_state(self):
        """仅清除自动恢复标记，保留待选课程。"""
        self.save_monitor_state(is_monitoring=False)

    def write_watchdog_signal(self, action, pid=None):
        """写入 watchdog 信号文件"""
        signal_data = {
            'action': action,
            'timestamp': time.time(),
        }
        if pid is not None:
            signal_data['pid'] = pid

        try:
            write_json_atomic(WATCHDOG_SIGNAL_FILE, signal_data)
        except Exception as e:
            self._logger.error(f"写入 watchdog 信号失败: {e}")

    def start_watchdog_process(self):
        """按需启动守护进程（开始监控时调用）"""
        try:
            main_pid = os.getpid()

            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
                watchdog_exe = os.path.join(base_dir, 'Watchdog.exe')
                if not os.path.exists(watchdog_exe):
                    self._logger.warning(f"Watchdog.exe 不存在: {watchdog_exe}")
                    return

                subprocess.Popen(
                    [watchdog_exe, str(main_pid)],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                    start_new_session=True,
                    cwd=base_dir
                )
            else:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
                watchdog_script = os.path.join(base_dir, 'run_watchdog.py')
                if not os.path.exists(watchdog_script):
                    self._logger.warning(f"run_watchdog.py 不存在: {watchdog_script}")
                    return

                subprocess.Popen(
                    [sys.executable, watchdog_script, str(main_pid)],
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                    start_new_session=True,
                    cwd=base_dir
                )
        except Exception as e:
            self._logger.error(f"启动 watchdog 失败: {e}")

    def _auto_login_for_restore(self):
        """闪退恢复时自动登录"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            self.log("[WARN] 无法自动登录：缺少保存的用户名或密码")
            self._pending_restore_state = None
            self.clear_monitor_state()
            return
        
        self.log("[INFO] 正在自动登录以恢复监控...")
        self._is_manual_login_attempt = False
        self.login()

    def on_manual_login_clicked(self):
        """用户主动点击一键登录"""
        self._is_manual_login_attempt = True
        if hasattr(self, 'login_feedback_label'):
            self.login_feedback_label.clear()
        self.login()

    def login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            missing = "账号和密码" if not username and not password else "账号" if not username else "密码"
            self._logger.warning(f"登录输入检查失败：未填写{missing}")
            if hasattr(self, 'login_feedback_label'):
                self.login_feedback_label.setText(f"请输入{missing}")
            self._is_manual_login_attempt = False
            return
        
        self.save_config()
        self.login_btn.setEnabled(False)
        self.login_btn.setText("登录中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        if hasattr(self, 'login_progress'):
            self.login_progress.setVisible(True)
            self.login_progress.setRange(0, 0)
        if hasattr(self, 'login_feedback_label'):
            self.login_feedback_label.setText("正在连接云南大学选课系统")
        
        self.login_worker = LoginWorker(username, password)
        self.login_worker.success.connect(self.on_login_success)
        self.login_worker.failed.connect(self.on_login_failed)
        self.login_worker.status.connect(self._show_login_status)
        self.login_worker.start()

    def _show_login_status(self, msg):
        self.statusBar().showMessage(str(msg))
        if self.app_stack.currentWidget() is self.login_page:
            self.login_feedback_label.setStyleSheet(f"color: {Colors.SUBTEXT0}; font-size: 12px;")
            self.login_feedback_label.setText(str(msg))
    
    def on_login_success(self, cookies, token, batch_code, batch_name, student_code, campus):
        self.cookies = cookies
        self.token = token
        self.batch_code = batch_code
        self.batch_name = batch_name or ''
        self.student_code = student_code
        self.campus = campus  # 保存校区代码
        self.is_logged_in = True
        self._is_manual_login_attempt = False
        self._manual_login_fail_count = 0
        self._auto_relogin_retry_count = 0
        
        # 显示校区信息
        campus_name = "呈贡校区" if campus == "02" else "东陆校区" if campus == "01" else f"校区{campus}"
        self.status_label.setText(f"已登录 · {campus_name}")
        self.status_label.setStyleSheet(
            f"color: {Colors.GREEN}; background-color: {Colors.SURFACE1}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 16px; "
            "padding: 7px 13px; font-size: 13px; font-weight: 700;"
        )
        self.login_btn.setText("已登录")
        self.login_btn.setEnabled(False)
        self.logout_btn.setEnabled(True)
        self.curriculum_btn.setEnabled(True)
        self.selected_courses_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        if hasattr(self, 'login_progress'):
            self.login_progress.setVisible(False)
        if hasattr(self, 'login_feedback_label'):
            self.login_feedback_label.clear()
            self.login_feedback_label.setStyleSheet("")
        self._fade_in_workspace()
        # Do not compete with the first course-list request. Its completion
        # starts this prefetch; the timer covers watchdog restore paths where
        # no initial browser request is made.
        self._curriculum_prefetch_waiting = True
        QTimer.singleShot(2500, self._start_pending_curriculum_prefetch)

        self.log("[SUCCESS] 登录成功")
        self.log(f"[INFO] 校区: {campus_name} ({campus})")
        self.log("[INFO] Token 已获取")
        if self.batch_name and self.batch_name != self.batch_code:
            self.batch_label.setText(f"选课批次：{self.batch_name} ({self.batch_code})")
            self.log(f"[INFO] Batch: {self.batch_name} ({self.batch_code})")
        else:
            self.batch_label.setText(f"选课批次：{self.batch_code}")
            self.log(f"[INFO] BatchCode: {self.batch_code}")
        self.statusBar().showMessage("纯 API 模式已就绪，课程列表自动刷新中...")
        
        # 优先从状态文件恢复（闪退恢复）
        if self._pending_restore_state and self._pending_restore_state.get('courses'):
            courses = self._pending_restore_state['courses']
            self.log(f"[INFO] 从状态文件恢复 {len(courses)} 门监控课程")
            
            # 恢复并发数设置
            if 'concurrency' in self._pending_restore_state:
                self.concurrency_spin.setValue(self._pending_restore_state['concurrency'])
            
            # 添加课程到待抢列表
            for course in courses:
                tc_id = course.get('JXBID', '')
                exists = False
                for i in range(self.grab_list.count()):
                    item = self.grab_list.item(i)
                    if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                        exists = True
                        break
                
                if not exists:
                    display_text = self._build_grab_item_text(course)
                    
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, course)
                    self.grab_list.addItem(item)
                    self._apply_grab_item_visual(item, course)
            
            self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
            restored_conflict_policy = self._pending_restore_state.get('conflict_policy')
            restored_swap_risk_confirmed = bool(
                self._pending_restore_state.get(
                    'swap_risk_confirmed',
                    self._pending_restore_state.get('is_monitoring', False),
                )
            )
            self._active_conflict_policy = (
                restored_conflict_policy if isinstance(restored_conflict_policy, dict)
                else None
            )
            self._pending_restore_state = None
	            
            # 自动开始监控
            self.log("[INFO] 自动恢复监控中...")
            QTimer.singleShot(
                1000,
                lambda policy=restored_conflict_policy: self.start_monitoring(
                    conflict_policy=policy,
                    skip_policy_dialog=True,
                    skip_swap_risk_dialog=restored_swap_risk_confirmed,
                )
            )
        elif self._pending_monitor_courses:
            self.log(f"[INFO] 检测到 {len(self._pending_monitor_courses)} 门待恢复课程")
            QTimer.singleShot(1000, self._resume_monitoring)
        else:
            QTimer.singleShot(300, self._start_polling)
    
    def on_login_failed(self, msg):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")
        self.progress_bar.setVisible(False)
        if hasattr(self, 'login_progress'):
            self.login_progress.setVisible(False)
        self.log(f"[ERROR] 登录失败: {msg}")
        if hasattr(self, 'login_feedback_label'):
            self.login_feedback_label.setStyleSheet(f"color: {Colors.RED}; font-size: 12px;")
            self.login_feedback_label.setText(str(msg) or "登录失败，请稍后重试")

        credentials_error = '登录名或密码不正确' in str(msg)
        if self._is_manual_login_attempt and credentials_error:
            self._manual_login_fail_count = 0
            self.login_feedback_label.setText("登录名或密码不正确，请检查后重试")
            self.statusBar().showMessage("登录名或密码不正确")
        elif self._is_manual_login_attempt:
            self._manual_login_fail_count += 1
            remain = 5 - self._manual_login_fail_count
            if remain > 0:
                self.statusBar().showMessage(f"登录失败，已连续失败 {self._manual_login_fail_count} 次")
                self.log(f"[WARN] 手动登录连续失败 {self._manual_login_fail_count} 次")
            else:
                self.login_feedback_label.setText(
                    "连续登录失败 5 次，可能是用户名、密码或当前网络配置有误"
                )
                self._manual_login_fail_count = 0

        self._is_manual_login_attempt = False
    
    def logout(self):
        self.poll_timer.stop()
        self._is_searching = False
        
        was_monitoring = self.multi_grab_worker is not None
        self.stop_monitoring(reason='logout')
        self.is_logged_in = False
        self.token = ''
        self.batch_code = ''
        self.batch_name = ''
        self.student_code = ''
        self.campus = '02'  # 重置为默认
        self.cookies = ''
        self._curriculum_arranged = []
        self._curriculum_unarranged = []
        self._curriculum_loaded = False
        self._curriculum_error = ''
        self._curriculum_refresh_pending = False
        self._curriculum_prefetch_waiting = False
        self.batch_label.setText("选课批次：自动识别")
        
        self.status_label.setText("未登录")
        self.status_label.setStyleSheet("")
        self.login_btn.setText("登录")
        self.login_btn.setEnabled(True)
        self.logout_btn.setEnabled(False)
        self.curriculum_btn.setEnabled(False)
        self.selected_courses_btn.setEnabled(False)
        
        self.course_list.clear()
        self.clear_cards()
        self._api_courses_grouped = {}
        
        if not was_monitoring:
            self.log("[INFO] 已退出登录")
        self._show_login_page()

    def refresh_courses(self, keyword='', silent=False, force=False):
        """
        刷新课程列表（使用后台线程）
        force=True 时断开旧请求信号并启动新请求
        """
        if not self.is_logged_in:
            if not silent:
                self._show_standard_message(
                    self, QMessageBox.Warning, "提示", "请先登录"
                )
            return
        
        # 如果有正在运行的请求
        if self._course_fetch_worker and self._course_fetch_worker.isRunning():
            if force:
                # 断开旧请求的信号连接，让它自然结束（不使用 terminate 避免资源泄漏）
                try:
                    self._course_fetch_worker.finished.disconnect()
                except TypeError:
                    pass  # 信号未连接，忽略
                self.log("[API] 后台有未完成请求，已断开信号并重新发起")
                # 不再等待旧线程，让它自然结束
            else:
                # 非强制模式，跳过
                return
        
        course_type_name = self.course_type_combo.currentText()
        course_type_code = COURSE_TYPES.get(course_type_name, 'TJKC')
        internal_type = COURSE_NAME_TO_TYPE.get(course_type_name, 'recommend')
        
        search_keyword = keyword if keyword else self.search_input.text().strip()
        self._current_search_keyword = search_keyword
        
        # 记录当前请求的课程类型（用于回调时校验）
        self._current_fetch_type = course_type_name
        self._fetch_silent = silent
        
        if not silent:
            self.course_list.clear()
            self.clear_cards()
            self._api_courses_grouped = {}
            self.course_count_label.setText("加载中...")
            self.log(f"[API] 刷新课程列表: {course_type_name}" + (f" (搜索: {search_keyword})" if search_keyword else ""))
        
        self.statusBar().showMessage(f"正在获取 {course_type_name}...")
        
        self._course_fetch_worker = CourseFetchWorker(
            token=self.token,
            cookies=self.cookies,
            student_code=self.student_code,
            batch_code=self.batch_code,
            course_type_code=course_type_code,
            internal_type=internal_type,
            campus=self.campus,  # 传入校区代码
            search_keyword=search_keyword
        )
        self._course_fetch_worker.finished.connect(self._on_course_fetch_finished)
        self._course_fetch_worker.start()
    
    def _on_course_fetch_finished(self, courses_grouped, error):
        """CourseFetchWorker 完成回调"""
        silent = self._fetch_silent
        
        # 校验：如果当前下拉框的类型已经变了，说明用户切换了，忽略这个旧回调
        current_type = self.course_type_combo.currentText()
        if hasattr(self, '_current_fetch_type') and self._current_fetch_type != current_type:
            # 旧请求的回调，忽略
            return
        QTimer.singleShot(80, self._start_pending_curriculum_prefetch)
        
        if error:
            error_str = str(error).lower()
            
            # 初始化失败计数器
            if not hasattr(self, '_fetch_fail_count'):
                self._fetch_fail_count = 0
            self._fetch_fail_count += 1
            
            # 网络连接错误 - 自动重试
            is_network_error = any(kw in error_str for kw in [
                'connectionpool', 'connection', 'timeout', 'timed out',
                'refused', 'reset', 'network', 'socket', 'ssl', 'eof'
            ])
            
            if is_network_error:
                # 初始化重试计数器
                if not hasattr(self, '_fetch_retry_count'):
                    self._fetch_retry_count = 0
                
                self._fetch_retry_count += 1
                max_retries = 3
                
                if self._fetch_retry_count <= max_retries:
                    # 3次内都显示"加载中"，不显示失败
                    if not silent:
                        self.course_count_label.setText("加载中...")
                    # 延迟重试，间隔递增
                    QTimer.singleShot(self._fetch_retry_count * 1000, lambda: self.refresh_courses(silent=silent, force=True))
                    return
                else:
                    # 超过重试次数才显示失败
                    self._fetch_retry_count = 0
                    if not silent:
                        self.log(f"[API] 获取失败: {error}")
                        self.course_count_label.setText("获取失败 (等待下次轮询)")
                    return
            
            # 非网络错误：也要累计3次才显示失败
            if self._fetch_fail_count < 3:
                if not silent:
                    self.course_count_label.setText("加载中...")
                return
            
            # 重置计数器
            self._fetch_fail_count = 0
            self._fetch_retry_count = 0
            
            if not silent:
                self.log(f"[API] 获取失败: {error}")
                self.course_count_label.setText("获取失败")
            
            # 只有在非监控模式下才处理登录过期（监控时由 worker 自动重登）
            if '登录' in error_str or 'token' in error_str:
                if self.multi_grab_worker and self.multi_grab_worker.isRunning():
                    # 监控中，忽略这个错误，等待 worker 重登
                    self.log("[API] 监控中检测到 session 问题，等待自动重登...")
                else:
                    self.poll_timer.stop()
                    self.log("[WARN] 检测到会话过期，开始自动重登...")
                    self._auto_relogin_and_resume()
            return
        
        # 成功获取，重置计数器
        self._fetch_retry_count = 0
        self._fetch_fail_count = 0

        # 本地搜索过滤：仅匹配课程名/教师名
        search_keyword = self._current_search_keyword.strip().lower() if self._current_search_keyword else ''
        if search_keyword and courses_grouped:
            filtered_grouped = {}
            for grouped_course_name, tc_list in courses_grouped.items():
                grouped_course_name_lower = str(grouped_course_name or '').lower()
                matched_tc_list = []

                for tc in tc_list or []:
                    teacher_name = str(tc.get('SKJS', '') or '').lower()
                    tc_course_name = str(tc.get('KCM', '') or '').lower()

                    if (search_keyword in grouped_course_name_lower
                            or search_keyword in tc_course_name
                            or search_keyword in teacher_name):
                        matched_tc_list.append(tc)

                if matched_tc_list:
                    filtered_grouped[grouped_course_name] = matched_tc_list

            courses_grouped = filtered_grouped
        
        if courses_grouped:
            if self._showing_search_empty_state:
                self.clear_cards()
                self.schedule_title.setText("选择课程查看教学班")
                self._showing_search_empty_state = False

            self._api_courses_grouped = courses_grouped
            
            current_names = set(self._api_courses_grouped.keys())
            existing_names = set()
            for i in range(self.course_list.count()):
                existing_names.add(self.course_list.item(i).data(Qt.UserRole))
            
            if current_names != existing_names:
                self.course_list.clear()
                for course_name in self._api_courses_grouped:
                    item = QListWidgetItem(course_name)
                    item.setData(Qt.UserRole, course_name)
                    self.course_list.addItem(item)
            
            self.course_count_label.setText(f"共 {len(self._api_courses_grouped)} 门课程")
            self.statusBar().showMessage(f"获取到 {len(self._api_courses_grouped)} 门课程")
            if not silent:
                self.log(f"[API] 获取到 {len(self._api_courses_grouped)} 门课程")
        else:
            if not silent:
                if self._is_searching and search_keyword:
                    self.course_count_label.setText("未找到结果")
                    self.statusBar().showMessage("未找到结果")
                    self.show_search_empty_state(self._current_search_keyword)
                else:
                    self.course_count_label.setText("共 0 门课程")
                    self.statusBar().showMessage("未找到匹配的课程")
    
    def on_course_type_changed(self, text):
        """课程类型切换 - 强制刷新"""
        if not self.is_logged_in:
            return
        
        # 停止轮询，防止干扰
        self.poll_timer.stop()
        self._is_searching = False
        self.search_input.clear()
        
        # 立即清空 UI（抢占式）
        self.course_list.clear()
        self.clear_cards()
        self._api_courses_grouped = {}
        self.course_count_label.setText("切换中...")
        
        # 强制刷新（终止旧请求）
        self.refresh_courses(force=True)
        
        # 延迟启动轮询，给新请求一点时间
        QTimer.singleShot(500, lambda: self.poll_timer.start(self._poll_interval))
    
    def on_search(self):
        """搜索功能"""
        if not self.is_logged_in:
            self._show_standard_message(
                self, QMessageBox.Warning, "提示", "请先登录"
            )
            return
        
        search_text = self.search_input.text().strip()
        
        if search_text:
            self.poll_timer.stop()
            self._is_searching = True
            
            self.course_list.clear()
            self.clear_cards()
            self._api_courses_grouped = {}
            
            self.refresh_courses(keyword=search_text)
        else:
            self._is_searching = False
            self.refresh_courses()
            self.poll_timer.start(self._poll_interval)
    
    def on_course_selected(self, item):
        course_name = item.data(Qt.UserRole)
        if course_name and course_name in self._api_courses_grouped:
            self.show_course_cards(course_name, self._api_courses_grouped[course_name])
    
    def clear_cards(self):
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            widget = child.widget()
            if widget:
                # Hide and detach immediately.  deleteLater alone leaves the
                # last drop-shadow frame visible until the next event cycle.
                widget.hide()
                widget.setGraphicsEffect(None)
                widget.setParent(None)
                widget.deleteLater()
        if hasattr(self, 'cards_widget'):
            self.cards_widget.update()

    def show_search_empty_state(self, keyword):
        """显示搜索空结果状态"""
        self.clear_cards()
        self.schedule_title.setText("未找到结果")

        empty_label = QLabel(f"未找到结果：{keyword}")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {Colors.OVERLAY0};
            padding: 30px 0;
        """)
        self.cards_layout.addWidget(empty_label, 0, 0, 1, 2)
        self._showing_search_empty_state = True
    
    def show_course_cards(self, course_name, tc_list):
        self.clear_cards()
        self.schedule_title.setText(course_name)

        columns = self._course_card_columns()
        for i, tc in enumerate(tc_list):
            card = CourseCard(tc)
            card.grab_clicked.connect(self.add_to_grab_list)
            row = i // columns
            col = i % columns
            self.cards_layout.addWidget(card, row, col)
            card.show()
        self.cards_layout.activate()
        self.cards_widget.repaint()

    def _to_bool(self, value):
        """统一布尔解析，兼容 0/1、true/false、yes/no 等字符串"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'1', 'true', 'yes', 'y', 'on'}:
                return True
            if normalized in {'0', 'false', 'no', 'n', 'off', ''}:
                return False
        return bool(value)

    def _build_grab_item_text(self, course):
        """构建待抢列表文本；颜色和图形由 item visual 单独处理。"""
        course_name = course.get('KCM', '')
        teacher = course.get('SKJS', '')

        tc_id = str(course.get('JXBID', '') or '')
        is_conflict = (
            self._to_bool(course.get('isConflict', False))
            or bool(str(course.get('conflictDesc', '') or '').strip())
        )
        is_full = self._to_bool(course.get('isFull', False))
        is_preferred = tc_id in self._preferred_course_ids()

        display_text = f"{course_name} - {teacher}"
        tags = []
        if is_preferred:
            tags.append("首选")
        if is_conflict:
            tags.append("冲突换课")
        if is_full:
            tags.append("当前满员")
        if tags:
            display_text += "  ·  " + "  ·  ".join(tags)

        return display_text

    def _preferred_course_ids(self):
        preferred_ids = set()
        policy = self._active_conflict_policy
        if not isinstance(policy, dict):
            return preferred_ids
        for group in policy.get('groups', []) or []:
            preferred_id = str(group.get('preferred_id', '') or '')
            if preferred_id:
                preferred_ids.add(preferred_id)
        return preferred_ids

    def _apply_grab_item_visual(self, item, course):
        if not item or not isinstance(course, dict):
            return
        tc_id = str(course.get('JXBID', '') or '')
        preferred = tc_id in self._preferred_course_ids()
        conflict = (
            self._to_bool(course.get('isConflict', False))
            or bool(str(course.get('conflictDesc', '') or '').strip())
        )
        full = self._to_bool(course.get('isFull', False))

        item.setText(self._build_grab_item_text(course))
        item.setSizeHint(QSize(0, 48))
        item.setToolTip(self._build_grab_item_text(course))

        if preferred:
            color = QColor(Colors.MAUVE)
            background = QColor(Colors.MAUVE)
            background.setAlpha(35 if self.theme_mode == 'light' else 50)
            item.setIcon(icon('star', Colors.MAUVE, 18))
        elif conflict:
            color = QColor(Colors.YELLOW)
            background = QColor(Colors.YELLOW)
            background.setAlpha(28 if self.theme_mode == 'light' else 42)
            item.setIcon(icon('alert-triangle', Colors.YELLOW, 18))
        elif full:
            color = QColor(Colors.RED)
            background = QColor(Colors.RED)
            background.setAlpha(22 if self.theme_mode == 'light' else 34)
            item.setIcon(icon('target', Colors.RED, 17))
        else:
            color = QColor(Colors.TEXT)
            background = QColor(Qt.transparent)
            item.setIcon(icon('target', Colors.BLUE, 17))
        item.setForeground(QBrush(color))
        item.setBackground(QBrush(background))
        self.grab_list.ensure_remove_button(item)

    def _refresh_grab_item_visuals(self):
        if not hasattr(self, 'grab_list'):
            return
        for index in range(self.grab_list.count()):
            item = self.grab_list.item(index)
            course = item.data(Qt.UserRole) if item else None
            if course:
                self._apply_grab_item_visual(item, course)
    
    def add_to_grab_list(self, course):
        tc_id = course.get('JXBID', '')
        course_name = course.get('KCM', '')
        teacher = course.get('SKJS', '')
        
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                self._show_standard_message(
                    self, QMessageBox.Information, "提示", "课程已在待抢列表中"
                )
                return
        
        display_text = self._build_grab_item_text(course)
        
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, course)
        self.grab_list.addItem(item)
        self._apply_grab_item_visual(item, course)
        
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        self.log(f"[INFO] 添加待抢: {course_name} - {teacher}")
        
        if self.multi_grab_worker and self.multi_grab_worker.isRunning():
            self.multi_grab_worker.add_course(course)
        self.save_monitor_state(
            is_monitoring=self.multi_grab_worker is not None
            and self.multi_grab_worker.isRunning()
        )
    
    def _remove_grab_item(self, item):
        if not item or self.grab_list.row(item) < 0:
            return
        course = item.data(Qt.UserRole) or {}
        tc_id = course.get('JXBID', '')
        row = self.grab_list.row(item)
        self.grab_list.takeItem(row)
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")

        if self.multi_grab_worker and self.multi_grab_worker.isRunning() and tc_id:
            self.multi_grab_worker.remove_course(tc_id)

        self.log(f"[INFO] 移除待抢: {course.get('KCM', '')}")
        self.save_monitor_state(
            is_monitoring=self.multi_grab_worker is not None
            and self.multi_grab_worker.isRunning()
        )

    def show_grab_context_menu(self, _pos):
        """Retained for compatibility; removal is now an inline row action."""
        return

    def _course_time_text(self, course):
        return (
            course.get('SKSJ', '')
            or course.get('classTime', '')
            or course.get('time', '')
            or course.get('teachingTime', '')
            or ''
        )

    def _parse_time_slots(self, time_str):
        if not time_str:
            return []

        slots = []
        segments = re.split(r'[,;，；/]', str(time_str))
        day_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7,
            '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
        }

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            slot = {'weeks': set(), 'day': 0, 'periods': set()}

            week_match = re.search(r'第?(\d+)-(\d+)周(?:\(([单双])\))?', segment)
            if week_match:
                start_week = int(week_match.group(1))
                end_week = int(week_match.group(2))
                odd_even = week_match.group(3)
                for week in range(start_week, end_week + 1):
                    if odd_even == '单' and week % 2 == 0:
                        continue
                    if odd_even == '双' and week % 2 == 1:
                        continue
                    slot['weeks'].add(week)
            else:
                single_week = re.search(r'第?(\d+)周', segment)
                if single_week:
                    slot['weeks'].add(int(single_week.group(1)))

            day_match = re.search(r'(?:星期|周|礼拜)([一二三四五六日天1-7])', segment)
            if day_match:
                slot['day'] = day_map.get(day_match.group(1), 0)

            period_match = re.search(r'第?(\d+)-(\d+)节', segment)
            if period_match:
                start_period = int(period_match.group(1))
                end_period = int(period_match.group(2))
                for period in range(start_period, end_period + 1):
                    slot['periods'].add(period)
            else:
                period_singles = re.findall(r'第(\d+)节', segment)
                if period_singles:
                    for period in period_singles:
                        slot['periods'].add(int(period))
                else:
                    period_singles = re.findall(r'(\d+)节', segment)
                    for period in period_singles:
                        slot['periods'].add(int(period))
                    comma_periods = re.search(r'(\d+(?:,\d+)+)节', segment)
                    if comma_periods:
                        for period in comma_periods.group(1).split(','):
                            if period.strip():
                                slot['periods'].add(int(period.strip()))

            if slot['weeks'] and slot['day'] and slot['periods']:
                slots.append(slot)
            elif slot['day'] and slot['periods']:
                slot['weeks'] = set(range(1, 19))
                slots.append(slot)

        return slots

    def _check_time_conflict(self, time_str1, time_str2):
        slots1 = self._parse_time_slots(time_str1)
        slots2 = self._parse_time_slots(time_str2)
        if not slots1 or not slots2:
            return False

        for slot1 in slots1:
            for slot2 in slots2:
                if slot1['day'] != slot2['day']:
                    continue
                if not (slot1['weeks'] & slot2['weeks']):
                    continue
                if slot1['periods'] & slot2['periods']:
                    return True
        return False

    def _build_pending_conflict_groups(self, courses):
        """按待抢课程之间的时间冲突构建连通冲突组。"""
        indexed = []
        for index, course in enumerate(courses):
            tc_id = str(course.get('JXBID', '') or '')
            time_text = self._course_time_text(course)
            if tc_id and time_text:
                indexed.append((index, course, tc_id, time_text))

        edges = {item[2]: set() for item in indexed}
        course_by_id = {item[2]: item[1] for item in indexed}
        for left_pos in range(len(indexed)):
            _, left_course, left_id, left_time = indexed[left_pos]
            for right_pos in range(left_pos + 1, len(indexed)):
                _, right_course, right_id, right_time = indexed[right_pos]
                if self._check_time_conflict(left_time, right_time):
                    edges[left_id].add(right_id)
                    edges[right_id].add(left_id)

        groups = []
        visited = set()
        for tc_id in edges:
            if tc_id in visited or not edges[tc_id]:
                continue
            stack = [tc_id]
            component = []
            visited.add(tc_id)
            while stack:
                current = stack.pop()
                component.append(course_by_id[current])
                for neighbor in edges[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)
            if len(component) >= 2:
                groups.append(component)
        return groups

    def _show_pending_conflict_policy_dialog(self, groups):
        """提示待抢列表内部冲突，并让用户选择每组首选课程。"""
        if not groups:
            return {"enabled": True, "groups": []}

        dialog = self._prepare_dialog(QDialog(self))
        dialog.setWindowTitle("待抢列表内部冲突")
        screen_geo = QApplication.primaryScreen().availableGeometry()
        dialog.resize(min(900, int(screen_geo.width() * 0.82)), min(680, int(screen_geo.height() * 0.82)))
        dialog.setMinimumSize(700, 500)

        layout = QVBoxLayout(dialog)
        intro = QLabel(
            "检测到待抢列表里有课程之间时间互相冲突。\n\n"
            "默认安全策略：同一冲突组里，只要任意一门抢成功，就自动停止本组其它待抢课程，"
            "避免程序后续又把刚抢到的课当作冲突课退掉。\n\n"
            "如果你给某组选择了“首选优先级”：非首选课程先抢到时，首选课程仍会继续监控；"
            "后续首选课程出现余量时，可能触发自动换课。注意：换课会先退旧课再抢新课，"
            "不能保证一定抢到或一定回滚成功，请慎重选择。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        combo_records = []

        for index, group in enumerate(groups, start=1):
            frame = QFrame()
            frame.setObjectName("softCard")
            frame_layout = QVBoxLayout(frame)
            title = QLabel(f"冲突组 {index}")
            title.setStyleSheet(f"font-weight: bold; color: {Colors.YELLOW};")
            frame_layout.addWidget(title)

            detail_lines = []
            for course in group:
                course_name = course.get('KCM', '') or '未知课程'
                teacher = course.get('SKJS', '') or '未知教师'
                time_text = self._course_time_text(course) or '时间未知'
                detail_lines.append(f"• {course_name} - {teacher}｜{time_text}")
            detail = QLabel("\n".join(detail_lines))
            detail.setWordWrap(True)
            frame_layout.addWidget(detail)

            combo = SpaciousComboBox()
            combo.setMinimumHeight(42)
            combo.addItem("默认：抢到任意一门就停止本组其它课程", "")
            for course in group:
                course_name = course.get('KCM', '') or '未知课程'
                teacher = course.get('SKJS', '') or '未知教师'
                combo.addItem(f"首选：{course_name} - {teacher}", str(course.get('JXBID', '') or ''))
            frame_layout.addWidget(combo)
            combo_records.append((index, group, combo))
            container_layout.addWidget(frame)

        container_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("按此策略开始监控")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addWidget(buttons)

        result = {"accepted": False, "policy": None}

        def accept_policy():
            policy_groups = []
            for index, group, combo in combo_records:
                preferred_id = str(combo.currentData() or '')
                preferred_name = ''
                for course in group:
                    if str(course.get('JXBID', '') or '') == preferred_id:
                        preferred_name = course.get('KCM', '') or '未知课程'
                        break
                policy_groups.append({
                    "id": f"pending_conflict_group_{index}",
                    "course_ids": [str(course.get('JXBID', '') or '') for course in group],
                    "preferred_id": preferred_id,
                    "preferred_name": preferred_name,
                })
            result["accepted"] = True
            result["policy"] = {"enabled": True, "groups": policy_groups}
            dialog.accept()

        buttons.accepted.connect(accept_policy)
        buttons.rejected.connect(dialog.reject)
        dialog.exec_()

        if not result["accepted"]:
            return None
        return result["policy"]

    def _build_default_conflict_policy(self, groups):
        """为静默恢复构建默认冲突组策略：抢到任意一门即停止本组其它课程。"""
        policy_groups = []
        for index, group in enumerate(groups, start=1):
            policy_groups.append({
                "id": f"pending_conflict_group_{index}",
                "course_ids": [str(course.get('JXBID', '') or '') for course in group],
                "preferred_id": "",
                "preferred_name": "",
            })
        return {"enabled": True, "groups": policy_groups}

    def _log_conflict_policy(self, conflict_policy, restored=False):
        groups = conflict_policy.get('groups', []) if isinstance(conflict_policy, dict) else []
        if not groups:
            return
        prefix = "恢复待抢冲突组策略" if restored else "待抢冲突组策略"
        for group in groups:
            preferred_name = group.get('preferred_name') or ''
            if preferred_name:
                self.log(
                    f"[INFO] {prefix}: 首选 {preferred_name}；"
                    "非首选先成功时首选继续监控"
                )
            else:
                self.log(f"[INFO] {prefix}: 默认抢到任意一门即停止本组其它课程")

    def start_monitoring(
        self,
        conflict_policy=None,
        skip_policy_dialog=False,
        skip_swap_risk_dialog=False,
    ):
        if not self.is_logged_in:
            self._show_standard_message(
                self, QMessageBox.Warning, "提示", "请先登录"
            )
            return
        
        if self.grab_list.count() == 0:
            self._show_standard_message(
                self, QMessageBox.Warning, "提示", "请先添加待抢课程"
            )
            return
        
        courses = []
        for i in range(self.grab_list.count()):
            item = self.grab_list.item(i)
            course = item.data(Qt.UserRole)
            if course:
                courses.append(course)

        pending_conflict_groups = self._build_pending_conflict_groups(courses)
        if skip_policy_dialog:
            if not isinstance(conflict_policy, dict):
                conflict_policy = self._build_default_conflict_policy(pending_conflict_groups)
                if conflict_policy.get('groups'):
                    self.log("[WARN] 未找到上次冲突组策略，恢复时按默认安全策略继续监控")
            else:
                self.log("[INFO] 已复用上次待抢冲突组策略，恢复监控不再弹窗确认")
            self._log_conflict_policy(conflict_policy, restored=True)
        else:
            conflict_policy = self._show_pending_conflict_policy_dialog(pending_conflict_groups)
            if conflict_policy is None:
                self.log("[INFO] 用户取消启动：未确认待抢列表内部冲突策略")
                return
            self._log_conflict_policy(conflict_policy)

        self._active_conflict_policy = conflict_policy
        self._refresh_grab_item_visuals()

        conflict_courses = [
            course for course in courses
            if self._to_bool(course.get('isConflict', False))
            or bool(str(course.get('conflictDesc', '') or '').strip())
        ]
        if conflict_courses and skip_swap_risk_dialog:
            self._swap_risk_confirmed = True
            self.log("[INFO] 已复用上次冲突换课风险确认，恢复监控不再弹窗")
        elif conflict_courses:
            names = [str(course.get('KCM', '') or '未知课程') for course in conflict_courses]
            preview = '、'.join(names[:5])
            if len(names) > 5:
                preview += f" 等 {len(names)} 门"
            reply = self._show_centered_message(
                QMessageBox.Warning,
                "冲突换课风险确认",
                f"检测到待选课程与当前已选课程存在时间冲突：\n\n{preview}\n\n"
                "自动换课会先退掉冲突的旧课程，再尝试选择目标课程。"
                "在多人同时抢课、旧课名额被他人占用或网络异常时，"
                "目标课程可能抢不到，旧课程也无法保证回滚成功。\n\n"
                "请确认你已理解风险，并慎重决定是否继续监控。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
                yes_text="继续监控",
                no_text="取消",
            )
            if reply != QMessageBox.Yes:
                self.log("[INFO] 用户取消启动：未接受冲突换课风险")
                return
            self._swap_risk_confirmed = True
        else:
            self._swap_risk_confirmed = False
        
        # 获取 Server酱 key
        serverchan_key = ''
        if self.serverchan_enabled:
            serverchan_key = self.serverchan_key_input.text().strip()
            self.serverchan_key = serverchan_key

        webhook_channels = []
        if self.developer_mode_enabled:
            valid, error = validate_webhook_channels(self.developer_webhooks)
            if valid:
                webhook_channels = normalize_webhook_channels(self.developer_webhooks)
            else:
                self.log(f"[WARN] 自定义 Webhook 配置无效，本次未启用: {error}")
	        
        self.log(f"[INFO] 开始监控 {len(courses)} 门课程 (HTTP并发: {self.concurrency_spin.value()})")
        if serverchan_key:
            self.log(f"[INFO] Server酱通知已启用")
        if webhook_channels:
            enabled_count = sum(1 for item in webhook_channels if item.get('enabled', True))
            self.log(f"[INFO] 开发者模式自定义 Webhook 已启用，启用通道: {enabled_count}")
	        
        self.multi_grab_worker = MultiGrabWorker(
            courses=courses,
            student_code=self.student_code,
            batch_code=self.batch_code,
            token=self.token,
            cookies=self.cookies,
            campus=self.campus,  # 传入校区代码
            username=self.username_input.text(),
            password=self.password_input.text(),
            max_workers=self.concurrency_spin.value(),
            serverchan_key=serverchan_key,
            webhook_channels=webhook_channels,
            conflict_policy=conflict_policy,
        )
        
        self.multi_grab_worker.success.connect(self.on_grab_success)
        self.multi_grab_worker.failed.connect(self.on_grab_failed)
        self.multi_grab_worker.status.connect(self.on_grab_status)
        self.multi_grab_worker.need_relogin.connect(self.on_need_relogin)
        self.multi_grab_worker.course_available.connect(self.on_course_available)
        self.multi_grab_worker.session_updated.connect(self.on_session_updated)
        self.multi_grab_worker.finished.connect(self.on_worker_finished)
        self.multi_grab_worker.heartbeat.connect(self.update_heartbeat)
        self.multi_grab_worker.courses_retired.connect(self.on_courses_retired)

        # 写入守护信号并按需启动 watchdog
        self.write_watchdog_signal('start', pid=os.getpid())
        self.start_watchdog_process()
        
        self.multi_grab_worker.start()

        # 立即保存监控状态（即使程序崩溃也能恢复）
        self.save_monitor_state(is_monitoring=True)
        
        self.start_grab_btn.setEnabled(False)
        self.stop_grab_btn.setEnabled(True)
        self.run_indicator.setText("监控中 · 已扫描 0 次")
        self.run_indicator.setStyleSheet(f"""
            QLabel {{
                color: {Colors.GREEN};
                background-color: {Colors.SURFACE0};
                font-size: 13px;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 16px;
                margin: 2px 8px;
            }}
        """)
        self.statusBar().showMessage("监控中...")
    
    def stop_monitoring(self, clear_state=True, reason='manual'):
        was_monitoring = self.multi_grab_worker is not None

        if self.multi_grab_worker:
            self.multi_grab_worker.stop()
            wait_ms = 10000 if reason == 'update' else 5000
            if not self.multi_grab_worker.wait(wait_ms):
                self._logger.warning(f"停止监控超时: reason={reason}")
                if reason == 'update':
                    return False
            self.multi_grab_worker = None
        
        self.start_grab_btn.setEnabled(True)
        self.stop_grab_btn.setEnabled(False)
        self.run_indicator.setText("待机")
        self.run_indicator.setStyleSheet(f"""
            QLabel {{
                color: {Colors.OVERLAY0};
                background-color: {Colors.SURFACE0};
                font-size: 13px;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 16px;
                margin: 2px 8px;
            }}
        """)
        if reason == 'logout':
            if was_monitoring:
                self.statusBar().showMessage("已退出登录（监控已停止）")
                self.log("[INFO] 已退出登录（监控已停止）")
            else:
                self.statusBar().showMessage("已退出登录")
        elif reason == 'relogin':
            if was_monitoring:
                self.statusBar().showMessage("会话过期，监控已暂停")
                self.log("[WARN] 会话过期，监控已暂停，准备自动重登")
            else:
                self.statusBar().showMessage("会话过期，准备自动重登")
        elif reason == 'close':
            # 关闭程序时不追加停止日志，避免与手动停止混淆
            pass
        elif reason == 'update':
            self.statusBar().showMessage("正在退出并安装更新")
            self.log("[INFO] 更新安装前已停止监控")
        else:
            self.statusBar().showMessage("监控已停止")
            self.log("[INFO] 监控已停止")
        
        # 只有用户主动停止时才清除状态文件
        if clear_state:
            self.write_watchdog_signal('stop')
            self.clear_monitor_state()
            if reason not in ('relogin',):
                self._active_conflict_policy = None
                self._swap_risk_confirmed = False
                self._refresh_grab_item_visuals()
        return True
    
    def on_grab_success(self, msg, course):
        """抢课成功回调 - 带异常保护"""
        try:
            self.log(f"[SUCCESS] {msg}")
            
            tc_id = course.get('JXBID', '') if course else ''
            for i in range(self.grab_list.count()):
                item = self.grab_list.item(i)
                if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                    self.grab_list.takeItem(i)
                    break
            
            self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
            self.save_monitor_state(
                is_monitoring=self.multi_grab_worker is not None
                and self.multi_grab_worker.isRunning()
            )
            self._show_centered_message(
                QMessageBox.Information,
                "抢课成功",
                msg,
                icon_name_override="circle-check",
                icon_color_override=Colors.GREEN,
            )
        except Exception as e:
            try:
                self._logger.error(f"on_grab_success 异常: {str(e)[:50]}")
            except Exception:
                pass

    def on_courses_retired(self, tc_ids, reason):
        """worker 自动停止冲突待抢课程后，同步刷新 UI 列表。"""
        try:
            remove_ids = {str(tc_id) for tc_id in (tc_ids or [])}
            if not remove_ids:
                return
            for i in range(self.grab_list.count() - 1, -1, -1):
                item = self.grab_list.item(i)
                course = item.data(Qt.UserRole) if item else None
                if course and str(course.get('JXBID', '') or '') in remove_ids:
                    self.grab_list.takeItem(i)

            self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
            self.log(f"[INFO] {reason}")
            self.save_monitor_state(
                is_monitoring=self.multi_grab_worker is not None
                and self.multi_grab_worker.isRunning()
            )
        except Exception as e:
            try:
                self._logger.error(f"on_courses_retired 异常: {str(e)[:50]}")
            except Exception:
                pass
    
    def on_grab_failed(self, msg):
        """抢课失败回调 - 带异常保护"""
        try:
            self.log(f"[ERROR] {msg}")
        except Exception:
            pass
    
    def on_grab_status(self, msg):
        """状态更新回调 - 带异常保护"""
        try:
            self.log(msg)
            self.statusBar().showMessage(msg)
        except Exception:
            pass
    
    def on_session_updated(self, token, cookies):
        """Session 更新回调 - 带异常保护"""
        try:
            self.token = token
            self.cookies = cookies
            self.log("[INFO] Session 已同步更新")
            QTimer.singleShot(120, lambda: self._prefetch_curriculum(force=True))
        except Exception:
            pass
    
    def on_worker_finished(self):
        """Worker 完成回调 - 带异常保护"""
        try:
            self.start_grab_btn.setEnabled(True)
            self.stop_grab_btn.setEnabled(False)
            
            if self._pending_monitor_courses and not self.is_logged_in:
                self.log("[INFO] Worker 异常退出，尝试自动重登...")
                self._auto_relogin_and_resume()
        except Exception as e:
            try:
                self._logger.error(f"on_worker_finished 异常: {str(e)[:50]}")
            except Exception:
                pass
    
    def on_need_relogin(self):
        """需要重登回调 - 带异常保护"""
        try:
            self.log("[WARN] Session过期，准备自动重登...")
            
            pending_courses = []
            for i in range(self.grab_list.count()):
                item = self.grab_list.item(i)
                course = item.data(Qt.UserRole)
                if course:
                    pending_courses.append(course)
            
            self._pending_monitor_courses = pending_courses
            self._pending_resume_conflict_policy = self._active_conflict_policy
            self._pending_resume_swap_risk_confirmed = self._swap_risk_confirmed
            self.log(f"[INFO] 已保存 {len(pending_courses)} 门待抢课程")
	            
            self.stop_monitoring(clear_state=False, reason='relogin')
            self._auto_relogin_and_resume()
        except Exception as e:
            try:
                self._logger.error(f"on_need_relogin 异常: {str(e)[:50]}")
            except Exception:
                pass
    
    def _auto_relogin_and_resume(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            self.log("[ERROR] 无法自动重登：缺少用户名或密码")
            return
        
        self._is_manual_login_attempt = False
        self.log("[INFO] 开始自动重登...")
        self.login_btn.setEnabled(False)
        self.login_btn.setText("自动重登中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self.login_worker = LoginWorker(username, password)
        self.login_worker.success.connect(self.on_login_success)
        self.login_worker.failed.connect(self._on_auto_relogin_failed)
        self.login_worker.status.connect(self._show_login_status)
        self.login_worker.start()
    
    def _on_auto_relogin_failed(self, msg):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")
        self.progress_bar.setVisible(False)
        self.log(f"[ERROR] 自动重登失败: {msg}")
        if '登录名或密码不正确' in str(msg):
            self._auto_relogin_retry_count = 0
            self.save_monitor_state(is_monitoring=False)
            self.statusBar().showMessage("自动重登已停止：请重新输入正确的账号密码")
            self._show_standard_message(
                self,
                QMessageBox.Warning,
                "自动重登已停止",
                "保存的账号或密码不正确，请修改后重新登录。",
            )
            return
        self._auto_relogin_retry_count += 1
        retry_delay_ms = min(10000, 2000 * self._auto_relogin_retry_count)
        self.log(f"[INFO] {retry_delay_ms // 1000}s 后自动重试重登 (第 {self._auto_relogin_retry_count} 次)")
        self.statusBar().showMessage("自动重登失败，正在重试...")
        QTimer.singleShot(retry_delay_ms, self._auto_relogin_and_resume)
    
    def _resume_monitoring(self):
        if not self._pending_monitor_courses:
            return
        
        self.log(f"[INFO] 恢复监控 {len(self._pending_monitor_courses)} 门课程...")
        
        for course in self._pending_monitor_courses:
            tc_id = course.get('JXBID', '')
            exists = False
            for i in range(self.grab_list.count()):
                item = self.grab_list.item(i)
                if item and item.data(Qt.UserRole) and item.data(Qt.UserRole).get('JXBID') == tc_id:
                    exists = True
                    break
            
            if not exists:
                display_text = self._build_grab_item_text(course)
                
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, course)
                self.grab_list.addItem(item)
                self._apply_grab_item_visual(item, course)
        
        self.grab_count_label.setText(f"待抢: {self.grab_list.count()} 门")
        self._pending_monitor_courses = []
	        
        resume_policy = self._pending_resume_conflict_policy or self._active_conflict_policy
        resume_swap_risk_confirmed = (
            self._pending_resume_swap_risk_confirmed or self._swap_risk_confirmed
        )
        self._pending_resume_conflict_policy = None
        self._pending_resume_swap_risk_confirmed = False
        QTimer.singleShot(
            500,
            lambda policy=resume_policy: self.start_monitoring(
                conflict_policy=policy,
                skip_policy_dialog=True,
                skip_swap_risk_dialog=resume_swap_risk_confirmed,
            )
        )
    
    def on_course_available(self, course_name, teacher, remain, capacity):
        self.log(f"[ALERT] {course_name} 有余量，余量={remain}/{capacity}")
    
    def _start_polling(self):
        self.refresh_courses()
        self.poll_timer.start(self._poll_interval)
        self.log(f"[INFO] 自动轮询已启动 (间隔 {self._poll_interval/1000}s)")
    
    def _on_poll_timer(self):
        if not self.is_logged_in:
            self.poll_timer.stop()
            return
        
        if self._is_searching:
            return
        
        self.refresh_courses(silent=True)
    
    def closeEvent(self, event):
        """程序关闭事件"""
        if self._installing_update:
            # 更新流程已经保存过状态并停止 Watchdog，避免把恢复标记覆盖为 False。
            self.save_config()
            event.accept()
            return

        # 保存监控状态（如果正在监控中则标记 is_monitoring=True，用于重启恢复）
        is_monitoring = self.multi_grab_worker is not None and self.multi_grab_worker.isRunning()
        self.save_monitor_state(is_monitoring=is_monitoring)
        
        self.poll_timer.stop()
        # 关闭程序时不清除状态文件，让程序可以自动重启恢复
        self.stop_monitoring(clear_state=False, reason='close')
        self.save_config()
        event.accept()
