import asyncio
import logging
import os
from datetime import timedelta
from typing import Never, Callable, Optional

from asciimatics.effects import Print, Effect
from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import NextScene, InvalidFields
from asciimatics.renderers import FigletText, SpeechBubble
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import Frame, Layout, Label, Text, Button, PopUpDialog, Divider
from yarl import URL

from golem_core import GolemNode

ASCIIMATICS_SCREEN_UPDATE_INTERVAL = timedelta(seconds=1/20)


class BusyPopUpDialog(PopUpDialog):
    def __init__(self, screen, text, task: asyncio.Task, callback: Callable, theme="green"):
        super().__init__(screen, text, buttons=[], on_close=None, has_shadow=False, theme=theme)

        self._task = task
        self._callback = callback

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




class Step0Scene(Scene):
    def __init__(self, screen: Screen, scenes_count: int):
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
    def __init__(self, screen: Screen, step_count: int):
        self._connection_task = None

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
        layout.add_widget(Button('Connect', self._on_connect_button_click))

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

    def _on_connect_button_click(self):
        try:
            self._frame.save(validate=True)
        except InvalidFields as e:
            self.add_effect(PopUpDialog(
                self._frame.screen,
                "The following fields are invalid:\n\n{}".format(
                    '\n'.join(f"- {self._frame.find_widget(field).label[:-1]}" for field in e.fields)
                ),
                ["OK"]
            ))

            return

        loop = asyncio.get_event_loop()

        connection_task = loop.create_task(self._create_golem_node())

        self.add_effect(
            BusyPopUpDialog(self._frame.screen, "Connecting...", connection_task, self._on_connect_result),
            reset=False,
        )

    async def _create_golem_node(self) -> Optional[Exception]:
        self._frame.screen._golem_node = golem_node = GolemNode(
            base_url=self._frame.data['yagna_api_url'],
            app_key=self._frame.data['yagna_app_key'],
        )

        await golem_node.start()

        try:
            # FIXME: Use more suitable way to check if connection is possible
            await golem_node.invoices()
        except Exception as e:
            return e


    def _on_connect_result(self, result_exception: Optional[Exception]):
        if result_exception:
            self.add_effect(PopUpDialog(
                self._frame.screen,
                f"Can't connect to yagna:\n\n{result_exception}",
                ["OK"]
            ))
            return

        raise NextScene('step2')


class Step2Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[2/{step_count}] Preparing fund allocation",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step2")


class Step3Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[3/{step_count}] Creation of demand",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step3")


class Step4Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[4/{step_count}] Gathering proposals",
                reduce_cpu = True,
            ),
        ]

        super().__init__(effects, name="step4")


class Step5Scene(Scene):
    def __init__(self, screen: Screen, step_count: int):
        effects = [
            Frame(
                screen=screen,
                height=screen.height,
                width=screen.width,
                title=f"[5/{step_count}] Negotiating proposals",
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


def prepare_scenes(screen: Screen) -> None:
    scenes = [
        Step0Scene,
        Step1Scene, Step2Scene, Step3Scene, Step4Scene, Step5Scene,
        Step6Scene, Step7Scene, Step8Scene, Step9Scene, Step10Scene,
    ]
    scenes_count = len(scenes) - 1

    screen.set_scenes([scene(screen, scenes_count) for scene in scenes])


def main():
    logging.basicConfig(level=logging.DEBUG, filename='dupa.log', filemode='w')

    exception = None
    screen = Screen.open()
    screen._golem_node = None

    try:
        prepare_scenes(screen)

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
