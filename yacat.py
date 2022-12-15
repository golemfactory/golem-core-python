import aiofiles
import queue
import hashlib
import random
import string

from golem_core import Payload
from golem_core.commands import Run
from golem_core.low import Activity

#   TASKS INTERFACE
PAYLOAD = Payload.from_image_hash("055911c811e56da4d75ffc928361a78ed13077933ffa8320fb1ec2db")

def get_tasks(run_id):
    while True:
        try:
            task = tasks_queue.get_nowait()

            async def execute_task(activity):
                await task.execute(run_id, activity)

            yield execute_task
        except queue.Empty:
            insert_main_tasks(10)

async def results_cnt(run_id):
    try:
        async with aiofiles.open(results_fname(run_id), mode='r') as f:
            return len(await f.readlines())
    except FileNotFoundError:
        return 0


#   INTERNALS
PASSWORD_LENGTH = 3
CHUNK_SIZE = 2 ** 12
tasks_queue = queue.LifoQueue()

def results_fname(run_id):
    return f"_yacat_results_{run_id}"

class MainTask:
    def __init__(self, mask: str, hash_: str, hash_type: int, attack_mode: int):
        self.mask = mask
        self.hash_ = hash_
        self.hash_type = hash_type
        self.attack_mode = attack_mode

    async def execute(self, run_id: str, activity: Activity) -> None:
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
    def __init__(self, mask: str, hash_: str, hash_type: int, attack_mode: int, skip: int, limit: int):
        self.mask = mask
        self.hash_ = hash_
        self.hash_type = hash_type
        self.attack_mode = attack_mode
        self.skip = skip
        self.limit = limit

    async def execute(self, run_id: str, activity: Activity) -> None:
        batch = await activity.execute_commands(*self._commands())
        await batch.wait(timeout=120)
        result = batch.events[-1].stdout
        if result is not None:
            print(f"FOUND {result.strip()} between {self.skip} and {self.limit}")
            async with aiofiles.open(results_fname(run_id), mode='a+') as f:
                await f.write(result)

    def _commands(self):
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

def insert_main_tasks(cnt):
    mask = "".join(["?a" for _ in range(PASSWORD_LENGTH)])
    chars = string.ascii_letters + string.digits + string.punctuation

    for _ in range(cnt):
        password = "".join([random.choice(chars) for i in range(len(mask) // 2)])
        hash_ = hashlib.sha256(password.encode()).hexdigest()
        task = MainTask(mask=mask, hash_=hash_, hash_type=1400, attack_mode=3)
        tasks_queue.put_nowait(task)
