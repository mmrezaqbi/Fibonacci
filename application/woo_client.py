"""کلاینت ساده‌ی REST API ووکامرس (فقط کتابخانه‌ی استاندارد پایتون؛ نیازی به نصب requests نیست).

• سایت https: احراز هویت Basic با Consumer key/secret
• سایت http (مثلاً لوکال): امضای OAuth 1.0a، همان‌طور که ووکامرس برای غیر-SSL می‌خواهد
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class WooError(Exception):
    pass


def _q(value):
    return urllib.parse.quote(str(value), safe="~")


def oauth_signed_query(method, url, query, key, secret, *, nonce=None, timestamp=None):
    oauth = {
        "oauth_consumer_key": key,
        "oauth_nonce": nonce or uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(timestamp or int(time.time())),
    }
    params = {**{k: str(v) for k, v in query.items()}, **oauth}
    normalized = "&".join(f"{_q(k)}={_q(v)}" for k, v in sorted(params.items()))
    base = "&".join([method.upper(), _q(url), _q(normalized)])
    digest = hmac.new((_q(secret) + "&").encode(), base.encode(), hashlib.sha1).digest()
    oauth["oauth_signature"] = base64.b64encode(digest).decode()
    return {**query, **oauth}


class WooClient:
    def __init__(self, site_url, key, secret, timeout=20):
        self.base = site_url.rstrip("/") + "/wp-json/wc/v3/"
        self.key, self.secret, self.timeout = key, secret, timeout
        self.use_basic = self.base.startswith("https://")

    def request(self, method, path, params=None, data=None):
        url = self.base + path.lstrip("/")
        query = dict(params or {})
        headers = {"Accept": "application/json", "User-Agent": "Clothing-Warehouse/1.0"}
        if self.use_basic:
            token = base64.b64encode(f"{self.key}:{self.secret}".encode()).decode()
            headers["Authorization"] = "Basic " + token
        else:
            query = oauth_signed_query(method, url, query, self.key, self.secret)
        full = url + ("?" + urllib.parse.urlencode(query) if query else "")
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(full, data=body, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            message = ""
            try:
                message = json.loads(raw).get("message", "")
            except (ValueError, AttributeError):
                pass
            hint = " (کلیدهای API یا نوع احراز هویت را بررسی کنید)" if exc.code in (401, 403) else ""
            if exc.code == 404 and not message:
                hint = " (آدرس سایت یا پیوند یکتا (Permalinks) وردپرس را بررسی کنید)"
            raise WooError(f"خطای {exc.code}: {message or exc.reason}{hint}") from None
        except urllib.error.URLError as exc:
            raise WooError(f"اتصال به سایت برقرار نشد: {exc.reason}") from None
        except TimeoutError:
            raise WooError("پاسخ سایت دیر رسید (timeout).") from None
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            raise WooError("پاسخ سایت JSON معتبر نبود؛ آدرس سایت درست است و ووکامرس نصب است؟") from None

    def get(self, path, params=None):
        return self.request("GET", path, params)

    def post(self, path, data):
        return self.request("POST", path, data=data)

    def put(self, path, data):
        return self.request("PUT", path, data=data)
