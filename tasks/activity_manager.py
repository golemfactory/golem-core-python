class ActivityManager:
    def __init__(self, golem, db, *, payload, max_activities):
        self.golem = golem
        self.db = db
        self.payload = payload
        self.max_activities = max_activities

    async def run(self):
        from tasks.create_activities import create_activities
        await create_activities(self.golem, self.db, self.payload, self.max_activities)
