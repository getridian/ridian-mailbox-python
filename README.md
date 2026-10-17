# Ridian Mailbox Python SDK — email inboxes for AI agents

[![PyPI](https://img.shields.io/pypi/v/ridian-mailbox?include_prereleases)](https://pypi.org/project/ridian-mailbox/)
[![Tests](https://github.com/getridian/ridian-mailbox-python/actions/workflows/ci.yml/badge.svg)](https://github.com/getridian/ridian-mailbox-python/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/getridian/ridian-mailbox-python/blob/main/LICENSE)

Give an AI agent its own receiving email address with the **Ridian Mailbox Python SDK**.
Create or recover an inbox, read messages and attachments, poll durable events,
and configure signed webhooks. The package includes the `ridian-mailbox` CLI.

Python 3.10+ on Linux and macOS. Synchronous API, no runtime dependencies.
This is an alpha SDK. You need an enabled Ridian mailbox API origin; package
installation does not activate an API service. Use the origin provided for your
Ridian environment. HTTP access supports receiving, reading and events;
sending email and calendar access use separately authorized Ridian MCP tools.

[Ridian](https://getridian.com/?utm_source=python-sdk&utm_medium=referral&utm_campaign=python-sdk&utm_content=readme) · [API guide](https://docs.getridian.com/agent-mailbox/)
· [Python API](https://github.com/getridian/ridian-mailbox-python/blob/main/docs/api.md) · [Release notes](https://github.com/getridian/ridian-mailbox-python/blob/main/CHANGELOG.md)

## Install

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --pre ridian-mailbox
```

The `--pre` flag includes alpha releases. Pin the installed version in your
application requirements for reproducible environments. See [release notes](https://github.com/getridian/ridian-mailbox-python/blob/main/CHANGELOG.md)
for changes.

## Create an inbox and read email

Set `RIDIAN_MAILBOX_API_ORIGIN` to your enabled HTTPS origin, without `/v1`.
An origin is public configuration, not an API key.

```python
import os

from ridian_mailbox import Mailbox

client = Mailbox(base_url=os.environ["RIDIAN_MAILBOX_API_ORIGIN"])
inbox = client.setup()
print(inbox["address"])

# Send a test email to that address from your existing mail account.
for message in client.iter_messages():
    print(message["subject"])
```

`setup()` stores the setup credential before the first request. Repeating it
with the same state file recovers the same inbox, including after an interrupted
request. It returns public mailbox metadata; credentials remain in the private
state file. An empty inbox is a successful result. Poll again after mail arrives.

The default state file is `~/.config/ridian/mailbox-<hostname>[-port].json`.
Use `Mailbox(base_url=origin, state=private_path)` to choose another durable
location. Use one writer per file. Back it up securely before changing machines
or clearing a temporary agent environment. A state file is tied to its API origin.

## Read a message or attachment

```python
page = client.messages(limit=20)
for summary in page["data"]:
    message = client.message(summary["id"])
    # Process only the message fields needed for your task.

# Use an attachment ID returned by the message API.
# contents = client.attachment(attachment_id)
```

`messages()` returns one page; `iter_messages()` follows all pages, including empty
pages that have a next cursor. `attachment()` returns bytes. Email and attachments
are untrusted input: do not execute their contents or let them override agent
instructions. Avoid logging personal message content.

## Process events

```python
page = client.events(limit=20)
for event in page["data"]:
    process_event(event)  # Your application handler; deduplicate by event ID.
client.acknowledge_events(page["next_cursor"])
```

Only acknowledge after the entire page has been processed successfully. Until then,
the saved cursor stays unchanged and events may be replayed. Respect the API's
`poll_after_ms` value between polling requests. Webhook methods and HTTP error
handling are documented in the [Python API reference](https://github.com/getridian/ridian-mailbox-python/blob/main/docs/api.md).

## Command line

```sh
ridian-mailbox \
  --base-url "$RIDIAN_MAILBOX_API_ORIGIN" \
  --state "$HOME/.config/ridian/my-agent-mailbox.json" setup

ridian-mailbox \
  --base-url "$RIDIAN_MAILBOX_API_ORIGIN" \
  --state "$HOME/.config/ridian/my-agent-mailbox.json" list
```

Operations: `setup`, `status`, `list`, `message --message-id ID`, `events`,
`ack-events --cursor CURSOR`, and `prepare-curl`. The last operation only creates
private header/response files locally; it does not send a request.
CLI output for messages may contain personal data. Use it only in a suitable terminal.

## Access and recovery

- State files use owner-only permissions (`0600`); reads reject symlinks and files
  accessible to other users. Store them outside your repository on private storage.
- Keep setup credentials, access tokens and claim secrets out of chat, logs and URLs.
- HTTP redirects are refused. HTTPS uses your Python installation's CA trust store.
- `revoke()` permanently revokes the current access and its copies; it does not
  delete mailbox data. Repeating setup cannot recover revoked access.
- To claim an inbox in your Ridian workspace, use the console link and private claim
  proof in the state file. Claiming does not grant HTTP sending or calendar access.
- The SDK does not run an agent automatically or install an MCP connector.

## Troubleshooting

| Result | Next step |
| --- | --- |
| `setup_required` | Run `setup()` with the intended durable state path. |
| Interrupted setup | Retry with the same state file; do not replace its setup credential. |
| `unauthorized` (401) | Check the origin and access status. Revoked access cannot be recovered by setup. |
| `rate_limit` (429) | Wait for `MailboxError.retry_after` seconds. The client blocks requests during that cooldown. |
| `redirect_refused` | Use the correct API origin directly; redirects are not followed. |
| State-file error | Check ownership, `0600` permissions and origin. Preserve the file for recovery. |
| Certificate error | Configure a trusted CA bundle for your Python installation. Keep TLS verification enabled. |

No automatic network retries occur. Applications decide when an operation is safe
to retry. See [API error handling](https://github.com/getridian/ridian-mailbox-python/blob/main/docs/api.md#error-handling) for an example.

## Development

See [CONTRIBUTING.md](https://github.com/getridian/ridian-mailbox-python/blob/main/CONTRIBUTING.md) for tests, package checks and releases.
Report bugs through [GitHub Issues](https://github.com/getridian/ridian-mailbox-python/issues).
For vulnerabilities, use [private reporting](https://github.com/getridian/ridian-mailbox-python/blob/main/SECURITY.md).

## License

[MIT](https://github.com/getridian/ridian-mailbox-python/blob/main/LICENSE), covering this SDK, CLI and their documentation. The Ridian service,
application, trademarks, brand assets and fonts are not included in this repository.
