# openclaw-email-triage-v1-plugin

Out-of-tree OpenClaw plugin for upgrade-safe email triage integration with the v1 inference service.

## Goals

- No changes to OpenClaw core repo.
- Plugin-managed command: `email.triage.v1`.
- Strict OpenClaw version compatibility gate.
- Shadow/canary/full rollout controls via config and env.
- Fail-open behavior to keep inbox safe.
- Explicit backup/restore scripts for rollback.

## Install (example)

```bash
pip install openclaw-email-triage-v1-plugin
openclaw plugins install openclaw-email-triage-v1-plugin
```

Or load by path/package through existing OpenClaw plugin configuration.

## Plugin Config Example

```toml
[plugins.entries.email_triage_v1]
enabled = true
package = "openclaw-email-triage-v1-plugin"

[plugins.entries.email_triage_v1.config]
inference_base_url = "https://triage.internal"
inference_timeout_ms = 1500
inference_retries = 2
inference_backoff_ms = 200
model_version = "v1"
archive_confidence_threshold = 0.995
supported_openclaw_versions = ">=1.8.0,<2.0.0"
shadow_mode = true
canary_percent = 0
telemetry_jsonl_path = "/var/log/openclaw/email-triage-decisions.jsonl"
idempotency_sqlite_path = "/var/lib/openclaw/email-triage-idempotency.sqlite3"
```

Use env for secrets and runtime flags:

```bash
export OPENCLAW_TRIAGE_API_KEY="..."
export EMAIL_TRIAGE_ENGINE="v1"
export EMAIL_TRIAGE_ARCHIVE_ENABLED="true"
export EMAIL_TRIAGE_FAIL_OPEN="true"
export EMAIL_TRIAGE_BLOCKLIST_ENABLED="true"
export EMAIL_TRIAGE_LEGACY_RULES_ENABLED="false"
```

## Backup and Restore

Create a rollback snapshot before rollout:

```bash
python scripts/backup_openclaw_runtime.py \
  --path /etc/openclaw/config.toml \
  --path /etc/openclaw/plugins.toml \
  --path /etc/openclaw/rules.yaml \
  --path /etc/openclaw/runtime.env \
  --path /var/lib/openclaw \
  --output-dir /var/backups/openclaw-triage
```

Dry-run restore:

```bash
python scripts/restore_openclaw_runtime.py \
  --snapshot-dir /var/backups/openclaw-triage/openclaw-runtime-backup-YYYYMMDDTHHMMSSZ \
  --target-root /
```

Apply restore:

```bash
python scripts/restore_openclaw_runtime.py \
  --snapshot-dir /var/backups/openclaw-triage/openclaw-runtime-backup-YYYYMMDDTHHMMSSZ \
  --target-root / \
  --apply \
  --write-env-file /etc/openclaw/restore-triage-env.sh
```

## Command Contract

### Input

`email.triage.v1` expects a dict matching `EmailTriageRequest` fields:

- `request_id`, `message_id`, `thread_id`, `sender`, `to`, `subject`, `date`, `body_text`,
- optional: `body_html`, `gmail_labels`, `gmail_category`, `in_reply_to`, `references`, `sent_message_ids`, `is_starred`, `is_read`.

### Output

Returns dict with:

- `action_status` (`archived|kept_in_inbox|shadow_kept|archive_disabled_kept|action_failed|duplicate_skipped`)
- `decision`, `confidence`, `source`, `rule`, `reasoning`, `model_version`, `threshold_used`, `latency_ms`

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## Compatibility Policy

Plugin startup blocks if OpenClaw version is outside configured range (`supported_openclaw_versions`).

Default range: `>=1.8.0,<2.0.0`.
