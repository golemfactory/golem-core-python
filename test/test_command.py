import pytest

from golem_api.commands import Run

list_c = ["echo", "foo"]
str_c = "echo foo"

sh = ("/bin/sh", "-c", "echo foo")
bash = ("/bin/bash", "-c", "echo foo")
no_shell = ("echo", "foo")


@pytest.mark.parametrize("command, kwargs, full_command", (
    (list_c, {}, no_shell),
    (list_c, {"shell": True}, sh),
    (list_c, {"shell": "True", "shell_cmd": "/bin/bash"}, bash),
    (list_c, {"shell_cmd": "/bin/bash"}, no_shell),
    (str_c, {}, sh),
    (str_c, {"shell": True}, sh),
    (str_c, {"shell": "True", "shell_cmd": "/bin/bash"}, bash),
    (str_c, {"shell_cmd": "/bin/bash"}, bash),

    ("/bin/sh -c 'echo foo'", {}, ["/bin/sh", "-c", "/bin/sh -c 'echo foo'"]),
))
def test_correct(command, kwargs, full_command):
    entry_point, *args = full_command
    run = Run(command, **kwargs)
    assert run.entry_point == entry_point
    assert run.args == args


@pytest.mark.parametrize("command, kwargs", (
    (["echo foo", "bar"], {}),
    ('"echo foo" bar', {"shell": False}),
))
def test_invalid(command, kwargs):
    with pytest.raises(ValueError):
        Run(command, **kwargs)
