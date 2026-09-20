"""Bounded public metadata HTTP access with persistent platform pacing.

The caller owns the task queue. This module never retries in place, follows a
chapter URL, stores cookies on disk, or calculates request/response digests.
"""
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from http.cookiejar import CookieJar
import math
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from collect_qidian_catalog import UA as QIDIAN_UA


HOSTS = {"qidian": "m.qidian.com", "jjwxc": "www.jjwxc.net"}
RESEARCH_AGENT = "WebnovelBibliographyResearch"
JJWXC_UA = RESEARCH_AGENT + "/0.5 (+https://github.com/huwenbo-lab/research_harness)"
MAX_BYTES = 25 * 1024 * 1024
SENSITIVE_QUERY = re.compile(r"csrf|token|cookie|authorization|session|password|secret", re.I)


class FetchError(Exception):
    def __init__(self, category, message, retry_after=0, http_status=None):
        if category not in {"retry", "blocked", "gone", "invalid"}:
            raise ValueError("unknown_fetch_error_category")
        self.category = category
        # Only controlled machine-readable reasons may enter logs or the queue.
        self.message = message if re.fullmatch(r"[a-z0-9_]{1,100}", str(message)) else "request_failed"
        value = float(retry_after or 0)
        self.retry_after = max(0.0, value) if math.isfinite(value) else 0.0
        self.http_status = http_status
        super().__init__(self.message)


class BudgetExhausted(Exception):
    pass


@dataclass(frozen=True)
class Response:
    body: bytes
    status: int
    content_type: str
    url: str


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Redirects are followed explicitly so each HTTP attempt is accounted for.
        return None


def safe_url(url):
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not SENSITIVE_QUERY.search(key)]
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, urlencode(query), ""))


def validate_url(platform, url):
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.hostname != HOSTS[platform]
                or parts.port not in (None, 443) or parts.username or parts.password
                or parts.fragment or "%" in parts.path or "\\" in url):
            raise ValueError
        query = parse_qs(parts.query, keep_blank_values=True)
        if any(key.lower() in {"chapterid", "chapter_id", "cid"} for key in query):
            raise ValueError
        if parts.path == "/robots.txt":
            if query:
                raise ValueError
            return url
        if platform == "qidian":
            if re.fullmatch(r"/category/(?:male|female|catid[0-9]+)/?", parts.path):
                if query:
                    raise ValueError
            elif parts.path == "/webcommon/category/list":
                allowed = {"catId", "pageNum", "gender", "size", "isfinish", "_csrfToken"}
                if not set(query).issubset(allowed):
                    raise ValueError
            elif re.fullmatch(r"/book/[0-9]+/(?:catalog/)?", parts.path):
                if query:
                    raise ValueError
            else:
                raise ValueError
        elif parts.path == "/onebook.php":
            if set(query) != {"novelid"} or len(query["novelid"]) != 1 or not re.fullmatch(r"[0-9]+", query["novelid"][0]):
                raise ValueError
        elif parts.path != "/bookbase.php":
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise FetchError("invalid", "url_outside_metadata_scope") from None
    return url


def _challenge(body, content_type):
    prefix = body.lstrip()[:200].lower()
    if "html" not in content_type.lower() and not prefix.startswith((b"<!doctype", b"<html", b"<script")):
        return False
    soup = BeautifulSoup(body, "html.parser")
    # Detect explicit challenge scripts, not the English word in novel metadata.
    for node in soup.find_all("script"):
        script = (str(node.get("src", "")) + " " + node.get_text()).lower()
        if any(marker in script for marker in ("cf-chl-", "/cdn-cgi/challenge-platform/", "probe.js", "waf_captcha")):
            return True
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    visible = soup.get_text(" ", strip=True)
    if re.search(r"请\s*(?:登入|登录)\s*后再访问|请完成验证|请输入验证码|访问过于频繁|安全验证|请求异常.{0,20}验证", visible):
        return True
    return "验证码" in visible and len(visible) < 1200


def _retry_after(headers, now):
    raw = str(headers.get("Retry-After", "")).strip()
    try:
        value = float(raw)
        if math.isfinite(value):
            return max(0.0, value)
    except ValueError:
        pass
    try:
        date = parsedate_to_datetime(raw)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0.0, date.timestamp() - now)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _validate_robots_runtime():
    """Older stdlib parsers may silently ignore wildcard/longest-match rules."""
    parser = RobotFileParser("https://m.qidian.com/robots.txt")
    parser.parse(["User-agent: *", "Allow: /", "Disallow: /webcommon/*"])
    if (parser.can_fetch(RESEARCH_AGENT, "https://m.qidian.com/webcommon/category/list")
            or not parser.can_fetch(RESEARCH_AGENT, "https://m.qidian.com/book/1/")):
        raise RuntimeError("robots_parser_incompatible: use a current Python 3.14 patch release or newer")


class Client:
    def __init__(self, platform, store, max_requests=200, max_seconds=1200, delay=6, timeout=25):
        if platform not in HOSTS:
            raise ValueError("unknown_platform")
        if (max_requests < 0 or not all(math.isfinite(float(v)) for v in (max_seconds, delay, timeout))
                or max_seconds <= 0 or delay < 0 or timeout <= 0):
            raise ValueError("invalid_http_budget")
        _validate_robots_runtime()
        self.platform = platform
        self.store = store
        self.max_requests = int(max_requests)
        self.max_seconds = float(max_seconds)
        self._minimum_delay = max(6.0, float(delay))
        self.delay = self._minimum_delay
        self.timeout = float(timeout)
        self.requests = 0
        self.bytes = 0
        self._started = time.monotonic()
        self._deadline = self._started + self.max_seconds
        self._cookies = CookieJar()
        self._opener = build_opener(_NoRedirect(), HTTPCookieProcessor(self._cookies))
        self._robots_checked = False
        self._robots = None
        self._robots_response = None
        self._last_request_started = None

    def get_csrf(self):
        return next((cookie.value for cookie in self._cookies if cookie.name == "_csrfToken"
                     and (cookie.domain.lstrip(".") in {"qidian.com", HOSTS[self.platform]})), "")

    def _remaining(self):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise BudgetExhausted("time_budget_exhausted")
        return remaining

    def _check_budget(self):
        if self.requests >= self.max_requests:
            raise BudgetExhausted("request_budget_exhausted")
        return self._remaining()

    def _check_platform(self):
        state = self.store.platform_status(self.platform)
        remaining = max(0.0, float(state.get("blocked_until") or 0) - time.time())
        if remaining:
            raise FetchError("blocked", "platform_cooling_down", remaining)
        return state

    def _before_request(self):
        state = self._check_platform()
        remaining = self._check_budget()
        now = time.time()
        next_allowed = float(state.get("next_request_at") or 0)
        if self._last_request_started is not None:
            next_allowed = max(next_allowed, self._last_request_started + self.delay)
        if max(0.0, next_allowed - now) >= remaining:
            raise BudgetExhausted("pacing_exceeds_time_budget")
        # Newly learned robots delays also apply to the very next request. Wait
        # before reserving so the durable slot is based on its actual start.
        self._sleep(max(0.0, next_allowed - now))
        wait = self.store.reserve_request(self.platform, self.delay, now=time.time())
        if wait >= self._remaining():
            raise BudgetExhausted("pacing_exceeds_time_budget")
        self._sleep(max(0.0, wait))
        self._check_platform()
        self._remaining()
        self._last_request_started = time.time()
        self.requests += 1

    def _sleep(self, wait):
        until = time.monotonic() + max(0.0, wait)
        while time.monotonic() < until:
            time.sleep(min(1.0, until - time.monotonic(), self._remaining()))

    def _blocked(self, reason, seconds, status=None):
        self.store.block_platform(self.platform, reason, seconds, now=time.time())
        raise FetchError("blocked", reason, seconds, http_status=status)

    def _open_once(self, url, accept, referer):
        self._before_request()
        headers = {"User-Agent": (QIDIAN_UA + " " + JJWXC_UA) if self.platform == "qidian" else JJWXC_UA,
                   "Accept": accept, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"}
        if self.platform == "qidian" and urlsplit(url).path == "/webcommon/category/list":
            headers["X-Requested-With"] = "XMLHttpRequest"
        if referer:
            headers["Referer"] = safe_url(validate_url(self.platform, referer))
        request = Request(url, headers=headers)
        started = time.monotonic()
        response = None
        successful = False
        try:
            try:
                response = self._opener.open(request, timeout=min(self.timeout, self._remaining()))
            except HTTPError as error:
                response = error
            status = response.status
            response_headers = response.headers
            content_type = response_headers.get("Content-Type", "")
            if status != 200:
                return Response(b"", status, content_type, safe_url(url)), response_headers
            chunks, received = [], 0
            while True:
                self._remaining()
                chunk = response.read(min(65536, MAX_BYTES + 1 - received))
                self.bytes += len(chunk)
                received += len(chunk)
                if received > MAX_BYTES:
                    raise FetchError("invalid", "response_size_limit")
                if not chunk:
                    break
                chunks.append(chunk)
            self._remaining()
            successful = True
            return Response(b"".join(chunks), status, content_type, safe_url(url)), response_headers
        except (URLError, HTTPException, TimeoutError, OSError):
            raise FetchError("retry", "network_error", retry_after=60) from None
        finally:
            if response is not None:
                response.close()
            target = max(self._minimum_delay, time.monotonic() - started)
            # A temporary error can slow collection, but cannot speed it up.
            # Complete 200 responses let the delay recover gradually while the
            # durable reservation still protects the already scheduled next slot.
            self.delay = (self.delay + target) / 2 if successful else max(self.delay, target)

    def _fetch(self, url, accept="text/html", referer=None, checking_robots=False):
        current, seen = url, set()
        for _ in range(4):
            validate_url(self.platform, current)
            self._check_budget()
            if current in seen:
                raise FetchError("invalid", "redirect_loop")
            seen.add(current)
            if not checking_robots and self._robots is not None and not self._robots.can_fetch(RESEARCH_AGENT, current):
                # A path policy is not evidence that other public metadata on
                # this platform is blocked. Do not send the disallowed request.
                raise FetchError("invalid", "robots_path_not_permitted")
            response, headers = self._open_once(current, accept, referer)
            if response.status in {202, 401, 403}:
                self._blocked("http_access_restriction", 86400, response.status)
            if response.status == 429:
                self._blocked("http_rate_limited", max(3600, _retry_after(headers, time.time())), 429)
            if 500 <= response.status <= 599:
                raise FetchError("retry", "http_server_error", max(60, _retry_after(headers, time.time())), response.status)
            if response.status in {404, 410}:
                raise FetchError("gone", "http_" + str(response.status), http_status=response.status)
            if response.status in {301, 302, 303, 307, 308}:
                location = headers.get("Location")
                if not location:
                    raise FetchError("invalid", "redirect_location_missing")
                target = urljoin(current, location)
                validate_url(self.platform, target)
                if checking_robots and urlsplit(target).path != "/robots.txt":
                    self._blocked("robots_redirect_invalid", 86400)
                current = target
                continue
            if response.status != 200:
                raise FetchError("invalid", "unexpected_http_status", http_status=response.status)
            if _challenge(response.body, response.content_type):
                self._blocked("challenge_page", 86400, response.status)
            return response
        raise FetchError("invalid", "redirect_limit")

    def _ensure_robots(self):
        if self._robots_checked:
            return
        url = "https://" + HOSTS[self.platform] + "/robots.txt"
        try:
            response = self._fetch(url, accept="text/plain", checking_robots=True)
        except FetchError as error:
            if error.http_status == 404:
                self._robots_checked = True
                return
            if error.category == "gone":
                raise FetchError("retry", "robots_unavailable", 60) from None
            if error.category == "invalid":
                self._blocked("robots_unavailable", 86400, error.http_status)
            raise
        text = response.body.decode("utf-8-sig", "replace")
        lines = [line.split("#", 1)[0].strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        known = {"user-agent", "allow", "disallow", "crawl-delay", "sitemap", "request-rate", "host"}
        directives = []
        for line in lines:
            key, separator, value = line.partition(":")
            if not separator or key.strip().lower() not in known:
                self._blocked("robots_unrecognized_response", 86400)
            directives.append((key.strip().lower(), value.strip()))
        if "html" in response.content_type.lower() or not any(key == "user-agent" and value for key, value in directives):
            self._blocked("robots_unrecognized_response", 86400)
        parser = RobotFileParser(url)
        parser.parse(text.splitlines())
        # Applying the longest advertised delay is conservative and also handles
        # fractional crawl-delay values ignored by RobotFileParser.
        delays = []
        for key, value in directives:
            if key == "crawl-delay":
                try:
                    delay = float(value)
                    if not math.isfinite(delay) or delay < 0:
                        raise ValueError
                    delays.append(delay)
                except ValueError:
                    self._blocked("robots_invalid_crawl_delay", 86400)
        self._minimum_delay = max([self._minimum_delay, *delays])
        self.delay = max(self.delay, self._minimum_delay)
        self._robots = parser
        self._robots_response = response
        self._robots_checked = True

    def can_fetch(self, url):
        """Check public-path permission, fetching only robots.txt if necessary."""
        validate_url(self.platform, url)
        self._check_platform()
        self._check_budget()
        self._ensure_robots()
        return self._robots is None or self._robots.can_fetch(RESEARCH_AGENT, url)

    def get(self, url, accept="text/html", referer=None):
        validate_url(self.platform, url)
        if referer:
            validate_url(self.platform, referer)
        self._check_platform()
        # Denied paths do not make wire requests, but still obey the total time
        # budget so a queue of denied paths cannot run indefinitely.
        self._check_budget()
        self._ensure_robots()
        if urlsplit(url).path == "/robots.txt":
            if self._robots_response is None:
                raise FetchError("gone", "http_404", http_status=404)
            return self._robots_response
        return self._fetch(url, accept=accept, referer=referer)

    def summary(self):
        return {"platform": self.platform, "requests": self.requests, "bytes": self.bytes,
                "elapsed_seconds": round(time.monotonic() - self._started, 3), "delay_seconds": self.delay}

    def close(self):
        self._cookies.clear()
