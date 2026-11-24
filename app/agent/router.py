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
from app.workplaces.services import WorkplaceServices
from app.workplaces.schemas import WorkplaceUpdate, WorkplaceCreate
from app.agent.authorization import get_workplace_access, can_mutate_workplace
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
