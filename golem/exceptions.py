class GolemException(Exception):
    pass


class MissingConfiguration(GolemException):
    def __init__(self, key: str, description: str):
        self._key = key
        self._description = description

    def __str__(self) -> str:
        return f"Missing configuration for {self._description}. Please set env var {self._key}."
