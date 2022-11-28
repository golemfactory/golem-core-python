import aiopg
import asyncio

class DB:
    def __init__(self, dsn):
        self._dsn = dsn
        self._schema = "tasks"
        self._pool = None

    def execute(self, sql, *args, **kwargs):
        asyncio.create_task(self.aexecute(sql, *args, **kwargs))

    async def aexecute(self, sql, *args, **kwargs):
        return await self._execute(sql, False, args, kwargs)

    async def select(self, sql, *args, **kwargs):
        return await self._execute(sql, True, args, kwargs)

    async def _execute(self, sql, return_result, args, kwargs):
        pool = await self._get_pool()
        with (await pool.cursor()) as cur:
            await cur.execute(sql, *args, **kwargs)
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
            self._pool.terminate()
            await self._pool.wait_closed()
