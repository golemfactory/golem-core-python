import aiopg
import asyncio
from uuid import uuid4

class DB:
    def __init__(self, dsn, run_id):
        self._dsn = dsn
        self._run_id = run_id if run_id else uuid4().hex
        self._schema = "tasks"
        self._pool = None

    @property
    def run_id(self):
        return self._run_id

    @property
    def app_session_id(self):
        #   NOTE: changing this prefix without database cleanup might
        #         lead to weird errors
        return 'task_runner_' + self.run_id

    async def init_run(self):
        await self.aexecute(
            "INSERT INTO run (id, app_session_id) VALUES (%(run_id)s, %(app_session_id)s) ON CONFLICT DO NOTHING"
        )

    ########################
    #   HIGH LEVEL INTERFACE
    async def close_activity(self, activity, reason):
        await self.db.aexecute("""
            UPDATE  activity
            SET     (status, stop_reason) = ('STOPPING', %(reason)s)
            WHERE   id = %(activity_id)s
                AND status IN ('NEW', 'READY')
        """, {"activity_id": activity.id, "reason": reason})

        async def stop():
            await activity.parent.close_all()
            await self.db.aexecute(
                "UPDATE activity SET status = 'STOPPED' WHERE id = %(activity_id)s",
                {"activity_id": activity.id})

        asyncio.create_task(stop())

    #######################
    #   LOW-LEVEL INTERFACE
    def execute(self, sql, kwargs={}):
        asyncio.create_task(self.aexecute(sql, kwargs))

    async def aexecute(self, sql, kwargs={}):
        return await self._execute(sql, False, kwargs)

    async def select(self, sql, kwargs={}):
        return await self._execute(sql, True, kwargs)

    async def _execute(self, sql, return_result, kwargs):
        kwargs = kwargs.copy()
        kwargs["run_id"] = self.run_id
        kwargs["app_session_id"] = self.app_session_id
        pool = await self._get_pool()
        with (await pool.cursor()) as cur:
            await cur.execute(sql, kwargs)
            if return_result:
                return await cur.fetchall()

    async def _get_pool(self):
        if self._pool is None:
            self._pool = await aiopg.create_pool(
                self._dsn,
                options=f'-c search_path="{self._schema}"'
            )
        return self._pool

    async def aclose(self):
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
