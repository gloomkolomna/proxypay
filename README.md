# pay-gateway (ProxyPay)

Единый платёжный шлюз для игр на одном счёте MONETA (PayAnyWay).
Реализация плана `ПЛАН_ПЕРЕНОСА_ПЛАТЕЛЕЙ.md` (ревизия 4): Этапы 0–2 —
ядро шлюза, доставка вебхуков, админка на VK ID с CRUD реестра игр.

## Структура

```
app/                FastAPI-приложение (запуск: uvicorn app.main:app — из корня, см. ниже)
  main.py           сборка; порядок роутов важен (/pay/{txn} — catch-all, последний)
  config.py         ENV (секреты игр — НЕ здесь, они в БД)
  db.py             SQLAlchemy (SQLite + WAL; in-memory → StaticPool для тестов)
  models.py         Order, WebhookDelivery, GameRegistry, GatewayLog, GatewaySetting
  games.py          CRUD реестра игр + валидация (game_id ^[a-z0-9_]+$, URL-ы)
  security.py       HMAC-SHA256 (входящие от игр ±5 мин timestamp; исходящие вебхуки)
  moneta.py         подписи PayAnyWay (перенос 1:1 из драконьего moneta_service.py)
  auth.py           VK ID OAuth2 (PKCE) → JWT; allowlist ADMIN_VK_ALLOWED_IDS
  routes/           orders, pay (HTML-форма), moneta/callback, redirects, auth, admin
  services/         order_service, webhook_dispatcher, scheduler, settings_service
  tests/            65 тестов (pytest, in-memory SQLite)
alembic/            миграции (начальная 0001)
web/                SPA-админка (Vite+React+TS), собирается в web/dist
```

## Быстрый старт (dev)

```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt       # Windows (Linux: venv/bin/pip)
copy .env.example .env                             # заполнить (минимум: SECRET_KEY, ADMIN_VK_*)
venv/Scripts/python -m alembic upgrade head        # создать БД
cd web && npm install && npm run build && cd ..    # собрать админку
APP_ENV=dev venv/Scripts/python -m uvicorn app.main:app --port 8002
```

- Админка: http://127.0.0.1:8002/pay/admin/ (вход через VK ID; в dev есть `POST /pay/api/auth/dev-login {vk_id}`)
- Тесты: `venv/Scripts/python -m pytest app/tests -q`

## ENV (`.env`)

| Переменная | Назначение |
|---|---|
| `SECRET_KEY` | JWT админки (≥32 байта) |
| `ADMIN_VK_CLIENT_ID/SECRET/REDIRECT_URI` | Отдельное VK ID-приложение «ProxyPay Admin» |
| `ADMIN_VK_ALLOWED_IDS` | Кто админ (csv vk_id) |
| `MONETA_MNT_ID`, `MONETA_INTEGRITY_CODE` | Учётка MONETA |
| `MONETA_TEST_MODE` | 1 → demo.moneta.ru, 0 → прод |
| `MONETA_NO_SIGNATURE_CALLBACK`, `MONETA_CALLBACK_IPS` | Режим проверки колбэка |
| `PAYMENTS_TEST_MODE`, `PAYMENTS_TEST_VK_ID` | Начальные значения (дальше — тумблер в админке, в БД) |
| `ORDER_TTL_MINUTES` | TTL заказа (60) |

## Добавление игры

1. Админка → Игры → «Добавить игру» (game_id, URL-ы, чек-настройки).
2. Скопировать выданные `api_key` / `webhook_secret` в `.env` игры:
   `PAY_GATEWAY_API_KEY` / `PAY_GATEWAY_WEBHOOK_SECRET`.
3. Без рестарта шлюза. Пока идёт интеграция — `is_active=false`.

## Контракт для игр

**POST /pay/orders** — заголовки `X-Game-Id`, `X-Timestamp` (unix, ±5 мин),
`X-Game-Signature: HMAC-SHA256(raw_body, api_key)`; тело:
`{vk_id, amount_kop, description, receipt_email?, receipt_items?[{name, price_kop, quantity}]}`
→ `201 {transaction_id, payment_url, amount_kop, expires_at}`.
Ошибки: 401 (подпись/игра), 403 (`test_blocked` / `game disabled`), 422.

**GET /pay/orders/{txn}** — статус (та же подпись; без vk_id в ответе).

**GET /pay/status/{txn}** — публичный статус для браузерной страницы оплаты игры
(без подписи — в браузере ключей нет). Отдаёт минимум:
`{transaction_id, status: pending|success|cancelled|failed, paid_at, expires_at}` —
без vk_id/суммы/email. Сценарий: после оплаты шлюз редиректит игрока на
`success_url`/`fail_url` c `?txn=…`; страница статуса в игре опрашивает этот
эндпоинт, показывает результат и ведёт игрока обратно в сообщество/бота.

**GET /pay/{txn}** — HTML auto-submit форма MONETA (для игрока).

**Вебхук игре** — `POST {webhook_url}` c `X-Pay-Signature: HMAC-SHA256(body, webhook_secret)`,
тело `{transaction_id, game_id, vk_id, amount_kop, status: "success", paid_at, moneta_operation_id}`.
Ожидается 2xx; 404 трактуется как ретрай (гонка «вебхук раньше сохранения txn»).
Ретраи: 1м/5м/15м/1ч/4ч/24ч (1 первичная + 6), потом `failed` + кнопка переотправки в админке.

## Nginx (FastPanel)

```nginx
location /pay/ {
    proxy_pass http://127.0.0.1:8002;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;  # обязателен для IP-allowlist MONETA
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

В кабинете MONETA: Result URL = `https://<домен>/pay/moneta/callback`.

⚠️ Запускать **строго одним воркером** (`-w 1`): scheduler и webhook-dispatcher
живут в процессе; второй воркер даст дубли отправок.

## Развёртывание (прод)

Репозиторий: https://github.com/gloomkolomna/proxypay.git

Артефакты в `deploy/`:
- `deploy.sh` — **основной способ**: обновляет код из git, ставит зависимости,
  гоняет миграции, собирает админку, перезапускает сервис и делает health-check.
  Первый запуск:
  ```bash
  git clone -b main https://github.com/gloomkolomna/proxypay.git /opt/pay-gateway
  /opt/pay-gateway/deploy/deploy.sh     # остановится: заполни .env
  nano /opt/pay-gateway/.env            # SECRET_KEY, ADMIN_VK_*, MONETA_*
  /opt/pay-gateway/deploy/deploy.sh     # теперь до конца
  ```
- `pay-gateway.service` — systemd-юнит: gunicorn, **`-w 1`** (строго один воркер —
  scheduler и webhook-dispatcher живут в процессе), порт 8002.
- `nginx-pay.conf.example` — location `/pay/` с обязательным
  `proxy_set_header X-Forwarded-For ...` (IP-allowlist колбэков MONETA).
- `backup.sh` — бэкап БД (sqlite3 `.backup`, консистентно при WAL), в крон раз в 6 ч.
  **БД содержит реестр игр и секреты** — потеря критична (план §9).

В кабинете MONETA: Result URL = `https://<домен>/pay/moneta/callback`.
Дальше: админка `/pay/admin/` → создать игру (секреты — в `.env` игры).
