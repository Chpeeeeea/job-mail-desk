from __future__ import annotations

import logging
import sys


def notify_urgent(count: int) -> None:
    if count <= 0 or sys.platform != "win32":
        return
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except RuntimeError:
        logging.getLogger(__name__).warning("无法播放紧急任务提示音")

