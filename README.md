# EconPulse — Сервіс моніторингу ігрової економіки та трекінгу цін на віртуальні предмети

Курсовий проєкт з дисципліни «Python-програмування» (ДУІТЗ, спеціальність 122 / F3 «Комп'ютерні науки»).

Система автоматично збирає ціни й обсяги пропозицій на віртуальні предмети **Warframe** та **Rust** із кількох відкритих торгових майданчиків у різних валютах (`PLT`, `EUR`, `USD`), приводить їх до єдиної валюти (`USD`), будує історію цін із серверною агрегацією, виявляє цінові аномалії щодо 7-денного ковзного середнього, надсилає сповіщення за порогами та веде транзакційний портфель угод користувача.

## Технологічний стек
- **Мова:** Python 3.12+ (сувора типізація `mypy --strict`, `ruff`)
- **API та веб-інтерфейс:** FastAPI, Uvicorn, Pydantic v2, OpenAPI / Swagger UI
- **База даних:** PostgreSQL 16, SQLAlchemy 2.0 (async), Alembic
- **Збір даних:** `httpx[brotli]` (async), ледачий конвеєр генераторів, retry with exponential backoff, rate limiting
- **Спостережуваність:** `structlog` (JSON-логи), наскрізний `X-Request-ID`, `/healthz`, RFC 9457 (`application/problem+json`)
- **CLI:** Typer (`econ-cli`)
- **Інфраструктура:** Docker, Docker Compose, GitHub Actions CI

## Зовнішні джерела даних
1. **Warframe Market API v2** (`api.warframe.market`) — PC та PlayStation ринки, ціни в Platinum (`PLT`), описи, теги, іконки.
2. **Skinport API** (`api.skinport.com`) — скіни Rust у валюті `EUR`.
3. **Rust.tm API** (`rust.tm`) — скіни Rust у валюті `USD` (зіставлення зі Skinport для обчислення спреду).
4. **Frankfurter (ECB) / API НБУ** — актуальні курси валют для приведення до `USD`.

## Швидкий запуск (Docker Compose)
```bash
cp .env.example .env
docker compose up --build
```
Після запуску автоматично застосовуються міграції Alembic, база наповнюється seed-даними (≥ 300 предметів і 30 діб історії, ≥ 9 000 знімків), і сервіс стає доступним за адресами:
- Веб-інтерфейс: `http://localhost:8000/`
- Документація OpenAPI (Swagger): `http://localhost:8000/docs`
- Перевірка працездатності: `http://localhost:8000/healthz`

## Демо-облікові записи (створюються автоматично при seed)
| Логін | Пароль | Роль |
|---|---|---|
| `admin` | `admin123!` | Адміністратор |
| `analyst` | `analyst123!` | Аналітик |
| `trader` | `trader123!` | Користувач |

## Команди CLI
```bash
econ-cli seed                # Наповнити БД (300+ предметів, 30 діб історії)
econ-cli collect             # Запустити збір даних з усіх активних майданчиків
econ-cli report --game rust  # Зформувати аналітичний звіт у консоль/JSON
```

## Тестування та перевірка якості
```bash
ruff check src tests
mypy src
pytest --cov=econ_tracker --cov-report=term-missing
```

## Резервне копіювання та відновлення БД (PostgreSQL)
```bash
# Створення резервної копії
docker compose exec -T db pg_dump -U econ -d econ_tracker -Fc > backup.dump

# Відновлення з резервної копії
docker compose exec -T db pg_restore -U econ -d econ_tracker --clean --if-exists < backup.dump
```

## Архітектурні рішення (ADR)
Див. каталог [`docs/adr/`](docs/adr/).
