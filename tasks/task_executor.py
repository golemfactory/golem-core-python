class TaskExecutor:
    def __init__(self, golem, db, *, get_tasks, max_concurrent):
        self.golem = golem
        self.db = db
        self.get_tasks = get_tasks
        self.max_concurrent = max_concurrent

    async def run(self):
        from tasks.process_tasks import process_tasks
        await process_tasks(self.golem, self.db, self.get_tasks, self.max_concurrent)
