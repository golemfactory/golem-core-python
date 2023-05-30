import logging
from functools import partial
from typing import List

from golem_core.core.golem_node.golem_node import GolemNode
from golem_core.managers.base import DoWorkCallable, Work, WorkResult

logger = logging.getLogger(__name__)


class SequentialWorkManager:
    def __init__(self, golem: GolemNode, do_work: DoWorkCallable):
        self._do_work = do_work

    def _apply_work_decorators(self, do_work: DoWorkCallable, work: Work) -> DoWorkCallable:
        logger.debug(f"Applying decorators on `{work}`...")

        if not hasattr(work, "_work_decorators"):
            return do_work

        result = do_work
        for dec in work._work_decorators:
            result = partial(dec, result)

        logger.debug(f"Applying decorators on `{work}` done")

        return result

    async def do_work(self, work: Work) -> WorkResult:
        logger.debug("Calling `do_work`...")

        decorated_do_work = self._apply_work_decorators(self._do_work, work)

        result = await decorated_do_work(work)

        logger.debug(f"Calling `do_work` done with `{result}`")

        return result

    async def do_work_list(self, work_list: List[Work]) -> List[WorkResult]:
        logger.debug("Doing work sequence...")

        results = []

        for i, work in enumerate(work_list):
            logger.debug(f"Doing work sequence #{i}...")

            results.append(await self.do_work(work))

            logger.debug(f"Doing work sequence #{i} done")

        logger.debug(f"Doing work sequence done with `{results}`")

        return results
