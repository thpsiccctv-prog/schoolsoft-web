"""Compatibility entry point for WSGI servers expecting app:app or wsgi:application (Render default)."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")

from schoolsoft.wsgi import application as app

application = app
