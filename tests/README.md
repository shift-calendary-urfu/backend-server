# Запуск тестов

Тесты покрывают реализованные роутеры:

- `POST /auth/login` — вход (форма `username` + `password`, в ответе `access_token`, `refresh_token`, `token_type`)
- `/users` — `GET /users/me`, `PUT /users/me`, `PUT /users/me/password`
- `/workplaces` — создание, список, карточка, изменение, удаление и `GET /{id}/employees`

Каталог `app/` тесты только импортируют. Своя схема создаётся в временном файле SQLite, рабочая PostgreSQL не нужна и не изменяется.

## 1. Окружение проекта

Из корня репозитория, как в основном README:

```powershell
uv sync
```

Тестам дополнительно нужны `pytest`, `pytest-asyncio` и `aiosqlite`. Их можно поставить разово, не записывая в `pyproject.toml`:

```powershell
uv run --with pytest --with pytest-asyncio --with aiosqlite pytest --rootdir=. -c tests/pytest.ini tests
```

Та же команда и запускает тесты.

## 2. Если `uv` не установлен

Поставьте зависимости из `pyproject.toml` в виртуальное окружение, затем тестовые пакеты. Запускать pytest нужно из корня репозитория.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install "fastapi[standard]" "sqlalchemy>=2.1.4" "asyncpg>=0.32.0" "greenlet>=3.5.6" "pwdlib[argon2]" "pydantic-settings" "pyjwt" "email-validator" "python-multipart"
pip install pytest pytest-asyncio aiosqlite
pytest --rootdir=. -c tests/pytest.ini tests
```

## 3. Отдельные файлы

```powershell
pytest --rootdir=. -c tests/pytest.ini tests/test_login.py
pytest --rootdir=. -c tests/pytest.ini tests/test_users.py
pytest --rootdir=. -c tests/pytest.ini tests/test_workplaces.py
```

## Что проверяется

- успешный вход и содержимое JWT (`sub`, `id`, `token_type`, срок refresh длиннее access);
- отказ при неверном пароле, неизвестном email, неактивном пользователе, пустом пароле и входе по телефону;
- логин принимает form-data (`username` — это email), JSON с полем `email` отклоняется;
- профиль `/users/me` без токена, с битым, просроченным и refresh-токеном;
- частичное обновление профиля, телефон `8XXXXXXXXXX`, пустое тело, смена email и пароля;
- точка создаётся от имени текущего пользователя;
- дубликат адреса и типа у того же владельца, повтор после удаления, другой тип и другой владелец;
- список точек: владелец, активный сотрудник, неактивный сотрудник, чужие точки;
- чтение карточки владельцем, сотрудником и админом; чужой пользователь и несуществующий id получают 403;
- изменение и удаление доступны только владельцу (админ точки тоже получает 403);
- удаление мягкое: точка, сотрудники, смены и шаблоны становятся неактивными, повторное удаление — 404;
- список сотрудников точки не включает неактивных и закрыт для посторонних.
