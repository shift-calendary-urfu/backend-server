from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent_service import AgentService, AgentServiceError
from app.agent.schemas import (
    AgentAnswer,
    AgentConfirmationAnswer,
    AgentConfirmationRequest,
    ListMyWorkplacesRequest,
)
from app.agent.confirmation import consume_pending_action, cancel_pending_action
from app.agent.authorization import (
    can_manage_shifts,
    can_mutate_workplace,
    get_workplace_access,
)
from app.exceptions import EmployeeNotFoundException, WorkplaceNotFoundException
from app.shifts.schemas import ShiftCreate
from app.shifts.services import ShiftServices
from app.workplaces.services import WorkplaceServices
from app.workplaces.schemas import WorkplaceUpdate, WorkplaceCreate
from app.core.database import get_db
from app.core.security import get_current_user
from app.users.model import User


router = APIRouter(
    prefix="/agent",
    tags=["Agent"],
)


@router.post(
    "/query",
    response_model=AgentAnswer,
    response_model_exclude_defaults=True,
)
async def query_agent(
    body: ListMyWorkplacesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentAnswer:
    """Обрабатывает запрос пользователя о рабочих точках и календаре смен.

    Агент отвечает на запросы с учётом данных текущего пользователя. Сейчас он
    может показать рабочие точки пользователя, подготовить изменение рабочей
    точки или составить график смен одного сотрудника. Подготовленные изменения
    не применяются без отдельного подтверждения. Для подготовленного действия
    ответ содержит ``confirmation_required=True``, ``confirmation_id`` и краткое
    описание в ``confirmation_summary``. Передайте этот идентификатор в
    ``POST /agent/confirm``, чтобы подтвердить или отменить действие. Для
    неподдерживаемых запросов агент возвращает объяснение в поле ``answer``.

    Требуется авторизация. Поле ``query`` должно содержать непустой текст длиной
    от 1 до 500 символов; лишние поля в теле запроса не допускаются.

    Args:
        body: Текст запроса пользователя.
        db: Сессия базы данных для получения доступных пользователю данных.
        current_user: Аутентифицированный пользователь, от имени которого
            обрабатывается запрос.

    Returns:
        Ответ агента; при необходимости подтверждения также включает
        идентификатор и описание ожидающего действия.

    Raises:
        HTTPException: Возвращает 401 при отсутствии действительной авторизации,
            422 при некорректном запросе или его обработке и 502, если сервис
            агента или внешний языковой сервис недоступен.
    """
    try:
        return await AgentService(db=db, user=current_user).process(body.query)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except AgentServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error


@router.post(
    "/confirm",
    response_model=AgentConfirmationAnswer,
)
async def confirm_agent_action(
    body: AgentConfirmationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentConfirmationAnswer:
    """Подтверждает или отменяет подготовленное агентом действие.

    Передайте идентификатор подтверждения, полученный при обработке запроса
    через ``POST /agent/query``. Подтверждение действует 10 минут, может быть
    использовано только создавшим его пользователем и принимается однократно.
    При ``approved=True`` действие выполняется; права на изменение рабочей
    точки или составление смен проверяются повторно. При подтверждении графика
    смен уже существующие смены сотрудника на соответствующие даты пропускаются.
    При ``approved=False`` ожидающее действие отменяется без выполнения.

    Поле ``status`` в ответе принимает значение ``executed`` (действие выполнено),
    ``cancelled`` (действие отменено), ``expired`` (срок подтверждения истёк)
    или ``invalid`` (подтверждение не найдено, уже недействительно либо
    пользователю не разрешено выполнить действие). Поле ``answer`` содержит
    пояснение результата.

    Требуется авторизация. Подтверждение привязано к текущему пользователю;
    идентификатор другого пользователя не позволяет выполнить или отменить его
    действие.

    Args:
        body: Идентификатор ожидающего действия и решение о его выполнении.
        db: Сессия базы данных, используемая при выполнении действия.
        current_user: Аутентифицированный пользователь, которому принадлежит
            подтверждение.

    Returns:
        Итоговый статус подтверждения и текстовое описание результата.

    Raises:
        HTTPException: Возвращает 401 при отсутствии действительной авторизации
            и 422, если тело запроса не соответствует ожидаемой схеме.
    """
    if not body.approved:
        cancelled = cancel_pending_action(body.confirmation_id, current_user.id)
        if not cancelled:
            return AgentConfirmationAnswer(status="invalid", answer="Запрос подтверждения не найден")
        return AgentConfirmationAnswer(status="cancelled", answer="Действие отменено")

    pending, result = consume_pending_action(body.confirmation_id, current_user.id)
    if pending is None:
        return AgentConfirmationAnswer(
            status=result,
            answer=(
                "Срок подтверждения истёк"
                if result == "expired"
                else "Запрос подтверждения не найден или принадлежит другому пользователю"
            ),
        )

    if pending.action in {"update_workplace", "delete_workplace"}:
        role = await get_workplace_access(db, current_user, pending.workplace_id)
        if not can_mutate_workplace(role, pending.action):
            return AgentConfirmationAnswer(
                status="invalid",
                answer="У вас нет прав для выполнения этого действия",
            )

    if pending.action == "create_shifts":
        if pending.workplace_id is None:
            return AgentConfirmationAnswer(
                status="invalid",
                answer="Для подтверждённого графика не указана рабочая точка",
            )
        role = await get_workplace_access(db, current_user, pending.workplace_id)
        if not can_manage_shifts(role):
            return AgentConfirmationAnswer(
                status="invalid",
                answer="У вас нет прав для составления смен этой рабочей точки",
            )
        try:
            shifts = [
                ShiftCreate.model_validate(item)
                for item in pending.payload["shifts"]
            ]
            created_count, skipped_dates = await ShiftServices(db).create_scheduled_shifts(
                workplace_id=pending.workplace_id,
                employee_id=pending.payload["employee_id"],
                shifts=shifts,
            )
        except (
            EmployeeNotFoundException,
            WorkplaceNotFoundException,
            ValidationError,
            KeyError,
            TypeError,
        ) as error:
            return AgentConfirmationAnswer(
                status="invalid",
                answer=f"Не удалось применить график: {error}",
            )

        skipped_text = ""
        if skipped_dates:
            skipped_text = "; пропущены уже занятые даты: " + ", ".join(
                date.strftime("%d.%m.%Y") for date in skipped_dates
            )
        return AgentConfirmationAnswer(
            status="executed",
            answer=(
                f"График подтверждён. Создано смен: {created_count}"
                f"{skipped_text}. {pending.summary}"
            ),
        )

    services = WorkplaceServices(db)
    if pending.action == "update_workplace":
        await services.update_workplace(
            pending.workplace_id,
            WorkplaceUpdate.model_validate(pending.payload),
        )
        return AgentConfirmationAnswer(status="executed", answer=pending.summary)
    if pending.action == "delete_workplace":
        await services.delete_workplace(pending.workplace_id)
        return AgentConfirmationAnswer(status="executed", answer=pending.summary)
    if pending.action == "create_workplace":
        await services.create_workplace(
            WorkplaceCreate.model_validate(pending.payload),
            current_user,
        )
        return AgentConfirmationAnswer(status="executed", answer=pending.summary)

    return AgentConfirmationAnswer(status="invalid", answer="Неизвестное действие")
