class NewResourceManager:
    def __init__(self, golem, db):
        self.golem = golem
        self.db = db

    async def run(self):
        from tasks.save_new_objects import save_new_objects
        await save_new_objects(self.golem, self.db)
