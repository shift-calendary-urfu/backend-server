from pydantic import BaseModel, Field

from typing import Annotated


class RefreshTokenRequest(BaseModel):
    refresh_token: Annotated[str, Field(
        description="Refresh token для продления сессии"
    )]