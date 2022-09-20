from abc import ABC, abstractmethod
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

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
