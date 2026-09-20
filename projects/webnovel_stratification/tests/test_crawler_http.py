"""Offline HTTP policy tests; no real network or digest calculations."""
from email.message import Message
from email.utils import formatdate
from http.client import RemoteDisconnected
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import crawler_http as http


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Store:
    def __init__(self):
        self.state = {"blocked_until": 0.0, "next_request_at": 0.0, "blocked_reason": None}
        self.reservations = []

    def platform_status(self, platform):
        return dict(self.state)

    def reserve_request(self, platform, delay, now=None):
        slot = max(now, self.state["next_request_at"], self.state["blocked_until"])
        self.state["next_request_at"] = slot + delay
        self.reservations.append((now, delay, slot))
        return slot - now

    def block_platform(self, platform, reason, seconds, now=None):
        self.state["blocked_until"] = max(self.state["blocked_until"], now + seconds)
        self.state["blocked_reason"] = reason


class WireResponse:
    def __init__(self, body=b"<html><h1>Book</h1></html>", status=200, content_type="text/html", **headers):
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        for key, value in headers.items():
            self.headers[key.replace("_", "-")] = str(value)
        self.stream = BytesIO(body)

    def read(self, size):
        return self.stream.read(size)

    def close(self):
        self.stream.close()


def robots(body=b"User-agent: *\nAllow: /\n"):
    return WireResponse(body, content_type="text/plain")


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = Store()
        self.patches = [patch.object(http.time, name, getattr(self.clock, method))
                        for name, method in (("time", "time"), ("monotonic", "time"), ("sleep", "sleep"))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def client(self, *responses, platform="qidian", **kwargs):
        client = http.Client(platform, self.store, **kwargs)
        client._opener.open = Mock(side_effect=responses)
        return client

    def test_all_requests_count_and_persist_pacing(self):
        client = self.client(robots(), WireResponse(), WireResponse())
        client.get("https://m.qidian.com/category/male")
        client.get("https://m.qidian.com/book/12/")
        self.assertEqual(client.requests, 3)
        self.assertEqual(len(self.store.reservations), 3)
        self.assertEqual([entry[2] for entry in self.store.reservations], [1000, 1006, 1012])
        self.assertEqual(self.store.state["next_request_at"], 1018)
        self.assertGreater(client.bytes, 0)
        self.assertLessEqual(max(self.clock.sleeps), 1)
        second = self.client(robots(), WireResponse())
        second.get("https://m.qidian.com/book/13/")
        self.assertEqual(self.store.reservations[-2][2], 1018)

    def test_hard_url_scope_without_network(self):
        for url in (
            "https://m.qidian.com/chapter/12/34/", "https://m.qidian.com/book/12/34.html",
            "https://read.qidian.com/book/12/", "https://m.qidian.com.evil.invalid/book/12/",
            "http://m.qidian.com/book/12/", "https://user:secret@m.qidian.com/book/12/",
            "https://m.qidian.com/book/12/?chapterid=34", "https://m.qidian.com/book/%31%32/",
        ):
            with self.subTest(url=url):
                client = self.client()
                with self.assertRaises(http.FetchError) as caught:
                    client.get(url)
                self.assertEqual(caught.exception.category, "invalid")
                self.assertEqual(client.requests, 0)

    def test_jjwxc_chapter_query_is_rejected(self):
        client = self.client(platform="jjwxc")
        with self.assertRaises(http.FetchError):
            client.get("https://www.jjwxc.net/onebook.php?novelid=1&chapterid=2")
        with self.assertRaises(http.FetchError):
            client.get("https://www.jjwxc.net/onebook.php?novelid=1&ChapterId=2")
        self.assertEqual(client.requests, 0)

    def test_redirect_is_checked_and_not_followed_to_chapter(self):
        client = self.client(robots(), WireResponse(status=302, Location="/chapter/12/34/"))
        with self.assertRaises(http.FetchError) as caught:
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(caught.exception.category, "invalid")
        self.assertEqual(client.requests, 2)
        self.assertEqual(client._opener.open.call_count, 2)

    def test_safe_redirect_is_a_separate_paced_request(self):
        client = self.client(robots(), WireResponse(status=302, Location="/book/13/"), WireResponse())
        response = client.get("https://m.qidian.com/book/12/")
        self.assertEqual(response.url, "https://m.qidian.com/book/13/")
        self.assertEqual(client.requests, 3)
        self.assertEqual(self.clock.now, 1012)

    def test_status_200_challenge_blocks_whole_platform(self):
        for body in ("<html>请完成验证</html>".encode(), b'<html><script src="/probe.js"></script></html>'):
            with self.subTest(body=body):
                self.store = Store()
                client = self.client(robots(), WireResponse(body))
                with self.assertRaises(http.FetchError) as caught:
                    client.get("https://m.qidian.com/category/male")
                self.assertEqual(caught.exception.category, "blocked")
                self.assertEqual(caught.exception.retry_after, 86400)
                with self.assertRaises(http.FetchError):
                    client.get("https://m.qidian.com/book/12/")
                self.assertEqual(client.requests, 2)

    def test_english_challenge_in_legitimate_metadata_is_not_blocked(self):
        client = self.client(robots(), WireResponse(b"<html><h1>The challenge</h1></html>"))
        self.assertEqual(client.get("https://m.qidian.com/book/12/").status, 200)

    def test_429_uses_retry_after_and_stops(self):
        for value, expected in (("60", 3600), ("7200", 7200), ("garbage", 3600),
                                (formatdate(self.clock.now + 7206, usegmt=True), 7200)):
            with self.subTest(value=value):
                self.store = Store()
                client = self.client(robots(), WireResponse(status=429, Retry_After=value))
                with self.assertRaises(http.FetchError) as caught:
                    client.get("https://m.qidian.com/book/12/")
                self.assertEqual(caught.exception.retry_after, expected)
                self.assertEqual(caught.exception.category, "blocked")
                self.assertEqual(client.requests, 2)
                self.clock.now = 1000

    def test_remote_disconnect_is_retryable_without_inline_retry(self):
        client = self.client(robots(), RemoteDisconnected("private token=never-log"))
        with self.assertRaises(http.FetchError) as caught:
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(caught.exception.category, "retry")
        self.assertNotIn("token", str(caught.exception))
        self.assertEqual(client.requests, 2)

    def test_delay_recovers_after_slow_error_without_shortening_reserved_slots(self):
        responses = iter([(0, robots()), (25, RemoteDisconnected("slow failure")),
                          *[(1, WireResponse()) for _ in range(4)]])
        client = self.client(delay=8)
        def timed_open(*args, **kwargs):
            duration, response = next(responses)
            self.clock.now += duration
            if isinstance(response, Exception):
                raise response
            return response
        client._opener.open = Mock(side_effect=timed_open)
        with self.assertRaises(http.FetchError):
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(client.delay, 25)
        delays = [client.delay]
        for _ in range(4):
            self.assertEqual(client.get("https://m.qidian.com/book/12/").status, 200)
            delays.append(client.delay)
        self.assertTrue(all(after < before for before, after in zip(delays, delays[1:])))
        self.assertAlmostEqual(delays[1], 16.5)
        self.assertTrue(all(delay >= 8 for delay in delays))
        for previous, following in zip(self.store.reservations, self.store.reservations[1:]):
            self.assertGreaterEqual(following[2], previous[2] + previous[1])

    def test_errors_never_reduce_delay_and_successes_respect_robots_floor(self):
        responses = iter([(0, robots(b"User-agent: *\nAllow: /\nCrawl-delay: 18.5\n")),
                          (25, RemoteDisconnected("slow failure")),
                          (1, RemoteDisconnected("fast failure")), (1, WireResponse(status=500)),
                          *[(1, WireResponse()) for _ in range(5)]])
        client = self.client(delay=10)
        def timed_open(*args, **kwargs):
            duration, response = next(responses)
            self.clock.now += duration
            if isinstance(response, Exception):
                raise response
            return response
        client._opener.open = Mock(side_effect=timed_open)
        for _ in range(3):
            before = client.delay
            with self.assertRaises(http.FetchError):
                client.get("https://m.qidian.com/book/12/")
            self.assertGreaterEqual(client.delay, before)
        self.assertEqual(client.delay, 25)
        for _ in range(5):
            client.get("https://m.qidian.com/book/12/")
            self.assertGreaterEqual(client.delay, 18.5)
        self.assertLess(client.delay, 25)
        self.assertTrue(all(delay >= 18.5 for _, delay, _ in self.store.reservations[1:]))

    def test_robots_missing_allows_but_unknown_html_stops(self):
        client = self.client(WireResponse(status=404), WireResponse())
        self.assertEqual(client.get("https://m.qidian.com/book/12/").status, 200)
        self.assertEqual(client.requests, 2)
        self.store = Store()
        client = self.client(WireResponse(b"<html>temporary information</html>"))
        with self.assertRaises(http.FetchError) as caught:
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(caught.exception.category, "blocked")
        self.assertEqual(client.requests, 1)

    def test_robots_restriction_and_decimal_delay(self):
        client = self.client(robots(b"User-agent: *\nDisallow: /book/\n"))
        with self.assertRaises(http.FetchError) as caught:
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(caught.exception.message, "robots_path_not_permitted")
        self.assertEqual(caught.exception.category, "invalid")
        self.assertEqual(self.store.state["blocked_until"], 0)
        self.store = Store()
        client = self.client(robots(b"User-agent: *\nAllow: /\nCrawl-delay: 12.5\n"), WireResponse(), WireResponse())
        client.get("https://m.qidian.com/book/12/")
        client.get("https://m.qidian.com/book/13/")
        self.assertGreaterEqual(self.store.reservations[1][2] - self.store.reservations[0][2], 12.5)
        self.assertGreaterEqual(self.store.reservations[-1][2] - self.store.reservations[-2][2], 12.5)

    def test_path_restriction_preserves_other_public_paths(self):
        client = self.client(robots(b"User-agent: *\nAllow: /\nDisallow: /webcommon/*\n"), WireResponse())
        blocked = "https://m.qidian.com/webcommon/category/list?catId=21&pageNum=1"
        allowed = "https://m.qidian.com/book/12/"
        self.assertFalse(client.can_fetch(blocked))
        self.assertTrue(client.can_fetch(allowed))
        self.assertEqual(client.requests, 1)
        with self.assertRaises(http.FetchError) as caught:
            client.get(blocked)
        self.assertEqual(caught.exception.message, "robots_path_not_permitted")
        self.assertEqual(caught.exception.category, "invalid")
        self.assertEqual(self.store.state["blocked_until"], 0)
        self.assertEqual(client.get(allowed).status, 200)
        targets = [call.args[0].full_url for call in client._opener.open.call_args_list]
        self.assertEqual(targets, ["https://m.qidian.com/robots.txt", allowed])

    def test_redirect_to_disallowed_path_does_not_block_platform(self):
        client = self.client(robots(b"User-agent: *\nAllow: /\nDisallow: /webcommon/*\n"),
                             WireResponse(status=302, Location="/webcommon/category/list?catId=21"),
                             WireResponse())
        with self.assertRaises(http.FetchError) as caught:
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(caught.exception.message, "robots_path_not_permitted")
        self.assertEqual(client.requests, 2)
        self.assertEqual(self.store.state["blocked_until"], 0)
        self.assertEqual(client.get("https://m.qidian.com/book/13/").status, 200)
        self.assertEqual(client.requests, 3)

    def test_can_fetch_validates_scope_and_obeys_existing_cooldown(self):
        client = self.client()
        with self.assertRaises(http.FetchError) as caught:
            client.can_fetch("https://m.qidian.com/chapter/12/34/")
        self.assertEqual(caught.exception.message, "url_outside_metadata_scope")
        self.store.block_platform("qidian", "challenge_page", 86400, now=self.clock.now)
        with self.assertRaises(http.FetchError) as caught:
            client.can_fetch("https://m.qidian.com/book/12/")
        self.assertEqual(caught.exception.category, "blocked")
        self.assertEqual(client.requests, 0)
        client._opener.open.assert_not_called()

    def test_denied_paths_still_obey_elapsed_time_budget(self):
        client = self.client(robots(b"User-agent: *\nDisallow: /book/\n"), max_seconds=10)
        url = "https://m.qidian.com/book/12/"
        self.assertFalse(client.can_fetch(url))
        self.clock.now += 11
        for method in (client.can_fetch, client.get):
            with self.subTest(method=method.__name__), self.assertRaises(http.BudgetExhausted):
                method(url)
        self.assertEqual(client.requests, 1)

    def test_denied_paths_still_obey_request_budget(self):
        client = self.client(robots(b"User-agent: *\nDisallow: /book/\n"), max_requests=1)
        url = "https://m.qidian.com/book/12/"
        self.assertFalse(client.can_fetch(url))
        for method in (client.can_fetch, client.get):
            with self.subTest(method=method.__name__), self.assertRaises(http.BudgetExhausted):
                method(url)
        self.assertEqual(client.requests, 1)

    def test_incompatible_robots_parser_stops_before_network(self):
        with patch.object(http, "RobotFileParser") as factory:
            factory.return_value.can_fetch.return_value = True
            with patch.object(http, "build_opener") as opener:
                with self.assertRaisesRegex(RuntimeError, "robots_parser_incompatible"):
                    http.Client("qidian", self.store)
                opener.assert_not_called()

    def test_request_budget_counts_robots(self):
        client = self.client(robots(), max_requests=1)
        with self.assertRaises(http.BudgetExhausted):
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(client.requests, 1)

    def test_time_budget_does_not_sleep_or_advance_persisted_slot(self):
        self.store.state["next_request_at"] = self.clock.now + 60
        client = self.client(max_seconds=10)
        with self.assertRaises(http.BudgetExhausted):
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(client.requests, 0)
        self.assertEqual(self.store.state["next_request_at"], 1060)
        self.assertEqual(self.clock.sleeps, [])

    def test_response_url_and_http_error_do_not_expose_csrf(self):
        url = "https://m.qidian.com/webcommon/category/list?catId=21&pageNum=1&gender=male&_csrfToken=secret"
        client = self.client(robots(), WireResponse(b'{"code":0}', content_type="application/json"))
        response = client.get(url)
        self.assertNotIn("csrf", response.url.lower())
        self.assertNotIn("secret", response.url)
        request = client._opener.open.call_args.args[0]
        self.assertEqual(request.get_header("X-requested-with"), "XMLHttpRequest")
        error = HTTPError(url, 403, "forbidden secret", {}, BytesIO(b"denied"))
        client._opener.open = Mock(side_effect=[error])
        with self.assertRaises(http.FetchError) as caught:
            client.get(url)
        self.assertEqual(str(caught.exception), "http_access_restriction")
        self.assertNotIn("secret", str(caught.exception))

    def test_errors_are_classified_and_counted(self):
        for status, category in ((500, "retry"), (404, "gone"), (410, "gone"), (202, "blocked"), (401, "blocked")):
            with self.subTest(status=status):
                self.store = Store()
                client = self.client(robots(), WireResponse(status=status))
                with self.assertRaises(http.FetchError) as caught:
                    client.get("https://m.qidian.com/book/12/")
                self.assertEqual(caught.exception.category, category)
                self.assertEqual(client.requests, 2)

    def test_prior_block_prevents_new_client_network(self):
        self.store.block_platform("qidian", "challenge_page", 86400, now=self.clock.now)
        client = self.client()
        with self.assertRaises(http.FetchError) as caught:
            client.get("https://m.qidian.com/book/12/")
        self.assertEqual(caught.exception.category, "blocked")
        self.assertEqual(client.requests, 0)
        self.assertEqual(self.store.reservations, [])

    def test_robots_temporary_errors_are_never_permission(self):
        for response, category in ((WireResponse(status=500), "retry"),
                                   (WireResponse(status=410), "retry"),
                                   (WireResponse(status=204), "blocked")):
            with self.subTest(category=category, status=response.status):
                self.store = Store()
                client = self.client(response)
                with self.assertRaises(http.FetchError) as caught:
                    client.get("https://m.qidian.com/book/12/")
                self.assertEqual(caught.exception.category, category)
                self.assertEqual(client.requests, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
