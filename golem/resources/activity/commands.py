import asyncio
import shlex
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from ya_activity import models

from golem.utils.storage import Destination, Source
from golem.utils.storage.gftp import GftpProvider

ArgsDict = Mapping[str, Union[str, List, Dict[str, Any]]]


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


class Script:
    """A helper class for executing multiple commands in a single batch.

    Details: :any:`execute_script`.
    """

    def __init__(self) -> None:
        self._commands: List[Command] = []
        self._futures: List[asyncio.Future[models.ExeScriptCommandResult]] = []

    @property
    def commands(self) -> List[Command]:
        return self._commands.copy()

    @property
    def futures(self) -> "List[asyncio.Future[models.ExeScriptCommandResult]]":
        return self._futures.copy()

    def add_command(self, command: Command) -> "asyncio.Future[models.ExeScriptCommandResult]":
        """Add a :any:`Command` to the script.

        Returns an awaitable that will (after a call to :any:`execute_script`):

        * Return the result of the command once it finished succesfully
        * Raise :any:`CommandFailed` if the command failed
        * Raise :any:`CommandCancelled` if any previous command in the same batch failed

        """
        self._commands.append(command)
        fut: asyncio.Future[models.ExeScriptCommandResult] = asyncio.Future()
        self._futures.append(fut)
        return fut


class Deploy(Command):
    """Executes `deploy()` in the exeunit."""

    def __init__(self, args_dict: Optional[ArgsDict] = None):
        self._args_dict = args_dict or {}

    def args_dict(self) -> ArgsDict:
        return self._args_dict


class Start(Command):
    """Executes `start()` in the exeunit."""

    def args_dict(self) -> ArgsDict:
        return {}


class Run(Command):
    """Executes `run()` in the exeunit."""

    def __init__(
        self,
        command: Union[str, List[str]],
        *,
        shell: Optional[bool] = None,
        shell_cmd: str = "/bin/sh",
    ):
        """Init Run.

        :param command: Either a list `[entry_point, *args]` or a string.
        :param shell: If True, command will be passed as a string to "/bin/sh -c".
            Default value is True if `command` is a string and False if it is a list.
        :param shell_cmd: Shell command, matters only in `shell` is True.

        Examples::

            Run(["/bin/echo", "foo"])                       # /bin/echo "foo"
            Run("echo foo")                                 # /bin/sh -c "echo foo"
            Run(["echo", "foo"], shell=True)                # /bin/sh -c "echo foo"
            Run(["/bin/echo", "foo", ">", "/my_volume/x"])  # /bin/echo "foo" ">" "/my_volume/x"
                                                            # (NOTE: this is usually **not** the
                                                            # intended effect)
            Run("echo foo > /my_volume/x")                  # /bin/sh -c "echo foo > /my_volume/x"
                                                            # (This is better)
        """
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
            },
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
    """Sends a local file to the exeunit."""

    command_name = "transfer"

    def __init__(self, src_path: str, dst_path: str):
        """Init SendFile.

        :param src_path: Name of the local file.
        :param dst_path: Remote (provider-side) path where the file will be saved.
            Usually this path should be under a directory specified as a VOLUME in the image.
        """
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
    """Downloads a file from the exeunit."""

    command_name = "transfer"

    def __init__(self, src_path: str, dst_path: str):
        """Init DownloadFile.

        :param src_path: Remote (provider-side) name of the file.
        :param dst_path: Path in the local filesystem where the file will be saved.
        """
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
