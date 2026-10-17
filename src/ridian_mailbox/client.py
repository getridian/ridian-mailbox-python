"""Dependency-free, synchronous HTTP client with private durable setup state."""

import json
import math
import re
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ._state import load_or_create_state, save_state


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class MailboxError(Exception):
    """Contains status/retry metadata, never credentials or arbitrary response bodies."""

    def __init__(
        self, code: str, status: int | None = None, retry_after: int | None = None
    ) -> None:
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(
            f"Mailbox request failed: {code}" + (f" (HTTP {status})" if status else "")
        )


class Mailbox:
    """A receiving mailbox with credentials persisted to private local storage."""

    def __init__(
        self, *, base_url: str, state: str | Path | None = None, timeout: float = 30
    ) -> None:
        url = urlsplit(base_url.rstrip("/"))
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
        ):
            raise ValueError("Use a fixed HTTPS origin, without path or credentials.")
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        default_name = "mailbox-" + url.hostname + (f"-{url.port}" if url.port else "") + ".json"
        self.base_url, self.state_path, self.timeout = (
            url.geturl(),
            (
                Path(state).expanduser()
                if state is not None
                else Path.home() / ".config/ridian" / default_name
            ),
            timeout,
        )
        self._blocked_until = 0
        self._transport = build_opener(NoRedirect())

    def __repr__(self):
        return "Mailbox(<private state>)"

    def _state(self, create=False):
        if not create and not self.state_path.exists():
            raise MailboxError("setup_required")
        return load_or_create_state(self.state_path, self.base_url)

    def _request(self, path, *, method="GET", token=None, body=None, binary=False):
        if time.monotonic() < self._blocked_until:
            raise MailboxError(
                "rate_limit", 429, max(1, int(self._blocked_until - time.monotonic()) + 1)
            )
        if token is None:
            token = self._state().get("access_token")
            if not token:
                raise MailboxError("repeat_setup_with_saved_state")
        if not isinstance(token, str) or not re.fullmatch(
            r"ridian_(?:setup|mailbox)_[a-f0-9]{64}", token
        ):
            raise MailboxError("invalid_saved_credential")
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "ridian-mailbox-python/" + version("ridian-mailbox"),
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(
            self.base_url + "/v1/mailboxes" + path,
            method=method,
            headers=headers,
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            with self._transport.open(req, timeout=self.timeout) as response:
                if binary:
                    return response.read()
                if response.status == 204:
                    return None
                return json.load(response)
        except HTTPError as error:
            error.close()
            wait = None
            if error.code == 429:
                value = error.headers.get("Retry-After", "60")
                try:
                    wait = max(1, int(value))
                except ValueError:
                    try:
                        wait = max(
                            1,
                            int(
                                (
                                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                                ).total_seconds()
                            ),
                        )
                    except (ValueError, TypeError, OverflowError):
                        wait = 60
                self._blocked_until = time.monotonic() + wait
            codes = {
                401: "unauthorized",
                403: "forbidden",
                404: "not_found",
                409: "conflict",
                429: "rate_limit",
                503: "unavailable",
            }
            raise MailboxError(
                "redirect_refused"
                if 300 <= error.code < 400
                else codes.get(error.code, "http_error"),
                error.code,
                wait,
            ) from None
        except (URLError, TimeoutError, OSError):
            raise MailboxError("transport_interrupted_reuse_state") from None
        except (ValueError, UnicodeDecodeError):
            raise MailboxError("invalid_response") from None

    def setup(self) -> dict[str, Any]:
        """Create/recover the same mailbox; only return public mailbox metadata."""
        state = self._state(create=True)
        result = self._request("", method="POST", token=state["setup_token"], body={})
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("mailbox"), dict)
            or not all(
                isinstance(result.get(k), str)
                for k in ("access_token", "claim_secret", "claim_url")
            )
        ):
            raise MailboxError("invalid_response_repeat_setup")
        if not re.fullmatch(r"ridian_mailbox_[a-f0-9]{64}", result["access_token"]):
            raise MailboxError("invalid_response_repeat_setup")
        if not re.fullmatch(r"[a-f0-9]{64}", result["claim_secret"]):
            raise MailboxError("invalid_response_repeat_setup")
        for key in ("mailbox", "access_token", "claim_secret", "claim_url"):
            state[key] = result[key]
        save_state(self.state_path, state)
        return result["mailbox"]

    def status(self) -> dict[str, Any]:
        return self._request("/current")

    @staticmethod
    def _page(cursor, limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        return "?" + urlencode(
            {"limit": limit, **({"cursor": cursor} if cursor is not None else {})}
        )

    def messages(self, *, cursor: str | None = None, limit: int = 20) -> dict[str, Any]:
        return self._request("/current/messages" + self._page(cursor, limit))

    def iter_messages(self, *, limit: int = 20) -> Iterator[dict[str, Any]]:
        cursor = None
        seen = set()
        while True:
            page = self.messages(cursor=cursor, limit=limit)
            if (
                not isinstance(page, dict)
                or not isinstance(page.get("data"), list)
                or "next_cursor" not in page
                or not all(isinstance(item, dict) for item in page["data"])
            ):
                raise MailboxError("invalid_response")
            following = page["next_cursor"]
            if following is not None and (
                not isinstance(following, str) or not following or following in seen
            ):
                raise MailboxError("invalid_pagination_cursor")
            if following is not None:
                seen.add(following)
            yield from page["data"]
            cursor = following
            if cursor is None:
                return

    def message(self, message_id: str) -> dict[str, Any]:
        return self._request("/current/messages/" + quote(str(message_id), safe=""))

    def attachment(self, attachment_id: str) -> bytes:
        """Return authenticated bytes. Call only where this content may be held."""
        return self._request(
            "/current/attachments/" + quote(str(attachment_id), safe=""), binary=True
        )

    def events(self, *, cursor: str | None = None, limit: int = 20) -> dict[str, Any]:
        if cursor is None:
            cursor = self._state().get("event_cursor")
        return self._request("/current/events" + self._page(cursor, limit))

    def acknowledge_events(self, cursor: str) -> None:
        """Persist only after processing the complete page; deduplicate event IDs."""
        if not isinstance(cursor, str) or not cursor or len(cursor) > 4096:
            raise ValueError("Use next_cursor from a fully processed events page")
        state = self._state()
        state["event_cursor"] = cursor
        save_state(self.state_path, state)

    def webhook(self) -> dict[str, Any]:
        return self._request("/current/webhook")

    def set_webhook(self, *, url: str, signing_secret: str) -> dict[str, Any]:
        return self._request(
            "/current/webhook", method="POST", body={"url": url, "signing_secret": signing_secret}
        )

    def resume_webhook(self) -> dict[str, Any]:
        return self._request("/current/webhook/resume", method="POST", body={})

    def delete_webhook(self) -> None:
        return self._request("/current/webhook", method="DELETE")

    def revoke(self) -> None:
        """Permanently revoke this credential and its copies; preserve mailbox data."""
        return self._request("/current/access", method="DELETE")
