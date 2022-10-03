from abc import ABC, abstractmethod
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path
import shlex

from yapapi.storage import Destination, Source
from yapapi.storage.gftp import GftpProvider

ArgsDict = Dict[str, Union[str, List[str], Dict[str, Any]]]


class Command(ABC):
    def text(self) -> Dict[str, ArgsDict]:
        return {self.command_name: self.args_dict()}

    @property
    def command_name(self) -> str:
        return type(self).__name__.lower()

    @abstractmethod
    def args_dict(self) -> ArgsDict:
        raise NotImplementedError

    async def before(self) -> None:
        pass

    async def after(self) -> None:
        pass


class Deploy(Command):
    def args_dict(self) -> ArgsDict:
        return {}


class Start(Command):
    def args_dict(self) -> ArgsDict:
        return {}


class Run(Command):
    def __init__(self, command: Union[str, List[str]], *, shell: Optional[bool] = None, shell_cmd: str = "/bin/sh"):
        self.entry_point, self.args = self._resolve_init_args(command, shell, shell_cmd)

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

    @staticmethod
    def _resolve_init_args(
        command: Union[str, List[str]], shell: Optional[bool], shell_cmd: str
    ) -> Tuple[str, List[str]]:
        if shell is None:
            shell = isinstance(command, str)

        if shell:
            command_str = command if isinstance(command, str) else shlex.join(command)
            entry_point = shell_cmd
            args = ["-c", command_str]
        else:
            command_list = command if isinstance(command, list) else shlex.split(command)
            entry_point, *args = command_list

        if len(entry_point.split()) > 1:
            raise ValueError(f"Whitespaces in entry point '{entry_point}' are forbidden")

        return entry_point, args


class SendFile(Command):
    command_name = 'transfer'

    def __init__(self, src_path: str, dst_path: str):
        self.src_path = src_path
        self.dst_path = dst_path

        self._tmp_dir = TemporaryDirectory()
        self._gftp = GftpProvider(tmpdir=self._tmp_dir.name)
        self._source: Optional[Source] = None

    async def before(self) -> None:
        self._source = await self._gftp.upload_file(Path(self.src_path))

    async def after(self) -> None:
        assert self._source is not None
        await self._gftp.release_source(self._source)

    def args_dict(self) -> ArgsDict:
        assert self._source is not None
        return {
            "from": self._source.download_url,
            "to": f"container:{self.dst_path}",
        }


class DownloadFile(Command):
    command_name = 'transfer'

    def __init__(self, src_path: str, dst_path: str):
        self.src_path = src_path
        self.dst_path = dst_path

        self._tmp_dir = TemporaryDirectory()
        self._gftp = GftpProvider(tmpdir=self._tmp_dir.name)
        self._destination: Optional[Destination] = None

    async def before(self) -> None:
        self._destination = await self._gftp.new_destination(Path(self.dst_path))

    async def after(self) -> None:
        assert self._destination is not None
        await self._destination.download_file(Path(self.dst_path))

    def args_dict(self) -> ArgsDict:
        assert self._destination is not None
        return {
            "from": f"container:{self.src_path}",
            "to": self._destination.upload_url,
        }
