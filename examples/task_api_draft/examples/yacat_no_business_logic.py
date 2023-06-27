import asyncio
import hashlib
import random
import string
from typing import List, Union

from examples.task_api_draft.task_api.execute_tasks import execute_tasks
from golem.resources.activity import Activity, Run
from golem.resources.market import RepositoryVmPayload

PAYLOAD = RepositoryVmPayload("055911c811e56da4d75ffc928361a78ed13077933ffa8320fb1ec2db")
PASSWORD_LENGTH = 3
CHUNK_SIZE = 2**12
MAX_WORKERS = 3

tasks_queue: "asyncio.Queue[Union[MainTask, AttackPartTask]]" = asyncio.LifoQueue()
results = set()


class MainTask:
    def __init__(self, mask: str, hash_: str, hash_type: int, attack_mode: int):
        self.mask = mask
        self.hash_ = hash_
        self.hash_type = hash_type
        self.attack_mode = attack_mode

    async def execute(self, activity: Activity) -> None:
        cmd = f"hashcat --keyspace -a {self.attack_mode} -m {self.hash_type} {self.mask}"
        batch = await activity.execute_commands(Run(cmd))
        await batch.wait(timeout=30)
        result = batch.events[-1].stdout
        assert result is not None
        keyspace = int(result.strip())

        for skip in range(0, keyspace, CHUNK_SIZE):
            task = AttackPartTask(
                mask=self.mask,
                hash_=self.hash_,
                hash_type=self.hash_type,
                attack_mode=self.attack_mode,
                skip=skip,
                limit=skip + CHUNK_SIZE,
            )
            tasks_queue.put_nowait(task)


class AttackPartTask:
    def __init__(
        self, mask: str, hash_: str, hash_type: int, attack_mode: int, skip: int, limit: int
    ):
        self.mask = mask
        self.hash_ = hash_
        self.hash_type = hash_type
        self.attack_mode = attack_mode
        self.skip = skip
        self.limit = limit

    async def execute(self, activity: Activity) -> None:
        batch = await activity.execute_commands(*self._commands())
        await batch.wait(timeout=120)
        result = batch.events[-1].stdout
        if result is not None:
            print(f"FOUND {result.strip()} between {self.skip} and {self.limit}")
            results.add(result)

    def _commands(self) -> List[Run]:
        out_fname = "/golem/output/out.potfile"
        str_cmds = [
            f"rm -f {out_fname}",
            f"touch {out_fname}",
            (
                f"hashcat -a {self.attack_mode} -m {self.hash_type} "
                f"--self-test-disable --potfile-disable "
                f"--skip={self.skip} --limit={self.limit} -o {out_fname} "
                f"'{self.hash_}' '{self.mask}' "
                f"|| true"
            ),
            f"cat {out_fname}",
        ]
        return [Run(str_cmd) for str_cmd in str_cmds]


async def main_task_source() -> None:
    mask = "".join(["?a" for _ in range(PASSWORD_LENGTH)])
    chars = string.ascii_letters + string.digits + string.punctuation

    while True:
        if tasks_queue.qsize() < 1000:
            password = "".join([random.choice(chars) for i in range(len(mask) // 2)])
            hash_ = hashlib.sha256(password.encode()).hexdigest()
            task = MainTask(mask=mask, hash_=hash_, hash_type=1400, attack_mode=3)
            tasks_queue.put_nowait(task)
        else:
            await asyncio.sleep(0.1)


async def main() -> None:
    asyncio.create_task(main_task_source())
    await asyncio.sleep(0.1)
    async for result in execute_tasks(
        budget=1,
        execute_task=lambda activity, task: task.execute(activity),  # type: ignore[attr-defined]
        task_data=iter(tasks_queue.get_nowait, None),
        payload=PAYLOAD,
        max_workers=MAX_WORKERS,
    ):
        pass

    print("DONE")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    task = loop.create_task(main())
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
