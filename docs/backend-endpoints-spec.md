# Спецификация API-эндпоинтов для 1 спринта

## Общая информация

- **Base URL:** `/api/v1`
- **Аутентификация:** JWT Bearer Token (кроме `/auth/*`)
- **Формат данных:** JSON
- **Версионирование:** через URL (`/api/v1/...`)

---

## Роутер 1: `auth` (Аутентификация)

**Префикс:** `/api/v1/auth`

| Метод | Путь | Описание | Request | Response | Auth |
|-------|------|----------|---------|----------|:----:|
| POST | `/register` | Регистрация нового пользователя | `email`, `password`, `first_name`, `second_name`, `third_name` (опц.), `phone` (опц.) | `{id, email, first_name, second_name, ...}` | ❌ |
| POST | `/login` | Вход в систему, получение JWT | `email`, `password` | `{access_token, token_type}` | ❌ |
| POST | `/logout` | Выход из системы (опционально, можно просто удалить токен на клиенте) | — | `{message: "Logged out"}` | ✅ |

**Примечания:**
- При регистрации создаётся только `User`, без привязки к точкам
- `access_token` имеет срок жизни (например, 30 минут)
- Для refresh token можно добавить `/refresh` в спринте 2

---

## Роутер 2: `users` (Профиль пользователя)

**Префикс:** `/api/v1/users`

| Метод | Путь | Описание | Request | Response | Auth | Роли |
|-------|------|----------|---------|----------|:----:|------|
| GET | `/me` | Получить текущего пользователя | — | `{id, email, first_name, second_name, third_name, phone}` | ✅ | Все |
| PUT | `/me` | Обновить профиль текущего пользователя | `first_name`, `second_name`, `third_name`, `phone` (все опц.) | Обновлённый пользователь | ✅ | Все |
| PUT | `/me/password` | Изменить пароль | `old_password`, `new_password` | `{message: "Password updated"}` | ✅ | Все |

**Примечания:**
- `/me` — стандартный паттерн для получения данных текущего пользователя
- Email нельзя изменить (или только через отдельный flow с подтверждением)
- Пароль меняется только после проверки старого пароля

---

## Роутер 3: `workplaces` (Рабочие точки)

**Префикс:** `/api/v1/workplaces`

| Метод | Путь | Описание | Request | Response | Auth | Роли |
|-------|------|----------|---------|----------|:----:|------|
| GET | `/` | Получить список точек текущего пользователя (где он owner или employee) | — | `[{id, name, address, workplace_type, owner_id, ...}]` | ✅ | Все |
| GET | `/{workplace_id}` | Получить детальную информацию о точке | — | `{id, name, address, phone, description, workplace_type, owner_id, ...}` | ✅ | Owner/Admin/Employee точки |
| POST | `/` | Создать новую рабочую точку | `name`, `address`, `phone`, `description`, `workplace_type` | Созданная точка | ✅ | Все (автоматически становится owner) |
| PUT | `/{workplace_id}` | Обновить рабочую точку | `name`, `address`, `phone`, `description`, `workplace_type` (все опц.) | Обновлённая точка | ✅ | Owner/Admin точки |
| DELETE | `/{workplace_id}` | Удалить рабочую точку | — | `{message: "Workplace deleted"}` | ✅ | Owner точки |
| GET | `/{workplace_id}/employees` | Получить список сотрудников точки | `is_active` (опц., фильтр) | `[{id, user_id, role_in_workplace, position, ...}]` | ✅ | Owner/Admin/Employee точки |

**Примечания:**
- При создании точки пользователь автоматически становится `owner` (через `Workplace.owner_id`)
- Удаление точки — каскадное (удаляются все сотрудники, смены, шаблоны) или soft delete? **Нужно обсудить с командой**
- Фильтр `is_active` для сотрудников — чтобы показать только активных

---

## Роутер 4: `employees` (Сотрудники)

**Префикс:** `/api/v1/employees`

| Метод | Путь | Описание | Request | Response | Auth | Роли |
|-------|------|----------|---------|----------|:----:|------|
| POST | `/` | Добавить сотрудника в точку | `user_id` (ID существующего пользователя), `workplace_id`, `role_in_workplace`, `position`, `hire_date` | Созданный профиль сотрудника | ✅ | Owner/Admin точки |
| GET | `/{employee_id}` | Получить информацию о сотруднике | — | `{id, user_id, workplace_id, role_in_workplace, position, ...}` | ✅ | Owner/Admin/Employee точки |
| PUT | `/{employee_id}` | Обновить информацию о сотруднике | `role_in_workplace`, `position`, `hire_date`, `is_active` (все опц.) | Обновлённый профиль | ✅ | Owner/Admin точки |
| DELETE | `/{employee_id}` | Удалить сотрудника из точки (или деактивировать) | — | `{message: "Employee removed"}` | ✅ | Owner/Admin точки |
| GET | `/me/workplaces` | Получить список точек, где текущий пользователь является сотрудником | — | `[{id, workplace_id, role_in_workplace, ...}]` | ✅ | Все |

**Примечания:**
- При добавлении сотрудника нужно проверить, что `user_id` существует и не является уже сотрудником в этой точке (UNIQUE constraint)
- `DELETE` может быть soft delete (установить `is_active = False`) или hard delete — **нужно обсудить**
- `/me/workplaces` — полезно для переключения между точками в интерфейсе

---

## Роутер 5: `shifts` (Смены)

**Префикс:** `/api/v1/shifts`

| Метод | Путь | Описание | Request | Response | Auth | Роли |
|-------|------|----------|---------|----------|:----:|------|
| GET | `/` | Получить список смен с фильтрами | `workplace_id` (опц.), `employee_id` (опц.), `date_from` (опц.), `date_to` (опц.), `status` (опц.) | `[{id, workplace_id, employee_id, date, start_time, end_time, status, ...}]` | ✅ | Owner/Admin/Employee точки |
| GET | `/{shift_id}` | Получить детальную информацию о смене | — | `{id, workplace_id, employee_id, date, start_time, end_time, status, notes, ...}` | ✅ | Owner/Admin/Employee точки |
| POST | `/` | Создать новую смену | `workplace_id`, `employee_id`, `date`, `start_time`, `end_time`, `notes` (опц.) | Созданная смена | ✅ | Owner/Admin точки |
| PUT | `/{shift_id}` | Обновить смену | `employee_id`, `date`, `start_time`, `end_time`, `status`, `notes` (все опц.) | Обновлённая смена | ✅ | Owner/Admin точки |
| DELETE | `/{shift_id}` | Удалить смену | — | `{message: "Shift deleted"}` | ✅ | Owner/Admin точки |
| POST | `/bulk` | Массовое создание смен (для размножения) | `[{workplace_id, employee_id, date, start_time, end_time}, ...]` | `[{created_shifts}, {errors}]` | ✅ | Owner/Admin точки |
| GET | `/calendar` | Получить смены для календаря (по точке и периоду) | `workplace_id`, `date_from`, `date_to` | `{dates: {"2026-10-15": [{employee_id, start_time, end_time}, ...]}}` | ✅ | Owner/Admin/Employee точки |

**Примечания:**
- Фильтры в `GET /` — для гибкого поиска (по точке, сотруднику, периоду, статусу)
- `POST /bulk` — для быстрого создания нескольких смен сразу (например, при размножении)
- `GET /calendar` — специальный эндпоинт для календаря, возвращает данные в удобном для фронтенда формате (группировка по датам)
- **Важно:** нужно добавить проверку на пересечение смен одного сотрудника в одно время (бизнес-логика)

---

## Роутер 6: `shift_templates` (Шаблоны для автоформирования)

**Префикс:** `/api/v1/shift_templates`

| Метод | Путь | Описание | Request | Response | Auth | Роли |
|-------|------|----------|---------|----------|:----:|------|
| GET | `/` | Получить список шаблонов | `workplace_id` (опц.), `employee_id` (опц.), `is_active` (опц.) | `[{id, workplace_id, employee_id, work_pattern, ...}]` | ✅ | Owner/Admin точки |
| GET | `/{template_id}` | Получить детальную информацию о шаблоне | — | `{id, workplace_id, employee_id, work_pattern, shift_duration_hours, ...}` | ✅ | Owner/Admin/Employee точки |
| POST | `/` | Создать новый шаблон | `workplace_id`, `employee_id`, `work_pattern`, `shift_duration_hours`, `default_start_time`, `cycle_start_date` | Созданный шаблон | ✅ | Owner/Admin точки |
| PUT | `/{template_id}` | Обновить шаблон | `work_pattern`, `shift_duration_hours`, `default_start_time`, `cycle_start_date`, `is_active` (все опц.) | Обновлённый шаблон | ✅ | Owner/Admin точки |
| DELETE | `/{template_id}` | Удалить шаблон | — | `{message: "Template deleted"}` | ✅ | Owner/Admin точки |
| POST | `/generate` | Сгенерировать смены на основе шаблона | `template_id`, `date_from`, `date_to` | `{generated_shifts: [...], conflicts: [...]}` | ✅ | Owner/Admin точки |

**Примечания:**
- `POST /generate` — **ключевой эндпоинт для Приоритета 2** (автоматическое формирование графика)
- Алгоритм берёт шаблон и генерирует смены на период `date_from` — `date_to`
- Возвращает список созданных смен и список конфликтов (если есть пересечения)
- **Важно:** нужно обсудить с командой, как обрабатывать конфликты (пересечения смен)

---

## Дополнительные эндпоинты (мои предложения)

### 1. Дашборд / Статистика (опционально для MVP)

**Префикс:** `/api/v1/dashboard`

| Метод | Путь | Описание | Request | Response | Auth | Роли |
|-------|------|----------|---------|----------|:----:|------|
| GET | `/overview` | Общая статистика по точке | `workplace_id` | `{total_employees, total_shifts_this_month, upcoming_shifts, ...}` | ✅ | Owner/Admin точки |

**Зачем:** Для главной страницы после входа — быстрый обзор ситуации.

### 2. Проверка доступности сотрудника

**Префикс:** `/api/v1/shifts`

| Метод | Путь | Описание | Request | Response | Auth | Роли |
|-------|------|----------|---------|----------|:----:|------|
| GET | `/check-availability` | Проверить, доступен ли сотрудник в указанное время | `employee_id`, `date`, `start_time`, `end_time` | `{available: true/false, conflicts: [...]}` | ✅ | Owner/Admin точки |

**Зачем:** Перед созданием смены можно проверить, не занят ли сотрудник в это время.

### 3. Массовые операции со сменами

**Префикс:** `/api/v1/shifts`

| Метод | Путь | Описание | Request | Response | Auth | Роли |
|-------|------|----------|---------|----------|:----:|------|
| POST | `/bulk-delete` | Массовое удаление смен | `shift_ids: [...]` | `{deleted: [...], errors: [...]}` | ✅ | Owner/Admin точки |
| POST | `/bulk-update` | Массовое обновление смен | `shift_ids: [...]`, `updates: {...}` | `{updated: [...], errors: [...]}` | ✅ | Owner/Admin точки |

**Зачем:** Для удобного управления календарём (удалить все смены за неделю, перенести все смены сотрудника и т.д.).

---

## Сводная таблица всех эндпоинтов

| Роутер | Количество эндпоинтов | Основные операции |
|--------|:---------------------:|-------------------|
| `auth` | 3 | Регистрация, вход, выход |
| `users` | 3 | Профиль, настройки, смена пароля |
| `workplaces` | 6 | CRUD точек, просмотр сотрудников |
| `employees` | 5 | CRUD сотрудников, переключение между точками |
| `shifts` | 7 | CRUD смен, календарь, массовые операции |
| `shift_templates` | 6 | CRUD шаблонов, генерация смен |
| **Итого** | **30** | — |

---

## Матрица доступа по ролям

| Роль | Что может делать |
|------|------------------|
| **Owner точки** | Всё: CRUD точек, сотрудников, смен, шаблонов |
| **Admin точки** | CRUD сотрудников, смен, шаблонов (но не может удалить точку) |
| **Employee точки** | Просмотр смен, своего профиля. Не может создавать/редактировать |

**Реализация:** Через зависимости FastAPI (`Depends`). Пример:

```python
async def get_current_owner(
    workplace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    workplace = await db.get(Workplace, workplace_id)
    if workplace.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user
```

---

## 💡 Ключевые решения, которые нужно обсудить с командой

### 1. Удаление рабочей точки
- **Вариант А:** Hard delete (каскадное удаление всех связанных данных)
- **Вариант Б:** Soft delete (пометить как удалённую, но не удалять данные)

**Рекомендация:** Soft delete для безопасности (можно восстановить).

### 2. Удаление сотрудника
- **Вариант А:** Hard delete (удалить профиль, но оставить историю смен)
- **Вариант Б:** Soft delete (установить `is_active = False`)

**Рекомендация:** Soft delete (сохраняем историю).

### 3. Конфликты при создании смен
Что делать, если сотрудник уже занят в это время в другой точке?
- **Вариант А:** Запретить создание (возвращать ошибку)
- **Вариант Б:** Разрешить, но показать предупреждение
- **Вариант В:** Разрешить без предупреждений

**Рекомендация:** Вариант Б (предупреждение, но не запрет).

### 4. Формат календаря
Как фронтенд хочет получать данные для календаря?
- **Вариант А:** Плоский список смен с фильтрами
- **Вариант Б:** Группировка по датам (как в `GET /calendar`)

**Рекомендация:** Оба варианта (плоский список для фильтрации, группировка для календаря).
