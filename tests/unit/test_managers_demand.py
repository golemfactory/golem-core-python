import asyncio

import pytest

from golem.managers import AggregatingDemandManager


async def test_aggregating_demand_manager_should_block_until_proposal_arrives(mocker):
    mocked_golem_node = mocker.Mock()

    queue1: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal1 = mocker.AsyncMock(wraps=queue1.get)

    queue2: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal2 = mocker.AsyncMock(wraps=queue2.get)

    manager = AggregatingDemandManager(
        mocked_golem_node,
        (
            mocked_get_initial_proposal1,
            mocked_get_initial_proposal2,
        ),
    )

    get_task = asyncio.create_task(manager.get_initial_proposal())

    done, _ = await asyncio.wait([get_task], timeout=0.1)
    if done:
        pytest.fail("Somehow some tasks finished too early!")

    await queue1.put("a")

    await asyncio.sleep(0.1)

    assert "a" == await asyncio.wait_for(get_task, timeout=0.1)

    mocked_get_initial_proposal1.mock_calls = [mocker.call()]
    mocked_get_initial_proposal2.mock_calls = [mocker.call()]

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)

    await queue2.put("b")

    assert "b" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)

    mocked_get_initial_proposal1.mock_calls = [mocker.call()]
    mocked_get_initial_proposal2.mock_calls = [mocker.call()]

    await manager.stop()


async def test_aggregating_demand_manager_should_remember_concurrent_proposal_for_the_next_call(
    mocker,
):
    mocked_golem_node = mocker.Mock()

    queue1: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal1 = mocker.AsyncMock(wraps=queue1.get)

    queue2: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal2 = mocker.AsyncMock(wraps=queue2.get)

    manager = AggregatingDemandManager(
        mocked_golem_node,
        (
            mocked_get_initial_proposal1,
            mocked_get_initial_proposal2,
        ),
    )

    await queue1.put("a")
    await queue2.put("b")

    await asyncio.sleep(0.1)

    assert "a" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)
    assert "b" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)

    mocked_get_initial_proposal1.mock_calls = [mocker.call()]
    mocked_get_initial_proposal2.mock_calls = [mocker.call()]

    await queue1.put("a")
    await queue2.put("b")

    await asyncio.sleep(0.1)

    assert "a" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)
    assert "b" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)

    mocked_get_initial_proposal1.mock_calls = [mocker.call(), mocker.call()]
    mocked_get_initial_proposal2.mock_calls = [mocker.call(), mocker.call()]

    await manager.stop()


async def test_aggregating_demand_manager_should_recall_func_if_not_all_are_pending(mocker):
    mocked_golem_node = mocker.Mock()

    queue1: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal1 = mocker.AsyncMock(wraps=queue1.get)

    queue2: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal2 = mocker.AsyncMock(wraps=queue2.get)

    manager = AggregatingDemandManager(
        mocked_golem_node,
        (
            mocked_get_initial_proposal1,
            mocked_get_initial_proposal2,
        ),
    )

    await queue1.put("a")

    await asyncio.sleep(0.1)

    assert "a" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)

    mocked_get_initial_proposal1.mock_calls = [mocker.call()]
    mocked_get_initial_proposal2.mock_calls = [mocker.call()]

    await queue1.put("b")

    await asyncio.sleep(0.1)

    assert "b" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)

    mocked_get_initial_proposal1.mock_calls = [mocker.call(), mocker.call()]
    mocked_get_initial_proposal2.mock_calls = [mocker.call()]

    await manager.stop()


async def test_aggregating_demand_manager_should_keep_completion_order(mocker):
    mocked_golem_node = mocker.Mock()

    queue1: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal1 = mocker.AsyncMock(wraps=queue1.get)

    queue2: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal2 = mocker.AsyncMock(wraps=queue2.get)

    queue3: asyncio.Queue[str] = asyncio.Queue()
    mocked_get_initial_proposal3 = mocker.AsyncMock(wraps=queue3.get)

    manager = AggregatingDemandManager(
        mocked_golem_node,
        (
            mocked_get_initial_proposal1,
            mocked_get_initial_proposal2,
            mocked_get_initial_proposal3,
        ),
    )

    get_task = asyncio.create_task(manager.get_initial_proposal())

    done, _ = await asyncio.wait([get_task], timeout=0.1)
    if done:
        pytest.fail("Somehow some tasks finished too early!")

    await queue3.put("c")

    await asyncio.sleep(0.1)

    await queue2.put("b")

    await asyncio.sleep(0.1)

    await queue1.put("a")

    await asyncio.sleep(0.1)

    assert "c" == await asyncio.wait_for(get_task, timeout=0.1)
    assert "b" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)
    assert "a" == await asyncio.wait_for(manager.get_initial_proposal(), timeout=0.1)

    mocked_get_initial_proposal1.mock_calls = [mocker.call()]
    mocked_get_initial_proposal2.mock_calls = [mocker.call()]
    mocked_get_initial_proposal3.mock_calls = [mocker.call()]
