#!/bin/bash
# Odoo backup script for customer VMs (Phase 2).
# Mirrors the SystemaOps internal backup: db + filestore + project archive,
# flock serialization and retention cleanup. Self-discovering across all
# customer workspaces under PROJECT_DIR so one nightly run covers every
# deployment on the host.
set -euo pipefail

PROJECT_DIR="${1:-/opt/systemaops}"
BACKUP_ROOT="${BACKUP_ROOT:-/srv/backups}"
DATE="$(date +%F)"
BACKUP_DIR="$BACKUP_ROOT/$DATE"
LOCK_FILE="/var/lock/systemaops_backup.lock"

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

mkdir -p "$BACKUP_DIR"

echo "Backup started $(date)"

find "$PROJECT_DIR" -maxdepth 2 -name deployment_summary.json -print0 | while IFS= read -r -d '' SUMMARY; do
  WORKSPACE="$(dirname "$SUMMARY")"
  DEPLOYMENT_ID="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['deployment_id'])")"
  DB_NAME="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['database_name'])")"
  DB_USER="$(grep -m1 '^db_user' "$WORKSPACE/config/odoo.conf" | cut -d= -f2 | tr -d ' ')"
  PREFIX="$(python3 -c "import json;print(json.load(open('$SUMMARY'))['container_prefix'])")"

  SUBDIR="$BACKUP_DIR/$DEPLOYMENT_ID"
  mkdir -p "$SUBDIR"

  cd "$WORKSPACE"
  DB_CONTAINER="$(docker compose ps -q db_${PREFIX} 2>/dev/null || true)"
  ODOO_CONTAINER="$(docker compose ps -q odoo_${PREFIX} 2>/dev/null || true)"

  if [ -z "$DB_CONTAINER" ] || [ -z "$ODOO_CONTAINER" ]; then
    echo "Containers not running for $DEPLOYMENT_ID"
    continue
  fi

  echo "Backing up $DEPLOYMENT_ID ($DB_NAME)"

  # Database backup
  docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$SUBDIR/db.sql.gz"

  # Filestore backup
  docker exec "$ODOO_CONTAINER" tar -czf - /var/lib/odoo > "$SUBDIR/filestore.tar.gz"

  # Project backup
  tar -czf "$SUBDIR/systemaops.tar.gz" -C "$WORKSPACE" .

  # Offsite copy hook (optional): point OFFSITE_TARGET to an rsync/scp destination.
  if [[ -n "${OFFSITE_TARGET:-}" ]]; then
    rsync -az "$SUBDIR/" "$OFFSITE_TARGET/$DEPLOYMENT_ID/"
  fi
done

# Retention cleanup
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +"${RETENTION_DAYS:-4}" -exec rm -rf {} +

echo "Backup finished $(date)"
