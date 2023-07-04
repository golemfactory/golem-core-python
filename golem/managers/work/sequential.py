import logging
from typing import List

from golem.managers.base import (
    DoWorkCallable,
    Work,
    WorkManager,
    WorkManagerPluginsMixin,
    WorkResult,
)
from golem.node import GolemNode

logger = logging.getLogger(__name__)


class SequentialWorkManager(WorkManagerPluginsMixin, WorkManager):
    def __init__(self, golem: GolemNode, do_work: DoWorkCallable, *args, **kwargs):
        self._do_work = do_work

        super().__init__(*args, **kwargs)

    async def do_work(self, work: Work) -> WorkResult:
        result = await self._do_work_with_plugins(self._do_work, work)

        logger.info(f"Work `{work}` completed")

        return result

    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        logger.debug(f"Running work sequence `{work_list}`...")

        results = []

        for i, work in enumerate(work_list):
            logger.debug(f"Doing work sequence #{i}...")

            results.append(await self.do_work(work))

            logger.debug(f"Doing work sequence #{i} done")

        logger.debug(f"Running work sequence `{work_list}` done")

        return results
