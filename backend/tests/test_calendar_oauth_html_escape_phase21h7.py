import asyncio
import unittest
from unittest.mock import patch

from app.routers import calendar as calendar_router


class _FakeRequest:
    url = "http://localhost:8000/api/calendar/auth/callback?code=test"


class CalendarOAuthHtmlEscapePhase21H7Tests(unittest.TestCase):
    def test_oauth_error_query_is_html_escaped(self):
        payload = '<script>alert("x")</script>'
        response = asyncio.run(
            calendar_router.calendar_auth_callback(
                _FakeRequest(),
                code=None,
                error=payload,
            )
        )
        body = response.body.decode("utf-8")
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_calendar_integration_exception_is_html_escaped(self):
        payload = '<img src=x onerror="alert(1)">'
        with patch.object(
            calendar_router,
            "complete_calendar_auth",
            side_effect=calendar_router.CalendarIntegrationError(payload),
        ):
            response = asyncio.run(
                calendar_router.calendar_auth_callback(
                    _FakeRequest(),
                    code="test",
                    error=None,
                )
            )
        body = response.body.decode("utf-8")
        self.assertNotIn("<img", body)
        self.assertIn("&lt;img", body)

    def test_unexpected_exception_details_are_not_reflected(self):
        payload = '<svg onload="alert(1)"></svg>'
        with patch.object(
            calendar_router,
            "complete_calendar_auth",
            side_effect=RuntimeError(payload),
        ):
            response = asyncio.run(
                calendar_router.calendar_auth_callback(
                    _FakeRequest(),
                    code="test",
                    error=None,
                )
            )
        body = response.body.decode("utf-8")
        self.assertNotIn(payload, body)
        self.assertNotIn("<svg", body)
        self.assertIn("Check the backend log for technical details.", body)


if __name__ == "__main__":
    unittest.main()
