import os
import sys
import subprocess

from PySide6.QtCore import QDir, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)


class FileBrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide File Browser")
        self.resize(1000, 650)

        self.model = QFileSystemModel()
        self.model.setRootPath(QDir.rootPath())
        self.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(QDir.homePath()))
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.doubleClicked.connect(self.on_double_click)

        # hide some columns if you want
        # 0 = name, 1 = size, 2 = type, 3 = modified
        self.tree.setColumnWidth(0, 350)
        self.tree.setColumnWidth(1, 120)
        self.tree.setColumnWidth(2, 150)
        self.tree.setColumnWidth(3, 180)

        self.path_edit = QLineEdit()
        self.path_edit.setText(QDir.homePath())
        self.path_edit.returnPressed.connect(self.go_to_path)

        self.status_label = QLabel("Ready")

        self.btn_home = QPushButton("Home")
        self.btn_up = QPushButton("Up")
        self.btn_open = QPushButton("Open")
        self.btn_refresh = QPushButton("Refresh")

        self.btn_home.clicked.connect(self.go_home)
        self.btn_up.clicked.connect(self.go_up)
        self.btn_open.clicked.connect(self.open_selected)
        self.btn_refresh.clicked.connect(self.refresh_view)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.btn_home)
        top_bar.addWidget(self.btn_up)
        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.btn_refresh)
        top_bar.addWidget(self.path_edit)

        layout = QVBoxLayout()
        layout.addLayout(top_bar)
        layout.addWidget(self.tree)
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def current_index(self):
        index = self.tree.currentIndex()
        if not index.isValid():
            return self.tree.rootIndex()
        return index

    def current_path(self):
        index = self.current_index()
        return self.model.filePath(index)

    def set_root_path(self, path: str):
        if not os.path.exists(path):
            QMessageBox.warning(self, "Path not found", f"Path does not exist:\n{path}")
            return

        index = self.model.index(path)
        self.tree.setRootIndex(index)
        self.path_edit.setText(path)
        self.status_label.setText(f"Opened: {path}")

    def go_home(self):
        self.set_root_path(QDir.homePath())

    def go_up(self):
        current_root = self.model.filePath(self.tree.rootIndex())
        parent = os.path.dirname(current_root.rstrip("/"))
        if not parent:
            parent = "/"
        self.set_root_path(parent)

    def go_to_path(self):
        path = self.path_edit.text().strip()
        self.set_root_path(path)

    def refresh_view(self):
        current = self.model.filePath(self.tree.rootIndex())
        self.model.setRootPath("")   # force refresh trick
        self.model.setRootPath(QDir.rootPath())
        self.set_root_path(current)

    def on_double_click(self, index):
        path = self.model.filePath(index)

        if os.path.isdir(path):
            self.set_root_path(path)
        else:
            self.open_file(path)

    def open_selected(self):
        path = self.current_path()

        if os.path.isdir(path):
            self.set_root_path(path)
        else:
            self.open_file(path)

    def open_file(self, path: str):
        try:
            subprocess.Popen(["xdg-open", path])
            self.status_label.setText(f"Opened file: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open file:\n{e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileBrowserWindow()
    window.show()
    sys.exit(app.exec())