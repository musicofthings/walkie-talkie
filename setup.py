from setuptools import setup

APP = ['desktop_agent/walkietalkie_agent/main.py']
OPTIONS = {
    'argv_emulation': False,
    'plist': {'CFBundleName': 'WalkieTalkieAgent'},
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
