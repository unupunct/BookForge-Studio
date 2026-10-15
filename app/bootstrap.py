"""Application start-up."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .application_state import AppState
from .main_window import MainWindow
from .services.app_paths import user_data_dir
from .services.project_service import NewBookSpec
from .ui import theme


def configure_logging() -> None:
    # Logs never contain manuscript text: only events and error types.
    logging.basicConfig(filename=user_data_dir() / "bookforge.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def install_excepthook(app: QApplication) -> None:
    def hook(exc_type, exc, tb):
        logging.getLogger("bookforge").error("Unhandled %s", exc_type.__name__, exc_info=(exc_type, exc, tb))
        try:
            QMessageBox.critical(None, "Unexpected error",
                                 f"BookForge Studio hit an unexpected problem ({exc_type.__name__}: {exc}).\n\n"
                                 "Your work is protected by autosave. You can keep working, but saving "
                                 "and restarting is recommended.")
        except Exception:
            pass
    sys.excepthook = hook


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        from .selftest import run as selftest
        i = argv.index("--selftest")
        return selftest(argv[i + 1] if i + 1 < len(argv) else "selftest-output")
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("BookForge Studio")
    app.setOrganizationName("BookForgeStudio")
    configure_logging()
    state = AppState()
    theme.apply_theme(app, state.settings_store.data.ui_scale)
    install_excepthook(app)
    window = MainWindow(state)
    window.show()
    args = [a for a in argv[1:] if not a.startswith("-")]
    if args and Path(args[0]).suffix.lower() == ".bookforge":
        window._open_path(Path(args[0]))
    else:
        # Start with an empty book so the window is immediately usable.
        state.new_project(NewBookSpec(title="Untitled Book", profile="custom"))
        state.mark_dirty(False)
        QTimer.singleShot(250, window.check_recovery)
    return app.exec()
