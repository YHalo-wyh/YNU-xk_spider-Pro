import os
import tempfile
import unittest
import io
import threading
import time
from unittest.mock import Mock, patch
from types import SimpleNamespace

import numpy as np
import requests
from PIL import Image

from xk_spider.storage import monitor_state_batch_status
from xk_spider.gui.workers import MultiGrabWorker, UpdateCheckWorker
from xk_spider.gui.ui import MainWindow, QMessageBox
from build import resolve_ocr_data_files, verify_ocr_helper_runtime
from run_ocr_helper import CaptchaClassifier


class OCRPackagingTests(unittest.TestCase):
    def test_preprocess_matches_ddddocr_model_normalization(self):
        image = Image.fromarray(np.array([[0, 255]], dtype=np.uint8), mode="L")
        payload = io.BytesIO()
        image.save(payload, format="PNG")

        tensor = CaptchaClassifier._preprocess(payload.getvalue())

        self.assertAlmostEqual(float(tensor.min()), -1.0, places=5)
        self.assertAlmostEqual(float(tensor.max()), 1.0, places=5)

    def test_resolves_ocr_assets_from_active_environment(self):
        for path in resolve_ocr_data_files():
            self.assertTrue(os.path.isfile(path), path)

    def test_runtime_smoke_check_rejects_non_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_helper = os.path.join(directory, "OCRHelper.exe")
            with open(fake_helper, "wb") as target:
                target.write(b"not an executable")
            self.assertFalse(verify_ocr_helper_runtime(fake_helper, timeout=1))


class MonitorStateBatchTests(unittest.TestCase):
    def test_matches_current_batch(self):
        state = {"batch_code": "current", "courses": [{"JXBID": "1"}]}
        self.assertEqual(
            monitor_state_batch_status(state, "current"),
            "match",
        )

    def test_rejects_different_or_unknown_batch(self):
        courses = [{"JXBID": "1"}]
        self.assertEqual(
            monitor_state_batch_status(
                {"batch_code": "old", "courses": courses},
                "current",
            ),
            "mismatch",
        )
        self.assertEqual(
            monitor_state_batch_status({"courses": courses}, "current"),
            "unknown",
        )


class UpdateCheckFallbackTests(unittest.TestCase):
    def test_extracts_latest_tag_from_redirect_url(self):
        worker = UpdateCheckWorker("v2.7.0")
        self.assertEqual(
            worker._version_from_release_url(
                "https://github.com/YHalo-wyh/YNU-xk_spider-Pro/releases/tag/v2.8.0"
            ),
            "2.8.0",
        )
        self.assertTrue(worker._compare_versions("2.8.0", "v2.7.0"))


class CourseMonitorDiagnosticsTests(unittest.TestCase):
    @staticmethod
    def _worker(response):
        worker = MultiGrabWorker.__new__(MultiGrabWorker)
        worker.student_code = "student"
        worker.batch_code = "batch-current"
        worker.campus = "02"
        worker.token = "token"
        worker.cookies = "JSESSIONID=current"
        worker._logger = Mock()
        worker._auth_state_lock = threading.Lock()
        worker._auth_generation = 0
        worker._auth_401_generation = 0
        worker._auth_401_streak = 0
        worker._auth_401_last_at = 0.0
        worker._request_authenticated = Mock(return_value=(0, response))
        worker._probe_current_session = Mock(return_value=False)
        worker._handle_session_expired = Mock(return_value=False)
        return worker

    @staticmethod
    def _course():
        return {
            "JXBID": "target-class",
            "KCM": "测试课程",
            "type": "major",
            "number": "COURSE001",
        }

    def test_http_401_is_expired_but_plain_403_is_not(self):
        worker = MultiGrabWorker.__new__(MultiGrabWorker)
        response = requests.Response()
        response.status_code = 401
        response.history = []
        self.assertTrue(worker._is_session_expired(response=response))

        response = requests.Response()
        response.status_code = 403
        response.history = []
        response._content = b"rate limit"
        self.assertFalse(worker._is_session_expired(response=response))

        response = requests.Response()
        response.status_code = 403
        response.history = []
        response._content = "登录状态已过期".encode("utf-8")
        self.assertTrue(worker._is_session_expired(response=response))

    def test_missing_teaching_class_reports_specific_reason(self):
        response = Mock()
        response.status_code = 200
        response.history = []
        response.json.return_value = {
            "code": "1",
            "dataList": [
                {
                    "tcList": [
                        {
                            "teachingClassID": "another-class",
                            "classCapacity": 50,
                            "numberOfFirstVolunteer": 50,
                        }
                    ]
                }
            ],
        }
        worker = self._worker(response)

        remain, capacity, details = worker._api_query_course_capacity(
            self._course()
        )

        self.assertIsNone(remain)
        self.assertIsNone(capacity)
        self.assertEqual(details["query_error"], "teaching_class_not_found")

    def test_single_401_waits_for_confirmation(self):
        response = requests.Response()
        response.status_code = 401
        response.history = []
        worker = self._worker(response)

        remain, capacity, details = worker._api_query_course_capacity(
            self._course()
        )

        self.assertIsNone(remain)
        self.assertIsNone(capacity)
        self.assertEqual(details["query_error"], "auth_challenge_unconfirmed")
        worker._handle_session_expired.assert_not_called()

    def test_two_consecutive_401s_request_relogin(self):
        response = requests.Response()
        response.status_code = 401
        response.history = []
        worker = self._worker(response)

        first = worker._api_query_course_capacity(self._course())
        second = worker._api_query_course_capacity(self._course())

        self.assertEqual(first[2]["query_error"], "auth_challenge_unconfirmed")
        self.assertEqual(second, ("session_expired", None, None))
        worker._probe_current_session.assert_called_once_with(0)
        worker._handle_session_expired.assert_called_once()

    def test_cross_endpoint_success_prevents_relogin_after_two_401s(self):
        unauthorized = requests.Response()
        unauthorized.status_code = 401
        unauthorized.history = []
        successful = Mock()
        successful.status_code = 200
        successful.history = []
        successful.json.return_value = {
            "code": "1",
            "dataList": [{
                "tcList": [{
                    "teachingClassID": "target-class",
                    "classCapacity": 50,
                    "numberOfFirstVolunteer": 50,
                }]
            }],
        }
        worker = self._worker(unauthorized)
        worker._probe_current_session.return_value = True
        worker._request_authenticated.side_effect = [
            (0, unauthorized), (0, unauthorized), (0, successful)
        ]

        first = worker._api_query_course_capacity(self._course())
        second = worker._api_query_course_capacity(self._course())

        self.assertEqual(first[2]["query_error"], "auth_challenge_unconfirmed")
        self.assertEqual(second[:2], (0, 50))
        worker._probe_current_session.assert_called_once_with(0)
        worker._handle_session_expired.assert_not_called()

    def test_success_between_401s_resets_confirmation_streak(self):
        unauthorized = requests.Response()
        unauthorized.status_code = 401
        unauthorized.history = []
        successful = Mock()
        successful.status_code = 200
        successful.history = []
        successful.json.return_value = {
            "code": "1",
            "dataList": [{
                "tcList": [{
                    "teachingClassID": "target-class",
                    "classCapacity": 50,
                    "numberOfFirstVolunteer": 50,
                }]
            }],
        }
        worker = self._worker(unauthorized)
        worker._request_authenticated.side_effect = [
            (0, unauthorized), (0, successful), (0, unauthorized)
        ]

        self.assertEqual(
            worker._api_query_course_capacity(self._course())[2]["query_error"],
            "auth_challenge_unconfirmed",
        )
        self.assertEqual(
            worker._api_query_course_capacity(self._course())[:2], (0, 50)
        )
        self.assertEqual(
            worker._api_query_course_capacity(self._course())[2]["query_error"],
            "auth_challenge_unconfirmed",
        )
        worker._handle_session_expired.assert_not_called()

    def test_stale_401_retries_with_current_generation_without_relogin(self):
        unauthorized = requests.Response()
        unauthorized.status_code = 401
        unauthorized.history = []
        successful = Mock()
        successful.status_code = 200
        successful.history = []
        successful.json.return_value = {
            "code": "1",
            "dataList": [{
                "tcList": [{
                    "teachingClassID": "target-class",
                    "classCapacity": 50,
                    "numberOfFirstVolunteer": 50,
                }]
            }],
        }
        worker = self._worker(unauthorized)
        worker._auth_generation = 1
        worker._request_authenticated.side_effect = [
            (0, unauthorized), (1, successful)
        ]

        remain, capacity, _ = worker._api_query_course_capacity(self._course())

        self.assertEqual((remain, capacity), (0, 50))
        worker._handle_session_expired.assert_not_called()

    def test_authenticated_request_replaces_old_session_cookie(self):
        response = requests.Response()
        response.status_code = 200
        session = requests.Session()
        session.cookies.set(
            "JSESSIONID", "old", domain="xk.ynu.edu.cn", path="/"
        )
        worker = self._worker(response)
        worker.cookies = "JSESSIONID=new; route=active"
        worker._get_http_session = Mock(return_value=session)
        worker._request_with_session = Mock(return_value=response)

        generation, actual = MultiGrabWorker._request_authenticated(
            worker, "GET", "https://xk.ynu.edu.cn/protected"
        )

        self.assertEqual(generation, 0)
        self.assertIs(actual, response)
        self.assertEqual(session.cookies.get_dict(), {
            "JSESSIONID": "new", "route": "active"
        })

    def test_query_confirmed_selection_emits_success_before_cleanup(self):
        course = self._course()
        course["SKJS"] = "测试教师"
        with patch("xk_spider.gui.workers.OCR_AVAILABLE", False):
            worker = MultiGrabWorker(
                [course], "student", "batch-current", "token",
                "JSESSIONID=current", max_workers=1,
            )
        worker._last_login_check_time = time.time()
        worker._api_query_course_capacity = Mock(return_value=(
            1,
            50,
            {"isFull": False, "isChoose": True},
        ))
        success_events = []
        worker.success.connect(
            lambda message, selected: success_events.append((message, selected))
        )

        worker._monitor_course_loop(course)

        self.assertEqual(len(success_events), 1)
        self.assertIn("已确认选中", success_events[0][0])
        self.assertEqual(success_events[0][1]["JXBID"], "target-class")
        self.assertEqual(worker._get_courses_snapshot(), [])


class MonitorCompletionUITests(unittest.TestCase):
    def test_empty_watchlist_warning_uses_centered_dialog(self):
        centered_message = Mock()
        window = SimpleNamespace(
            is_logged_in=True,
            grab_list=Mock(count=Mock(return_value=0)),
            _show_centered_message=centered_message,
        )

        MainWindow.start_monitoring(window)

        centered_message.assert_called_once_with(
            QMessageBox.Warning,
            "提示",
            "待抢列表为空，请先添加待抢课程",
        )

    def test_authoritative_completion_clears_ui_and_saved_watchlist(self):
        status_bar = Mock()
        window = SimpleNamespace(
            grab_list=Mock(),
            grab_count_label=Mock(),
            _pending_monitor_courses=[{"JXBID": "target-class"}],
            _active_conflict_policy={"groups": []},
            _swap_risk_confirmed=True,
            _refresh_grab_item_visuals=Mock(),
            save_monitor_state=Mock(),
            write_watchdog_signal=Mock(),
            statusBar=Mock(return_value=status_bar),
            _logger=Mock(),
        )

        MainWindow.on_all_courses_processed(window)

        window.grab_list.clear.assert_called_once_with()
        window.grab_count_label.setText.assert_called_once_with("待抢: 0 门")
        self.assertEqual(window._pending_monitor_courses, [])
        self.assertIsNone(window._active_conflict_policy)
        self.assertFalse(window._swap_risk_confirmed)
        window.save_monitor_state.assert_called_once_with(is_monitoring=False)
        window.write_watchdog_signal.assert_called_once_with("stop")
        status_bar.showMessage.assert_called_once_with(
            "所有课程已处理完毕，待抢列表已清空"
        )

    def test_worker_emits_authoritative_completion_signal(self):
        course = {"JXBID": "target-class", "KCM": "测试课程"}
        with patch("xk_spider.gui.workers.OCR_AVAILABLE", False):
            worker = MultiGrabWorker(
                [course], "student", "batch-current", "token",
                "JSESSIONID=current", max_workers=1,
            )
        worker._monitor_course_loop = lambda selected: worker._remove_course_safe(
            selected["JXBID"]
        )
        worker._health_check_loop = lambda: None
        events = []
        worker.all_courses_processed.connect(lambda: events.append("done"))

        worker.run()

        self.assertEqual(events, ["done"])
        self.assertEqual(worker._get_courses_snapshot(), [])


if __name__ == "__main__":
    unittest.main()
