from __future__ import annotations

from pathlib import Path
import tomllib

from setuptools import find_packages, setup


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
APP = [str(PROJECT_ROOT / "launcher.py")]
with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
    VERSION = str(tomllib.load(stream)["project"]["version"])
OPTIONS = {
    "argv_emulation": False,
    "packages": ["job_mail_desk", "keyring.backends.macOS", "webview"],
    "excludes": ["PyInstaller"],
    "plist": {
        "CFBundleName": "JobMailDesk Core",
        "CFBundleDisplayName": "JobMailDesk Core",
        "CFBundleIdentifier": "io.github.chpeeeeea.jobmaildesk",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
}


setup(
    name="JobMailDesk",
    version=VERSION,
    description="Privacy-first, Markdown-native job email desk.",
    app=APP,
    package_dir={"": str(SOURCE_ROOT)},
    packages=find_packages(str(SOURCE_ROOT)),
    package_data={"job_mail_desk": ["ui/*.html", "ui/*.css", "ui/*.js"]},
    options={"py2app": OPTIONS},
)
