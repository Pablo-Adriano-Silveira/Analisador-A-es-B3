"""Executa trabalho pesado em outra thread para a janela não congelar."""
import queue
import threading
from typing import Any, Callable


def run_in_background(root, work: Callable[[], Any],
                      on_done: Callable[[Any], None],
                      on_error: Callable[[BaseException], None]) -> None:
    q: "queue.Queue" = queue.Queue()

    def target():
        try:
            q.put(("ok", work()))
        except BaseException as exc:  # noqa: BLE001 - repassa qualquer erro para a interface
            q.put(("err", exc))

    threading.Thread(target=target, daemon=True).start()

    def poll():
        try:
            kind, payload = q.get_nowait()
        except queue.Empty:
            root.after(80, poll)
            return
        (on_done if kind == "ok" else on_error)(payload)

    root.after(80, poll)
