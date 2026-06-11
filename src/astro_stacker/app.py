from PySide6.QtWidgets import QApplication

from astro_stacker.ui.main_window import MainWindow


from PySide6.QtCore import QLibraryInfo

print("PluginsPath:")
print(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))

from PySide6.QtWidgets import QApplication

print("QApplication imported")

def main():
    app = QApplication([])

    window = MainWindow()
    window.show()

    app.exec()


if __name__ == "__main__":
    main()