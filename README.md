# goit-cloud-computing-fp

Колекція цитат — фінальний проєкт GoIT із хмарних обчислень.

```text
app/                    # застосунок і пов’язані компоненти
    app/                # Python-пакет FastAPI та статичні файли інтерфейсу
    tests/              # HTTP-тести
    requirements.txt    # Python-залежності
    Dockerfile          # збирання образу застосунку
    compose.yaml        # застосунок, ініціалізація БД і PostgreSQL
    .env.example        # приклад локальних налаштувань
img/                    # скриншоти проєкту
```

Команди запуску й тестування виконувати з кореневої папки `app`:

```powershell
cd app
Copy-Item .env.example .env
docker compose up --build -d
```

Застосунок: <http://localhost:8000>, API: <http://localhost:8000/docs>.

Початкові цитати з `app/app/seed.csv` завантажуються під час ініціалізації лише в порожню БД.
Формат CSV і параметр `--seed` описано в [інструкції](docs/README.md#початкові-дані-з-seedcsv).
