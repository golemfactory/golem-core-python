from abc import ABC, abstractmethod
from typing import Dict, List, Union


class Command(ABC):
    def text(self):
        return {type(self).__name__.lower(): self.args_dict()}

    @abstractmethod
    def args_dict(self) -> Dict[str, Union[str, Dict, List[str]]]:
        raise NotImplementedError


class Deploy(Command):
    def args_dict(self):
        return {}


class Start(Command):
    def args_dict(self):
        return {}


class Run(Command):
    def __init__(self, entry_point: str, args: List[str]):
        self.entry_point = entry_point
        self.args = args

    def args_dict(self):
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
