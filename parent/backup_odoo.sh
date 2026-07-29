#!/bin/bash
set -euo pipefail

PROJECT_DIR="/root/odoo/systemaops"
BACKUP_ROOT="/srv/backups"
DATE="$(date +%F)"
BACKUP_DIR="$BACKUP_ROOT/$DATE"
LOCK_FILE="/var/lock/odoo_backup.lock"

DB_NAME="odoo_db"
DB_USER="odoo"

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"

DB_CONTAINER="$(docker compose ps -q db)"
ODOO_CONTAINER="$(docker compose ps -q odoo18)"

if [ -z "$DB_CONTAINER" ] || [ -z "$ODOO_CONTAINER" ]; then
  echo "Containers not running"
  exit 1
fi

echo "Backup started $(date)"

# Database backup
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_DIR/db.sql.gz"

# Filestore backup
docker exec "$ODOO_CONTAINER" tar -czf - /var/lib/odoo > "$BACKUP_DIR/filestore.tar.gz"

# Project backup
tar -czf "$BACKUP_DIR/systemaops.tar.gz" -C /root/odoo systemaops

# Retention cleanup
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +4 -type d -print -exec rm -rf {} \;

echo "Backup finished $(date)"

