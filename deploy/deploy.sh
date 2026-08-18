#!/usr/bin/env bash
# Деплой pay-gateway на сервере из git (по образцу драконов).
#
# Первый запуск (fresh-хост):
#   git clone -b main https://github.com/gloomkolomna/proxypay.git /opt/pay-gateway
#   /opt/pay-gateway/deploy/deploy.sh          # остановится и попросит заполнить .env
#   nano /opt/pay-gateway/.env
#   /opt/pay-gateway/deploy/deploy.sh          # теперь до конца
#
# Дальнейшие обновления: просто /opt/pay-gateway/deploy/deploy.sh
set -euo pipefail

APP_DIR="/opt/pay-gateway"
VENV="$APP_DIR/venv"

cd "$APP_DIR"

echo "[deploy] git: обновление кода..."
git fetch origin main
git reset --hard origin/main

if [ ! -f .env ]; then
  cp .env.example .env
  echo "!!! Заполни $APP_DIR/.env (SECRET_KEY, ADMIN_VK_*, MONETA_*) и запусти снова"
  exit 1
fi

echo "[deploy] python-зависимости..."
if [ ! -d "$VENV" ]; then python3 -m venv "$VENV"; fi
"$VENV/bin/pip" install -q -r requirements.txt

echo "[deploy] миграции БД..."
"$VENV/bin/python" -m alembic upgrade head

echo "[deploy] сборка админки (web/)..."
if command -v npm >/dev/null 2>&1; then
  (cd web && npm install --silent && npm run build)
else
  echo "[deploy] WARN: npm не найден — админка не пересобрана (web/dist остался прежним)"
fi

echo "[deploy] systemd..."
mkdir -p /var/log/pay-gateway
if [ ! -f /etc/systemd/system/pay-gateway.service ]; then
  cp deploy/pay-gateway.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable pay-gateway
fi
systemctl restart pay-gateway
sleep 2
systemctl --no-pager -l status pay-gateway | head -8 || true

echo -n "[deploy] health check: "
curl -fsS http://127.0.0.1:8002/pay/health && echo " — OK"
echo "[deploy] готово. Админка: https://<домен>/pay/admin/"
