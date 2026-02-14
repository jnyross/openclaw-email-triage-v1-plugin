# OpenClaw v1 Plugin Rollout Runbook (No-Fork)

## Scope

- OpenClaw core repo remains unchanged.
- Deploy via out-of-tree plugin + runtime configuration only.

## Phase 0: Preflight

1. Install plugin package in non-prod OpenClaw runtime.
2. Validate compatibility and inference service health:

```bash
python scripts/preflight_check.py \
  --openclaw-version "1.8.2" \
  --supported-spec ">=1.8.0,<2.0.0" \
  --inference-base-url "https://triage.internal"
```

3. Configure plugin in shadow mode (`deploy/openclaw/shadow.toml`).
4. Validate command invocation from existing email rule config.

## Phase 1: Shadow

1. Keep legacy rules active.
2. `shadow_mode=true`, `canary_percent=0`.
3. Verify metrics:
- zero archive actions for blocklist-positive emails
- no plugin invocation failures
- p95 inference latency <= 1200ms

## Phase 2: Canary

1. Disable legacy rules for canary slice.
2. Start with `deploy/openclaw/canary.toml` (`canary_percent=5`).
3. Increase to 25 after 24h if healthy.
4. Evaluate rollback:

```bash
python scripts/evaluate_rollback.py \
  --decisions /var/log/openclaw/email-triage-decisions.jsonl \
  --corrections /var/log/openclaw/email-triage-corrections.jsonl \
  --rollback-threshold 0.002 \
  --write-env /etc/openclaw/email-triage-rollback.env
```

If `rollback_triggered=true`, apply env overrides and reload runtime config.

## Phase 3: Full

1. Apply `deploy/openclaw/full.toml` (`canary_percent=100`).
2. Keep rollback monitor running.
3. Stabilize for 7 consecutive days with FP rate <= 0.1%.

## Runtime Flags

- `EMAIL_TRIAGE_ENGINE=v1`
- `EMAIL_TRIAGE_ARCHIVE_ENABLED=true|false`
- `EMAIL_TRIAGE_FAIL_OPEN=true`
- `EMAIL_TRIAGE_BLOCKLIST_ENABLED=true`
- `EMAIL_TRIAGE_LEGACY_RULES_ENABLED=false` (post-shadow)
