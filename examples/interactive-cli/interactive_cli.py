# TODO: Finish this example

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Never, Callable, Optional, Coroutine, cast, List, AsyncGenerator

from asciimatics.effects import Print, Effect
from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import NextScene, InvalidFields
from asciimatics.renderers import FigletText, SpeechBubble
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import Frame, Layout, Label, Text, Button, PopUpDialog, Divider, DropdownList, TextBox
from yarl import URL

from golem_core import GolemNode, Payload
from golem_core.low import Allocation, Demand, Proposal
from yapapi.payload import vm

ASCIIMATICS_SCREEN_UPDATE_INTERVAL = timedelta(seconds=1/20)


@dataclass
class DemoModel:
    golem_node: Optional[GolemNode] = None
    allocation: Optional[Allocation] = None
    demand: Optional[Demand] = None
    proposals: Optional[List[Proposal]] = None


class AsyncFunctionBridge(Effect):
    def __init__(self, screen, async_function, on_done: Callable):
        super().__init__(
            screen=screen,
            start_frame=0,
            stop_frame=0,
            delete_count=None,
        )

        self._async_function = async_function
        self._on_done = on_done
        self._task: Optional[asyncio.Task] = None

    def reset(self):
        if self._task is not None:
            self._task.cancel()

        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._async_function())

    def _update(self, frame_no):
        assert self._task is not None, "Call .reset() first to be able to update AsyncFunctionBridge!"

        if not self._task.done():
            return

        self.scene.remove_effect(self)
        self._on_done(self._task.result())

    @property
    def stop_frame(self):
        return 0

class AsyncGeneratorBridge(Effect):
    def __init__(self, screen, async_function, on_yield: Callable):
        super().__init__(
            screen=screen,
            start_frame=0,
            stop_frame=0,
            delete_count=None,
        )

        self._async_function = async_function
        self._on_yield = on_yield
        self._task: Optional[asyncio.Task] = None
        self._generator: Optional[AsyncGenerator] = None

    def reset(self):
        if self._task is not None:
            self._task.cancel()

        self._generator = self._async_function()

        loop = asyncio.get_event_loop()
        self._task = loop.create_task(anext(self._generator))

    def _update(self, frame_no):
        assert self._task is not None, "Call .reset() first to be able to update AsyncGeneratorBridge!"

        if not self._task.done():
            return

        try:
            self._on_yield(self._task.result())
        except StopAsyncIteration:
            self.scene.remove_effect(self)
        else:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(anext(self._generator))

    @property
    def stop_frame(self):
        return 0


class BusyPopUpDialog(PopUpDialog):
    def __init__(self, screen, text, task: asyncio.Task, callback: Callable, theme="green"):
        self._task = task
        self._callback = callback

        super().__init__(screen, text, buttons=[], on_close=None, has_shadow=False, theme=theme)

    def _update(self, frame_no):
        if self._task.done():
            self._callback(self._task.result())
            self.scene.remove_effect(self)
            return

        super(BusyPopUpDialog, self)._update(frame_no)

    def process_event(self, event):
        return None

    @property
    def frame_update_count(self):
        # As we need to constantly fetch for self._task updates
        return 1

    def reset(self):
        self._task.cancel()
        self.scene.remove_effect(self)


def show_error_pop_up_dialog(frame: Frame, exception: InvalidFields):
    frame.scene.add_effect(PopUpDialog(
        frame.screen,
        "The following fields are invalid:\n\n{}".format(
            '\n'.join(f"- {frame.find_widget(field).label[:-1]}" for field in exception.fields)
        ),
        ["OK"]
    ))


def validate_float(value: str) -> bool:
    try:
        float(value)
    except Exception:
        return False

    return True

def validate_int(value: str) -> bool:
    try:
        int(value)
    except Exception:
        return False

    return True

def on_frame_submit(frame: Frame, message: str, async_function: Callable[[], Coroutine], callback_function: Callable) -> None:
    try:
        frame.save(validate=True)
    except InvalidFields as e:
        show_error_pop_up_dialog(frame, e)
        return

    loop = asyncio.get_event_loop()

    connection_task = loop.create_task(async_function())

    frame.scene.add_effect(
        BusyPopUpDialog(frame.screen, message, connection_task, callback_function),
        reset=False,
    )

class Step0Scene(Scene):
    def __init__(self, screen: Screen, scenes_count: int, model: DemoModel):
        self._model = model

        super().__init__(
            effects=[
                Print(
                    screen,
                    FigletText("Golem Core", font='big'),
                    (screen.height // 2) - 6
                ),
                Print(
                    screen,
                    SpeechBubble(f"Welcome to interactive demo!"),
                    screen.height // 2
                ),
                Print(
                    screen,
                    SpeechBubble(f"In {scenes_count} steps we'll show you full flow of Golem Network interaction."),
                    (screen.height // 2) + 2
                ),
                Print(
                    screen,
                    SpeechBubble("Hit [space] to start!"),
                    (screen.height // 2) + 4
                ),
            ],
            name="step0"
        )

    def process_event(self, event):
        if isinstance(event, KeyboardEvent) and event.key_code == ord(' '):
            raise NextScene('step1')

        return event


class Step1Scene(Scene):
    def __init__(self, screen: Screen, step_count: int, model: DemoModel):
        self._model = model

        self._frame = frame = Frame(
            screen=screen,
            height=10,
            width=(screen.width * 2) // 3,
            can_scroll=False,
            title=f"[1/{step_count}] Creation of Golem Node context",
            reduce_cpu=True,
            name='connection_details',
            data={
                'yagna_api_url': os.environ.get('YAGNA_API_URL', 'http://127.0.0.1:7465'),
                'yagna_app_key': os.environ.get('YAGNA_APPKEY', ''),
            }
        )

        layout = Layout([100])
        frame.add_layout(layout)

        layout.add_widget(Label('Provide basic information for YAGNA daemon connection.'))
        layout.add_widget(Divider(draw_line=False))
        layout.add_widget(Label('Note: UPPERCASE values makes environment variables lookup.'))
        layout.add_widget(Divider(draw_line=False))
        layout.add_widget(Text('YAGNA_API_URL:', 'yagna_api_url', validator=self._validate_yagna_api_url))
        layout.add_widget(Text('YAGNA_APPKEY:', 'yagna_app_key', validator=self._validate_yagna_appkey))
        layout.add_widget(Divider(draw_line=False))
        layout.add_widget(Button('Connect', on_click=partial(
            on_frame_submit,
            frame=frame,
            message='Connecting...',
            async_function=self._connect_to_golem_node,
            callback_function=self._on_connect_to_golem_node_done,
        )))

        frame.fix()

        super().__init__([frame], name="step1")

    @staticmethod
    def _validate_yagna_api_url(value: str) -> bool:
        try:
            URL(value)
        except Exception:
            return False

        return True

    @staticmethod
    def _validate_yagna_appkey(value: str) -> bool:
        return bool(value)

    async def _connect_to_golem_node(self) -> Optional[Exception]:
        self._model.golem_node = golem_node = GolemNode(
            base_url=self._frame.data['yagna_api_url'],
            app_key=self._frame.data['yagna_app_key'],
        )

        await golem_node.start()

        try:
            # FIXME: Use more suitable way to check if connection is possible
            await golem_node.invoices()
        except Exception as e:
            return e

    def _on_connect_to_golem_node_done(self, result_exception: Optional[Exception]):
        if result_exception:
            self.add_effect(PopUpDialog(
                self._frame.screen,
                f"Can't connect to yagna:\n\n{result_exception}",
                ["OK"]
            ))
            return

        raise NextScene('step2')


class Step2Scene(Scene):
    def __init__(self, screen: Screen, step_count: int, model: DemoModel):
        self._model = model

        self._frame = frame = Frame(
            screen=screen,
            height=10,
            width=(screen.width * 2) // 3,
            can_scroll=False,
            title=f"[1/{step_count}] Preparing fund allocation",
            reduce_cpu=True,
            name='connection_details',
            data={
                'funds': '1',
            }
        )

        layout = Layout([100])
        frame.add_layout(layout)

        layout.add_widget(Label(
            'Great! Connection to yagna works, now let\'s declare maximum amount of funds that we want to spend on this demo.',
            height=2,
        ))
        layout.add_widget(Divider(draw_line=False))
        layout.add_widget(Text('Funds to spend:', 'funds', validator=validate_float))
        layout.add_widget(Divider(draw_line=False))
        layout.add_widget(Button('Allocate', on_click=partial(
            on_frame_submit,
            frame=frame,
            message='Allocating...',
            async_function=self._create_allocation,
            callback_function=self._on_create_allocation_result,
        )))

        frame.fix()

        super().__init__([frame], name="step2")

    async def _create_allocation(self) -> Optional[Exception]:
        allocation = await self._model.golem_node.create_allocation(
            float(self._frame.data['funds'])
        )

        self._model.allocation = allocation

        return None

    def _on_create_allocation_result(self, result_exception: Optional[Exception]):
        raise NextScene('step3')


class Step3Scene(Scene):
    def __init__(self, screen: Screen, step_count: int, model: DemoModel):
        self._model = model
        self._frame = frame = Frame(
            screen=screen,
            height=11,
            width=(screen.width * 2) // 3,
            title=f"[3/{step_count}] Creation of demand",
            reduce_cpu = True,
            data={
                'image': 'debian',
                'min_ram': "0.5",
                'min_cpu': "1",
                'min_storage': "2",
            }
        )

        layout = Layout([100])
        frame.add_layout(layout)

        layout.add_widget(Label(
            'Funds are prepared. Now let\'s describe our needs. In this demo, let\'s narrow down our options to running virtual machine with following values.',
            height=2,
        ))
        layout.add_widget(Divider(draw_line=False))
        layout.add_widget(DropdownList(
            label='Linux distro',
            options=(
                ('Debian', 'debian'),
                ('Ubuntu', 'ubuntu'),
                ('Alpine', 'alpine'),
            ),
            name='image',
            fit=True,
        ))
        layout.add_widget(Text('Minimal RAM (GiBs):', 'min_ram', validator=validate_float))
        layout.add_widget(Text('Minimal CPUs:', 'min_cpu', validator=validate_int))
        layout.add_widget(Text('Minimal storage (GiBs):', 'min_storage', validator=validate_float))
        layout.add_widget(Divider(draw_line=False))
        layout.add_widget(Button('Publish', on_click=partial(
            on_frame_submit,
            frame=frame,
            message='Publishing...',
            async_function=self._create_demand,
            callback_function=self._on_create_demand_result,
        )))

        frame.fix()

        super().__init__([frame], name="step3")

    async def _create_demand(self) -> Optional[Exception]:
        payload = await vm.repo(
            image_hash='9a3b5d67b0b27746283cb5f287c13eab1beaa12d92a9f536b747c7ae',
            min_mem_gib=float(self._frame.data['min_ram']),
            min_cpu_threads=int(self._frame.data['min_cpu']),
            min_storage_gib=float(self._frame.data['min_storage']),
        )

        demand = await self._model.golem_node.create_demand(
            payload=cast(Payload, payload),
            allocations=[self._model.allocation]
        )

        self._model.demand = demand

        return None

    def _on_create_demand_result(self, result_exception: Optional[Exception]):
        raise NextScene('scene4')

class Step4Scene(Scene):
    def __init__(self, screen: Screen, step_count: int, model: DemoModel):
        self._model = model
        self._async_generator_bridge_effect = None

        self._frame = frame = Frame(
            screen=screen,
            height=screen.height,
            width=(screen.width * 2) // 3,
            title=f"[4/{step_count}] Gathering proposals",
            reduce_cpu = True,
            on_load=self._on_frame_load,
        )

        layout = Layout([100])
        frame.add_layout(layout)

        layout.add_widget(Label(
            'Great! Your demand was just posted to Golem Network. Now let\'s wait for proposals. They will be displayed realtime on the list below. Go to the next step if you\'ll be satisfied with proposal amount.',
            height=3,
        ))
        layout.add_widget(Divider(draw_line=False))

        self._proposals_summary_label = layout.add_widget(Text(disabled=True))
        self._proposals_summary_label.value = self._get_proposals_summary_label_text()
        self._proposals_summary_label.custom_colour = "label"

        self._proposals_list_label = layout.add_widget(TextBox(
            height=5,
            disabled=True,
        ))
        self._proposals_list_label.custom_colour = "label"

        layout.add_widget(Divider(draw_line=False))
        layout.add_widget(Button('Next', on_click=self._on_next_button_click))

        frame.fix()

        super().__init__([frame], name="scene4")

    def _on_frame_load(self):
        if self._async_generator_bridge_effect is not None:
            return

        self._async_generator_bridge_effect = AsyncGeneratorBridge(self._frame.screen, self._collect_proposals, on_yield=self._on_proposal_yield)
        self.add_effect(self._async_generator_bridge_effect)

    def reset(self, old_scene=None, screen=None):
        if old_scene is not None:
            self._async_generator_bridge_effect = old_scene._async_generator_bridge_effect

        super().reset(old_scene, screen)

    def _get_proposals_summary_label_text(self):
        return 'Proposals collected: {}'.format(
            0 if self._model.proposals is None else len(self._model.proposals)
        )

    def _get_proposals_list_label_text(self):
        if self._model.proposals is None or len(self._model.proposals) == 0:
            return ['No proposals so far...']

        return list(f'#{number:2} {proposal.id:.20}' for number, proposal in enumerate(self._model.proposals, start=1))

    async def _collect_proposals(self):
        count = 0
        async for proposal in self._model.demand.initial_proposals():
            count += 1
            yield proposal

            if 20 <= count:
                break

    def _on_proposal_yield(self, proposal) -> None:
        if self._model.proposals is None:
            self._model.proposals = []

        self._model.proposals.append(proposal)

        self._proposals_summary_label.value = self._get_proposals_summary_label_text()
        self._proposals_list_label.value = self._get_proposals_list_label_text()

    def _on_next_button_click(self):
        if not self._model.proposals:
            return

        self._model.demand.set_no_more_children()
        # TODO: Check if async generator is closed properly

        raise NextScene('step5')

class Step5Scene(Scene):
    def __init__(self, screen: Screen, step_count: int, model: DemoModel):
        self._model = model

        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[5/{step_count}] Negotiating proposals [TODO]",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step5")


class Step6Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[6/{step_count}] Creation of agreement",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step6")


class Step7Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[7/{step_count}] Creation of activity",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step7")


class Step8Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[8/{step_count}] Executing tasks",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step8")


class Step9Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[9/{step_count}] Collecting results",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step9")


class Step10Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[10/{step_count}] Collecting invoices",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step10")


async def amain(screen: Screen) -> Never:
    while True:
        screen.draw_next_frame()

        await asyncio.sleep(ASCIIMATICS_SCREEN_UPDATE_INTERVAL.total_seconds())


def prepare_scenes(screen: Screen, model: DemoModel) -> None:
    scenes = [
        Step0Scene,
        Step1Scene, Step2Scene, Step3Scene, Step4Scene, Step5Scene,
        # Step6Scene, Step7Scene, Step8Scene, Step9Scene, Step10Scene,
    ]
    scenes_count = len(scenes) - 1

    screen.set_scenes([scene(screen, scenes_count, model) for scene in scenes])


def main():
    logging.basicConfig(level=logging.DEBUG, filename='cli.log', filemode='w')

    exception = None
    screen = Screen.open()
    model = DemoModel()

    try:
        prepare_scenes(screen, model)

        asyncio.run(amain(screen), debug=True)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.exception('Fatal error!')
        exception = e
    finally:
        screen.close()

    if exception:
        print(exception)



if __name__ == "__main__":
    main()
