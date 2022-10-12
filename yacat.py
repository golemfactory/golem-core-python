import asyncio
from typing import List

from golem_api import execute_tasks, Payload
from golem_api.commands import Run
from golem_api.low import Activity

PAYLOAD = Payload.from_image_hash("055911c811e56da4d75ffc928361a78ed13077933ffa8320fb1ec2db")


async def execute_task(activity: Activity, commands: List[str]):
    print("START")
    run_commands = [Run(command) for command in commands]
    batch = await activity.execute_commands(*run_commands)
    try:
        await batch.wait(timeout=300)
    finally:
        for event in batch.events:
            print(event)
    result = batch.events[-1].stdout
    return result


def get_tasks():
    # yield [f"hashcat --keyspace -a 3 -m 400 '?l?l'"]a
    #   EASY
    # hash_ = '$P$5ZDzPE45CigTC6EY4cXbyJSLj/pGee0'
    # mask = '?a?a'
    #   HARDER
    # hash_ = '$P$5ZDzPE45CLLhEx/72qt3NehVzwN2Ry/'
    # mask = '?a?a?a'
    #   HARD
    # hash_ = '$H$5ZDzPE45C.e3TjJ2Qi58Aaozha6cs30'
    # mask = '?a?a?a?a'
    hash_ = '187ef4436122d1cc2f40dc2b92f0eba0'
    mask = '?a?a'

    yield [
        f"touch /golem/output/ttt.potfile",
        (
            f"hashcat -a 3 -m 0 "
            f"--self-test-disable --potfile-disable "
            f"-o /golem/output/ttt.potfile "
            f"'{hash_}' '{mask}' "
            f"|| true"
        ),
        "cat /golem/output/ttt.potfile",
    ]


async def main() -> None:
    async for result in execute_tasks(
        budget=1,
        execute_task=execute_task,
        task_data=get_tasks(),
        payload=PAYLOAD,
        max_workers=2,
    ):
        print(f"GOT RESULT {result}")

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
