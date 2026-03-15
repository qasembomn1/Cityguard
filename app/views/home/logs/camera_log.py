from app.views.home.logs._shared import ActivityLogsWindow


class MainWindow(ActivityLogsWindow):
    def __init__(self) -> None:
        super().__init__("/log/camera")
