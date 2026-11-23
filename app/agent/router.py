from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent_service import AgentService, AgentServiceError
from app.agent.schemas import AgentAnswer, ListMyWorkplacesRequest
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
