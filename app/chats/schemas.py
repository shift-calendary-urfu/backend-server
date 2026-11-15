
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.chats.models.chat import ChatType


# ==================== Common types ====================

ChatId = Annotated[
    int,
    Field(gt=0, description="Уникальный идентификатор чата"),
]

UserId = Annotated[
    int,
    Field(gt=0, description="Уникальный идентификатор пользователя"),
]

MessageId = Annotated[
    int,
    Field(gt=0, description="Уникальный идентификатор сообщения"),
]

MessageText = Annotated[
    str,
    Field(
        min_length=1,
        max_length=4000,
        description="Текст сообщения (от 1 до 4000 символов)",
    ),
]

ChatTitle = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
        description="Название чата",
    ),
]

ChatLimit = Annotated[
    int,
    Field(
        ge=1,
        le=100,
        description="Количество сообщений для получения (от 1 до 100)",
    ),
]


# ==================== Chat schemas ====================

class ChatListItem(BaseModel):
    """Информация о чате в списке чатов пользователя."""

    id: ChatId

    type: Annotated[
        ChatType,
        Field(description="Тип чата: workplace или direct"),
    ]

    workplace_id: Annotated[
        int | None,
        Field(
            description="Идентификатор торговой точки для общего чата",
        ),
    ]

    title: ChatTitle

    is_readonly: Annotated[
        bool,
        Field(description="Запрещена ли отправка сообщений в чат"),
    ]

    unread_count: Annotated[
        int,
        Field(
            ge=0,
            description="Количество непрочитанных сообщений",
        ),
    ]

    last_message_text: Annotated[
        str | None,
        Field(description="Текст последнего сообщения"),
    ]

    last_message_at: Annotated[
        datetime | None,
        Field(description="Дата и время последнего сообщения"),
    ]


class DirectChatCreate(BaseModel):
    """Данные для создания или получения личного чата."""

    target_user_id: UserId = Field(
        description="Идентификатор пользователя, с которым открывается диалог",
    )


class DirectChatResponse(BaseModel):
    """Результат создания или получения личного чата."""

    chat_id: ChatId


# ==================== Message schemas ====================

class MessageResponse(BaseModel):
    """Сообщение в истории чата."""

    model_config = ConfigDict(from_attributes=True)

    id: MessageId

    chat_id: ChatId

    sender_id: Annotated[
        int | None,
        Field(description="Идентификатор автора сообщения"),
    ]

    sender_name: Annotated[
        str,
        Field(
            min_length=1,
            description="Имя автора сообщения или системное имя удалённого пользователя",
        ),
    ]

    text: MessageText

    created_at: Annotated[
        datetime,
        Field(description="Дата и время отправки сообщения"),
    ]


class MessageHistoryResponse(BaseModel):
    """Ответ с историей сообщений чата."""

    messages: Annotated[
        list[MessageResponse],
        Field(description="Список сообщений в хронологическом порядке"),
    ]


# ==================== Chat read schemas ====================

class ChatReadResponse(BaseModel):
    """Результат отметки сообщений прочитанными."""

    last_read_message_id: MessageId
