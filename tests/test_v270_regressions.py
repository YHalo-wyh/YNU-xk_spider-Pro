import unittest
from unittest.mock import Mock

import requests

from xk_spider.storage import monitor_state_batch_status
from xk_spider.gui.workers import MultiGrabWorker, UpdateCheckWorker


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
        worker = UpdateCheckWorker("v2.6.0")
        self.assertEqual(
            worker._version_from_release_url(
                "https://github.com/YHalo-wyh/YNU-xk_spider-Pro/releases/tag/v2.7.0"
            ),
            "2.7.0",
        )
        self.assertTrue(worker._compare_versions("2.7.0", "v2.6.0"))


class CourseMonitorDiagnosticsTests(unittest.TestCase):
    @staticmethod
    def _worker(response):
        worker = MultiGrabWorker.__new__(MultiGrabWorker)
        worker.student_code = "student"
        worker.batch_code = "batch-current"
        worker.campus = "02"
        worker.token = "token"
        worker.cookies = ""
        worker._logger = Mock()
        worker._request = Mock(return_value=response)
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

    def test_http_401_and_403_are_session_expired(self):
        worker = MultiGrabWorker.__new__(MultiGrabWorker)
        for status in (401, 403):
            response = requests.Response()
            response.status_code = status
            response.history = []
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

    def test_unauthorized_capacity_query_requests_relogin(self):
        response = requests.Response()
        response.status_code = 401
        response.history = []
        worker = self._worker(response)

        remain, capacity, details = worker._api_query_course_capacity(
            self._course()
        )

        self.assertEqual(remain, "session_expired")
        self.assertIsNone(capacity)
        self.assertIsNone(details)
        worker._handle_session_expired.assert_called_once()


if __name__ == "__main__":
    unittest.main()
