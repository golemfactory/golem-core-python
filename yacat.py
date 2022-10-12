import asyncio
from dataclasses import dataclass
import queue
from typing import Iterator, List, Tuple, Union

from golem_api import execute_tasks, Payload
from golem_api.commands import Run
from golem_api.low import Activity

PAYLOAD = Payload.from_image_hash("055911c811e56da4d75ffc928361a78ed13077933ffa8320fb1ec2db")


@dataclass
class KeyspaceTask:
    mask: str
    hash_type: int
    attack_mode: int

    def commands(self) -> List[Run]:
        cmd = f"hashcat --keyspace -a {self.attack_mode} -m {self.hash_type} {self.mask}"
        return [Run(cmd)]


@dataclass
class AttackTask:
    mask: str
    hash_: str
    hash_type: int
    attack_mode: int = 3


class TaskManager:
    def __init__(self, mask_hash_list: List[Tuple[str, str]]):
        self.mask_hash_list = mask_hash_list
        self.pending_attacks: queue.Queue[AttackTask] = queue.Queue()

    def tasks(self) -> Iterator[Union[KeyspaceTask, AttackTask]]:
        task_ix = 0
        while True:
            try:
                yield self.pending_attacks.get_nowait()
            except queue.Empty:
                try:
                    mask, hash_ = self.mask_hash_list[task_ix]
                    task_ix += 1
                    yield KeyspaceTask(mask, hash_type=400, attack_mode=3)
                except IndexError:
                    return

    def process_result(self, task: Union[KeyspaceTask, AttackTask], result: str):
        if isinstance(task, KeyspaceTask):
            hash_ = next(hash_ for mask, hash_ in self.mask_hash_list if mask == task.mask)
            print(f"Keyspace for {task.mask} used for {hash_} is {result}")


task_manager = TaskManager([
    ('?a?a', '$P$5ZDzPE45CigTC6EY4cXbyJSLj/pGee0'),
    ('?a?a?a', '$P$5ZDzPE45CLLhEx/72qt3NehVzwN2Ry/'),
    ('?a?a?a?a', '$H$5ZDzPE45C.e3TjJ2Qi58Aaozha6cs30'),
])


async def execute_task(activity: Activity, task: Union[KeyspaceTask, AttackTask]):
    print("EXECUTE TASK", task)
    batch = await activity.execute_commands(*task.commands())
    try:
        await batch.wait(timeout=30)
    except Exception as e:
        print("EXCEPTION", e)
        # print(batch.events)
        raise
    result = batch.events[-1].stdout.strip()
    task_manager.process_result(task, result)


async def main() -> None:
    async for result in execute_tasks(
        budget=1,
        execute_task=execute_task,
        task_data=task_manager.tasks(),
        payload=PAYLOAD,
        max_workers=2,
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


#     # yield [f"hashcat --keyspace -a 3 -m 400 '?l?l'"]a
#     #   EASY
#     # hash_ = '$P$5ZDzPE45CigTC6EY4cXbyJSLj/pGee0'
#     # mask = '?a?a'
#     #   HARDER
#     # hash_ = '$P$5ZDzPE45CLLhEx/72qt3NehVzwN2Ry/'
#     # mask = '?a?a?a'
#     #   HARD
#     # hash_ = '$H$5ZDzPE45C.e3TjJ2Qi58Aaozha6cs30'
#     # mask = '?a?a?a?a'
#     hash_ = '187ef4436122d1cc2f40dc2b92f0eba0'
#     mask = '?a?a'
#     yield [
#         f"touch /golem/output/ttt.potfile",
#         (
#             f"hashcat -a 3 -m 0 "
#             f"--self-test-disable --potfile-disable "
#             f"-o /golem/output/ttt.potfile "
#             f"'{hash_}' '{mask}' "
#             f"|| true"
#         ),
#         "cat /golem/output/ttt.potfile",
#     ]
