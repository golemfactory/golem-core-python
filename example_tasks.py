from itertools import count

from golem_api import Payload, commands

PAYLOAD = Payload.from_image_hash("055911c811e56da4d75ffc928361a78ed13077933ffa8320fb1ec2db")

results = {}

def get_tasks():
    for i in count(0):
        yield _get_task(i)

def results_cnt():
    return len(results)

def _get_task(task_data):
    async def execute_task(activity):
        batch = await activity.execute_commands(
            commands.Run("sleep 1"),
            commands.Run(f"echo -n $(({task_data} * 7))"),
        )
        await batch.wait(5)

        result = batch.events[-1].stdout
        results[task_data] = result

        print(f"{task_data} -> {result}")

    return execute_task