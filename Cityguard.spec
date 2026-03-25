# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT_DIR = Path(SPECPATH).resolve()
RESOURCE_DIR = ROOT_DIR / "app" / "resources"


def _collect_data_files(source_dir: Path, target_root: str) -> list[tuple[str, str]]:
    datas: list[tuple[str, str]] = []
    if not source_dir.exists():
        return datas

    for file_path in source_dir.rglob("*"):
        if not file_path.is_file():
            continue
        relative_parent = file_path.relative_to(source_dir).parent
        target_dir = Path(target_root) / relative_parent
        datas.append((str(file_path), str(target_dir)))
    return datas


datas = _collect_data_files(RESOURCE_DIR, "app/resources")


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'PySide6.QtNetwork',
        'PySide6.QtWebSockets',
        'requests',
        'urllib3',
        'certifi',
        'idna',
        'charset_normalizer',
        'httpx',
        'httpcore',
        'anyio',
        'sniffio',
        'h11',
        # Dynamically imported via importlib.import_module — PyInstaller cannot
        # trace these automatically, so they must be listed explicitly.
        'app.views.home.stream.playback',
        'app.views.home.user.profile',
        'app.views.home.user.users',
        'app.views.home.user.roles',
        'app.views.home.user.department',
        'app.views.home.devices.clients',
        'app.views.home.devices.access_controls',
        'app.views.home.logs.user_log',
        'app.views.home.logs.client_log',
        'app.views.home.logs.camera_log',
        'app.views.home.activation',
        'app.views.home.update',
        'app.views.home.settings',
        'app.views.home.browser',
        'app.views.home.shell',
        'app.views.lpr.search',
        'app.views.lpr.repeated',
        'app.views.lpr.monitor_lpr',
        'app.views.lpr.blacklist',
        'app.views.lpr.whitelist',
        'app.views.lpr.report',
        'app.views.face.search',
        'app.views.face.monitor_face',
        'app.views.face.blacklist',
        'app.views.face.whitelist',
        'app.views.face.report',
        'app.views.face.count_report',
        'app.views.auth.live_view',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Cityguard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
