import asyncio
import hashlib
import queue
from typing import List
import random
import string

from golem_api import execute_tasks, Payload
from golem_api.commands import Run
from golem_api.low import Activity

PAYLOAD = Payload.from_image_hash("055911c811e56da4d75ffc928361a78ed13077933ffa8320fb1ec2db")
PASSWORD_LENGTH = 4
CHUNK_SIZE = 2 ** 16
MAX_WORKERS = 10

tasks_queue = queue.LifoQueue()
results = set()


class MainTask:
    def __init__(self, mask: str, hash_: str, hash_type: int, attack_mode: int):
        self.mask = mask
        self.hash_ = hash_
        self.hash_type = hash_type
        self.attack_mode = attack_mode

    async def execute(self, activity: Activity):
        cmd = f"hashcat --keyspace -a {self.attack_mode} -m {self.hash_type} {self.mask}"
        batch = await activity.execute_commands(Run(cmd))
        await batch.wait(timeout=30)
        result = batch.events[-1].stdout
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
    def __init__(self, mask: str, hash_: str, hash_type: int, attack_mode: int, skip: int, limit: int):
        self.mask = mask
        self.hash_ = hash_
        self.hash_type = hash_type
        self.attack_mode = attack_mode
        self.skip = skip
        self.limit = limit

    async def execute(self, activity: Activity):
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


async def main_task_source():
    mask = "".join(["?a" for _ in range(PASSWORD_LENGTH)])
    chars = string.ascii_letters + string.digits + string.punctuation

    while True:
        if tasks_queue.qsize() < MAX_WORKERS * 2:
            password = "".join([random.choice(chars) for i in range(len(mask) // 2)])
            hash_ = hashlib.sha256(password.encode()).hexdigest()
            task = MainTask(mask=mask, hash_=hash_, hash_type=1400, attack_mode=3)
            tasks_queue.put(task)
        else:
            await asyncio.sleep(0.1)


async def main() -> None:
    asyncio.create_task(main_task_source())
    async for result in execute_tasks(
        budget=1,
        execute_task=lambda activity, task: task.execute(activity),
        task_data=iter(tasks_queue.get, None),
        payload=PAYLOAD,
        max_workers=MAX_WORKERS,
    ):
        pass

    print("DONE")

if __name__ == '__main__':
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
