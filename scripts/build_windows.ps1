python -m pip install --upgrade pip
python -m pip install .[windows,tray]
python -m pip install pyinstaller
pyinstaller --name WalkieTalkieAgent --noconsole --onefile desktop_agent/walkietalkie_agent/main.py
