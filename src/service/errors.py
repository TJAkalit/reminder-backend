class ServiceError(Exception):
    pass


class NotFoundError(ServiceError):
    pass


class ForbiddenError(ServiceError):
    pass


class ChecklistClosedError(ServiceError):
    pass


class ValidationError(ServiceError):
    pass
