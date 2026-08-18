#!/usr/bin/env bash
# Бэкап pay-gateway: БД содержит РЕЕСТР ИГР и СЕКРЕТЫ — потеря критична
# (план §9). Крон: 0 */6 * * * /opt/pay-gateway/deploy/backup.sh
set -euo pipefail

APP_DIR="/opt/pay-gateway"
BACKUP_DIR="/var/backups/pay-gateway"
DB="$APP_DIR/pay-gateway.db"
STAMP="$(date +%Y%m%d-%H%M%S)"
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

if [ -f "$DB" ]; then
    # SQLite: консистентный снапшот через .backup (не cp при живом WAL)
    sqlite3 "$DB" ".backup '$BACKUP_DIR/pay-gateway-$STAMP.db'"
    chmod 600 "$BACKUP_DIR/pay-gateway-$STAMP.db"
    echo "[backup] $BACKUP_DIR/pay-gateway-$STAMP.db"
fi

# Подчистить старые
find "$BACKUP_DIR" -name "pay-gateway-*.db" -mtime +${KEEP_DAYS} -delete

echo "[backup] done"
