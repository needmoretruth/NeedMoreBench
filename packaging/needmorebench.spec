# PyInstaller build of NeedMoreBench for Windows and macOS (Linux ships as a Flatpak).
#   pyinstaller --noconfirm --distpath <out> --workpath <work> packaging/needmorebench.spec
# GTK, libadwaita and their typelibs come from the build machine (gvsbuild on Windows, Homebrew on macOS);
# PyInstaller's gi hooks copy the libraries, typelibs, the Adwaita icons and GLib schemas next to the app.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent  # noqa: F821  set by PyInstaller
sys.path.insert(0, str(ROOT))
from nmb import __version__  # noqa: E402

datas = [(str(ROOT / "po"), "po"), (str(ROOT / "data" / "icons"), "data/icons"),
         (str(ROOT / "nmb" / "data"), "nmb/data"), (str(ROOT / "nmb" / "ui" / "style.css"), "nmb/ui"),
         (str(ROOT / "LICENSE"), "."), (str(ROOT / "NOTICE"), ".")]
licenses = ROOT / "build" / "licenses"  # written by packaging/licenses.py before this build
if licenses.is_dir():
    datas.append((str(licenses), "licenses"))
datas += copy_metadata("keyring")  # keyring finds its backends through its package metadata
opencode = ROOT / "build" / "opencode"  # written by packaging/fetch_opencode.py: NMB's own server runs it (Y1)
if opencode.is_dir():
    datas.append((str(opencode), "opencode"))  # as data: PyInstaller must not rewrite or strip the program

hidden = collect_submodules("nmb") + collect_submodules("keyring.backends")
if sys.platform == "win32":
    hidden += collect_submodules("win32ctypes") + ["winsound"]  # the sound effects (§5) play through it

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hidden,
    # Pillow is only for building the icons; bundled, its own HarfBuzz stood in for GTK's and GTK failed to load
    excludes=["tkinter", "pytest", "IPython", "matplotlib", "PIL"],
    hooksconfig={"gi": {"icons": ["Adwaita", "hicolor"], "themes": ["Adwaita"], "languages": ["en", "ko"],
                        "module-versions": {"Gtk": "4.0"}}},
)
pyz = PYZ(a.pure)  # noqa: F821
icon = {"win32": str(ROOT / "build" / "icons" / "needmorebench.ico"),  # written by packaging/icons.py
        "darwin": str(ROOT / "build" / "icons" / "needmorebench.icns")}.get(sys.platform)
exe = EXE(  # noqa: F821
    pyz, a.scripts, [], exclude_binaries=True, name="NeedMoreBench", console=False,
    icon=icon if icon and Path(icon).exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="NeedMoreBench")  # noqa: F821
if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll, name="NeedMoreBench.app", icon=icon, bundle_identifier="org.needmorebench.NeedMoreBench",
        version=__version__,
        info_plist={"CFBundleName": "NeedMoreBench", "CFBundleDisplayName": "NeedMoreBench",
                    "CFBundleShortVersionString": __version__, "NSHighResolutionCapable": True,
                    "LSMinimumSystemVersion": "13.0", "NSRequiresAquaSystemAppearance": False},
    )
