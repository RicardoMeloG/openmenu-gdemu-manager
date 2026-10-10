"""Run original blocking services off the GUI thread while preserving caller API."""
from contextvars import copy_context
from PySide6.QtCore import QEventLoop, QThread, Qt


class ServiceCall(QThread):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.callback=callback
        self.context=copy_context()
        self.result=None
        self.failure=None

    def run(self):
        try:
            self.result=self.context.run(self.callback)
        except Exception as exc:
            self.failure=exc


def invoke_service(callback,parent):
    """Caller keeps busy guards until finished; GUI events keep being processed."""
    worker=ServiceCall(callback,parent)
    loop=QEventLoop(parent)
    worker.finished.connect(loop.quit,Qt.ConnectionType.QueuedConnection)
    worker.start()
    loop.exec()
    worker.wait()
    result,failure=worker.result,worker.failure
    worker.deleteLater()
    loop.deleteLater()
    if failure is not None:
        raise failure
    return result
