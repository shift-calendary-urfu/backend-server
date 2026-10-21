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