from golem_core.core.golem_node import GolemNode


def test_different_app_session_id() -> None:
    assert GolemNode().app_session_id != GolemNode().app_session_id
