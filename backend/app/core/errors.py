"""Domain errors, translated to HTTP only at the application boundary."""


class ResourceNotFound(Exception):
    pass


class ResourceConflict(Exception):
    pass
