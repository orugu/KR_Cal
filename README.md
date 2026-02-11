krCalendar — Windows system tray calendar (skeleton)

Structure created under `src/lib` with a tray app skeleton and holiday provider.

Quick start:

1. Create and activate a virtualenv (Windows PowerShell example):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Run the app (tray icon will appear):

```powershell
python -m src.main
```

Notes / next steps:
- The `src/lib/tray.py` is a minimal skeleton. It prints a text calendar to the console when "Show Calendar" is selected.
- `src/lib/holidays_provider.py` uses `holidays.KR(years=...)` to fetch Korean public holidays.
- Next work: render a GUI popup or native toast for the calendar, color Saturdays/Sundays and holidays, optionally fetch official government data via `requests` if you have an API key.
