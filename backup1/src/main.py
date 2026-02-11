"""Entrypoint for the krCalendar tray application.
Run: python -m src.main
"""
import time
import datetime
from src.lib.tray import TrayApp


def main():
    app = TrayApp(years=[datetime.datetime.now().year])
    app.start()
    try:
        # Run the Tk mainloop on the main thread so the popup works correctly
        if hasattr(app, 'popup') and app.popup is not None:
            app.popup.root.mainloop()
        else:
            # fallback: keep alive
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        app.stop()


if __name__ == '__main__':
    main()
