#!/usr/bin/env bash
# Keep exactly one open issue per outage: open on down, close on recovery.
set -euo pipefail

LABEL="site-down"

gh label create "$LABEL" --color B60205 --description "Monitored site is unreachable" 2>/dev/null || true

open_issue=$(gh issue list --label "$LABEL" --state open --limit 1 --json number --jq '.[0].number // empty')

if [ "$UP" = "false" ]; then
  if [ -n "$open_issue" ]; then
    gh issue comment "$open_issue" --body "Still down: ${DETAIL}

Checked at $(date -u '+%Y-%m-%d %H:%M UTC') · [workflow run](${RUN_URL})"
    echo "Commented on existing issue #${open_issue}"
  else
    gh issue create \
      --title "${SITE} is DOWN" \
      --label "$LABEL" \
      --body "${SITE} failed ${ATTEMPTS:-3} consecutive checks.

**Error:** ${DETAIL}
**Detected:** $(date -u '+%Y-%m-%d %H:%M UTC')
**Run:** ${RUN_URL}

This issue closes automatically when the site responds again."
    echo "Opened a new outage issue"
  fi
  exit 0
fi

if [ -n "$open_issue" ]; then
  gh issue comment "$open_issue" --body "Recovered: ${DETAIL}

Back up at $(date -u '+%Y-%m-%d %H:%M UTC') · [workflow run](${RUN_URL})"
  gh issue close "$open_issue"
  echo "Closed issue #${open_issue} after recovery"
else
  echo "Site is up, nothing to report"
fi
