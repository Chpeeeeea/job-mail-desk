from __future__ import annotations

from setuptools import find_packages, setup


APP = ["launcher.py"]
OPTIONS = {
    "argv_emulation": False,
    "packages": ["job_mail_desk", "keyring.backends.macOS", "webview"],
    "plist": {
        "CFBundleName": "JobMailDesk Core",
        "CFBundleDisplayName": "JobMailDesk Core",
        "CFBundleIdentifier": "io.github.chpeeeeea.jobmaildesk",
        "CFBundleShortVersionString": "0.3.0",
        "CFBundleVersion": "0.3.0",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
}


setup(
    name="JobMailDesk",
    version="0.3.0",
    description="Privacy-first, Markdown-native job email desk.",
    app=APP,
    package_dir={"": "src"},
    packages=find_packages("src"),
    package_data={"job_mail_desk": ["ui/*.html", "ui/*.css", "ui/*.js"]},
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
