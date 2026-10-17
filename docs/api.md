# Python API reference

Import `Mailbox` and `MailboxError` from `ridian_mailbox`.

## Client configuration

```python
client = Mailbox(base_url=origin, state=private_path, timeout=30)
```

`base_url` is an enabled HTTPS API origin without a path, credentials, query or
fragment. `state` is optional and accepts a string or `pathlib.Path`; its default
is documented in the [README](../README.md). `timeout` is a positive, finite
socket timeout in seconds. Methods return decoded API dictionaries unless noted.
No request is sent when constructing a client.

## Methods

| Method | Result and behavior |
| --- | --- |
| `setup()` | Create or recover an inbox with the saved setup credential; return mailbox metadata. |
| `status()` | Read the current mailbox's status, capabilities and limits. |
| `messages(cursor=None, limit=20)` | One page: `data` and `next_cursor`. Limit: 1–50. |
| `iter_messages(limit=20)` | Iterate through message summaries across pages. |
| `message(message_id)` | Read one message's content and metadata. |
| `attachment(attachment_id)` | Return authenticated attachment bytes. |
| `events(cursor=None, limit=20)` | Read one event page, using the saved cursor by default. Includes `next_cursor` and `poll_after_ms`. |
| `acknowledge_events(cursor)` | Save the next cursor locally, after processing its entire page. No HTTP request. |
| `webhook()` | Read the current webhook subscription. |
| `set_webhook(url=..., signing_secret=...)` | Configure the HTTPS receiver and signing secret. |
| `resume_webhook()` | Resume the current webhook subscription. |
| `delete_webhook()` | Remove the current webhook subscription. |
| `revoke()` | Permanently revoke the current access, including copies. Mailbox data remains. |

Pagination cursors are opaque: pass them unchanged. Message and attachment IDs
are URL-encoded. Do not treat the API's mailbox capabilities as a promise of
permission through another access channel.

## Webhooks

Provide an HTTPS receiver reachable by Ridian and a signing secret matching your
environment's API contract. Store that secret privately. Verify signatures at your
receiver before processing deliveries, and deduplicate events by ID. A webhook
subscription alone does not execute an agent. The SDK configures subscriptions;
it does not host a receiver or implement delivery signature verification.

## Error handling

```python
from ridian_mailbox import MailboxError

try:
    page = client.messages()
except MailboxError as error:
    if error.status == 429:
        schedule_retry_after(error.retry_after)  # Your application's scheduler.
    else:
        raise
```

`MailboxError` exposes `code`, optional HTTP `status`, and optional `retry_after`
in seconds. Error messages omit request credentials and upstream response bodies.
Local configuration or state-file errors may raise `ValueError` or `OSError`.
The CLI prints a short error and exits nonzero.

The SDK never retries network calls automatically. After 429, requests on the same
client instance fail locally until its cooldown ends. A new process must still
respect the server's retry interval. For interrupted setup, reuse the saved state;
do not generate another identity. Request user authorization before irreversible
operations such as revoking access.

## Storage contract

SDK and CLI share a JSON state file bound to one API origin. The setup credential
is saved before the first HTTP call. Subsequent writes use an owner-only temporary
file and atomic replacement. Reads reject symlinks and group/world permissions.
Use a durable private directory, one writer per file, and secure backups.

The default filename includes the host and optional port. Override `state` when
an agent needs a separate inbox at the same origin. Do not edit stored credentials
to switch environments. This package does not encrypt the file; its confidentiality
depends on operating-system permissions and your storage environment.
