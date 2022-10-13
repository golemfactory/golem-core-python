import asyncio
from dataclasses import dataclass
import hashlib
import queue
from typing import List, Union
import random
import string

from golem_api import execute_tasks, Payload
from golem_api.commands import Run
from golem_api.low import Activity

PAYLOAD = Payload.from_image_hash("055911c811e56da4d75ffc928361a78ed13077933ffa8320fb1ec2db")
CHUNK_SIZE = 2 ** 18
MAX_WORKERS = 10

tasks_queue = queue.LifoQueue()


@dataclass
class MainTask:
    mask: str
    hash_: str
    hash_type: int
    attack_mode: int
    timeout: int = 30

    @property
    def commands(self) -> List[Run]:
        cmd = f"hashcat --keyspace -a {self.attack_mode} -m {self.hash_type} {self.mask}"
        return [Run(cmd)]

    def process_result(self, result: str):
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


@dataclass
class AttackPartTask:
    mask: str
    hash_: str
    hash_type: int
    attack_mode: int
    skip: int
    limit: int
    timeout: int = 120

    @property
    def commands(self) -> List[Run]:
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

    def process_result(self, result: str):
        if result is not None:
            print(f"FOUND {result.strip()} between {self.skip} and {self.limit}")


async def main_task_source():
    mask = "?a?a?a?a"
    chars = string.ascii_letters + string.digits + string.punctuation

    while True:
        if tasks_queue.qsize() < MAX_WORKERS * 2:
            password = "".join([random.choice(chars) for i in range(len(mask) // 2)])
            hash_ = hashlib.sha256(password.encode()).hexdigest()
            task = MainTask(mask=mask, hash_=hash_, hash_type=1400, attack_mode=3)
            tasks_queue.put(task)
        else:
            await asyncio.sleep(0.1)


def get_tasks():
    while True:
        try:
            yield tasks_queue.get_nowait()
        except queue.Empty:
            return


async def execute_task(activity: Activity, task: Union[MainTask, AttackPartTask]):
    batch = await activity.execute_commands(*task.commands)
    await batch.wait(timeout=task.timeout)
    result = batch.events[-1].stdout
    task.process_result(result)


async def main() -> None:
    asyncio.create_task(main_task_source())
    async for result in execute_tasks(
        budget=1,
        execute_task=execute_task,
        task_data=get_tasks(),
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
