from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union

ArgsDict = Dict[str, Union[str, List[str], Dict[str, Any]]]


class Command(ABC):
    def text(self) -> Dict[str, ArgsDict]:
        return {type(self).__name__.lower(): self.args_dict()}

    @abstractmethod
    def args_dict(self) -> ArgsDict:
        raise NotImplementedError


class Deploy(Command):
    def args_dict(self) -> ArgsDict:
        return {}


class Start(Command):
    def args_dict(self) -> ArgsDict:
        return {}


class Run(Command):
    def __init__(self, entry_point: str, args: List[str]):
        self.entry_point = entry_point
        self.args = args

    def args_dict(self) -> ArgsDict:
        return {
            "entry_point": self.entry_point,
            "args": self.args,
            "capture": {
                "stdout": {
                    "stream": {},
                },
                "stderr": {
                    "stream": {},
                },
            }
        }
