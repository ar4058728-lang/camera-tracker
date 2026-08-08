import sys, os

# Path otomatis — tidak perlu edit username
path = os.path.expanduser('~/camera-tracker')
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
