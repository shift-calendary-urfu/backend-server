class EmailExistsException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class UsernamePasswordException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class InvalidRefreshTokenException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class InvalidPasswordException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class WorkplaceNotFoundException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class WorkplaceExistsException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class UserNotFoundException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class EmployeeAlreadyInWorkPlaceExceprion(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class EmployeeNotFoundException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class ShiftNotFoundException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class InvalidReportPeriodException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)



class WorkplaceChatNotFoundException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class WorkplaceChatCreationException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class ChatWithSelfException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class CommonWorkplaceNotFoundException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class ChatNotFoundException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)


class ChatReadOnlyException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)

class InvalidMessageTextException(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg)