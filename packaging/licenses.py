"""Collect the license texts of everything the Windows or macOS app carries, and where each source comes from.

    python packaging/licenses.py --gtk C:/gtk --out build/licenses     # Windows: the gvsbuild GTK folder
    python packaging/licenses.py --brew --out build/licenses           # macOS: the Homebrew GTK

Writes <out>/<package>/<license files>, <out>/THIRD-PARTY.md (every package, version, license, source) and
<out>/SOURCES.md (the release-notes block: exact source archives of the LGPL libraries the app links).
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GVSBUILD = "2026.10.0"
LICENSE_NAMES = re.compile(r"^(COPYING|LICEN[CS]E|COPYRIGHT|NOTICE|AUTHORS\.LGPL)", re.I)
# GNOME modules on download.gnome.org: pkg-config name -> module
GNOME = {"glib-2.0": "glib", "gtk4": "gtk", "libadwaita-1": "libadwaita", "pango": "pango", "gdk-pixbuf-2.0": "gdk-pixbuf",
         "gobject-introspection-1.0": "gobject-introspection", "librsvg-2.0": "librsvg", "json-glib-1.0": "json-glib",
         "graphene-1.0": "graphene", "pygobject-3.0": "pygobject", "libsecret-1": "libsecret"}
LGPL = ("glib", "gtk", "libadwaita", "pango", "gdk-pixbuf", "gobject-introspection", "librsvg", "pygobject", "pycairo",
        "cairo", "fribidi", "gettext", "libintl", "gstreamer", "gst-plugins-base", "libsecret", "json-glib")


def exists(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "needmorebench-build"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except OSError:
        return False


def gnome_url(module: str, version: str) -> str:
    """The exact tarball when it answers, else the version's folder (which holds it)."""
    series = ".".join(version.split(".")[:2])
    folder = f"https://download.gnome.org/sources/{module}/{series}/"
    for ext in ("tar.xz", "tar.gz"):
        url = f"{folder}{module}-{version}.{ext}"
        if exists(url):
            return url
    return folder


def gvsbuild_archive(name: str) -> tuple[str, str] | None:
    """(version, exact source archive) from gvsbuild's recipe of this project, when it has one."""
    url = f"https://raw.githubusercontent.com/wingtk/gvsbuild/{GVSBUILD}/gvsbuild/projects/{name}.py"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "needmorebench-build"}), timeout=30) as r:
            text = r.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    v, u = re.search(r'\bversion="([^"]+)"', text), re.search(r'\barchive_url="([^"]+)"', text)
    if not (v and u):
        return None
    parts = (v.group(1).split(".") + ["", "", ""])[:3]
    return v.group(1), u.group(1).format(version=v.group(1), major=parts[0], minor=parts[1], micro=parts[2])


def pypi_sdist(name: str, version: str) -> str:
    """The exact source archive of a Python package on PyPI, else its release page."""
    try:
        req = urllib.request.Request(f"https://pypi.org/pypi/{name}/{version}/json", headers={"User-Agent": "needmorebench-build"})
        with urllib.request.urlopen(req, timeout=30) as r:
            urls = json.load(r).get("urls", [])
        return next(u["url"] for u in urls if u.get("packagetype") == "sdist")
    except (OSError, ValueError, StopIteration):
        return f"https://pypi.org/project/{name}/{version}/#files"


def copy_licenses(files: list[Path], dest: Path) -> list[str]:
    out = []
    for f in files:
        if f.is_file():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest / f.name)
            out.append(f.name)
    return out


def from_gvsbuild(prefix: Path, out: Path) -> list[dict]:
    rows = []
    versions = {}
    for pc in (prefix / "lib" / "pkgconfig").glob("*.pc"):
        m = re.search(r"^Version:\s*(\S+)", pc.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            versions[pc.stem] = m.group(1)
    recipes = f"https://github.com/wingtk/gvsbuild/tree/{GVSBUILD}/gvsbuild/projects"
    for doc in sorted((prefix / "share" / "doc").glob("*")):
        files = [f for f in doc.rglob("*") if LICENSE_NAMES.match(f.name)]
        got = copy_licenses(files, out / doc.name)
        if got:
            pc = next((p for p in versions if p.split("-")[0] == doc.name or p == doc.name), "")
            rows.append({"name": doc.name, "version": versions.get(pc, ""), "files": got, "source": recipes})
    for pc, module in GNOME.items():
        if pc in versions:
            row = next((r for r in rows if r["name"] in (module, pc, pc.split("-")[0])), None)
            url = gnome_url(module, versions[pc])
            if row is None:
                rows.append({"name": module, "version": versions[pc], "files": [], "source": url})
            else:
                row["version"], row["source"] = versions[pc], url
    for row in rows:  # the other LGPL libraries: the exact archive gvsbuild built them from
        if row["source"] == recipes and any(row["name"].lower().startswith(x) for x in LGPL):
            found = gvsbuild_archive(row["name"])
            if found:
                row["version"], row["source"] = found
    rows.append({"name": "gvsbuild (build recipes with the exact source of every library above)", "version": GVSBUILD,
                 "files": [], "source": f"https://github.com/wingtk/gvsbuild/archive/refs/tags/{GVSBUILD}.tar.gz"})
    return rows


def from_brew(out: Path) -> list[dict]:
    names = subprocess.run(["brew", "deps", "--installed", "--union", "libadwaita", "pygobject3"], check=True,
                           capture_output=True, text=True).stdout.split() + ["libadwaita", "pygobject3"]
    info = json.loads(subprocess.run(["brew", "info", "--json=v2", *names], check=True, capture_output=True, text=True).stdout)
    cellar = Path(subprocess.run(["brew", "--cellar"], check=True, capture_output=True, text=True).stdout.strip())
    rows = []
    for f in info["formulae"]:
        version = (f.get("installed") or [{}])[0].get("version") or f["versions"]["stable"]
        keg = cellar / f["name"] / version
        files = [p for p in keg.glob("*") if LICENSE_NAMES.match(p.name)]
        files += [p for p in (keg / "share" / "doc").rglob("*") if LICENSE_NAMES.match(p.name)] if (keg / "share" / "doc").is_dir() else []
        rows.append({"name": f["name"], "version": version, "license": f.get("license") or "",
                     "files": copy_licenses(files, out / f["name"]), "source": f["urls"]["stable"]["url"]})
    return rows


def python_packages(out: Path) -> list[dict]:
    wanted = {re.split(r"[=;\s]", line.strip())[0].lower() for line in (ROOT / "packaging" / "requirements-bundle.txt")
              .read_text(encoding="utf-8").splitlines() if re.match(r"^[A-Za-z]", line)}
    wanted |= {"pygobject", "pycairo"}
    rows = []
    for dist in md.distributions():
        name = (dist.metadata["Name"] or "").lower().replace("_", "-")
        if name not in wanted and name.replace("-", ".") not in wanted or any(r["name"] == name for r in rows):
            continue  # the first copy on the path is the one the app imports
        files = [Path(str(dist.locate_file(f))) for f in dist.files or [] if LICENSE_NAMES.match(Path(str(f)).name)
                 or "licenses" in Path(str(f)).parts]
        lic = dist.metadata.get("License-Expression") or (dist.metadata.get("License") or "").splitlines()[0:1]
        rows.append({"name": name, "version": dist.version, "license": lic if isinstance(lic, str) else "".join(lic),
                     "files": copy_licenses(files, out / f"python-{name}"),
                     "source": pypi_sdist(name, dist.version)})
    return rows


def write(rows: list[dict], out: Path) -> None:
    lines = ["# Third-party software in this app", "",
             "Each package's license text is in the folder of the same name next to this file.", "",
             "| Package | Version | License | Source |", "|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["name"].lower()):
        lines.append(f"| {r['name']} | {r['version']} | {r.get('license', '')} | {r['source']} |")
    (out / "THIRD-PARTY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    lgpl = [r for r in rows if any(r["name"].lower().startswith(x) for x in LGPL)]
    src = ["Libraries under the GNU LGPL in this download, and their exact sources:", ""]
    src += [f"- {r['name']} {r['version']}: {r['source']}" for r in sorted(lgpl, key=lambda r: r["name"].lower())]
    (out / "SOURCES.md").write_text("\n".join(src) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gtk", type=Path)
    ap.add_argument("--brew", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "licenses")
    a = ap.parse_args()
    shutil.rmtree(a.out, ignore_errors=True)
    a.out.mkdir(parents=True)
    rows = from_gvsbuild(a.gtk, a.out) if a.gtk else from_brew(a.out) if a.brew else []
    py = python_packages(a.out)
    names = {r["name"] for r in py}  # the installed Python package wins over the GTK build's copy of its docs
    rows = [r for r in rows if r["name"] not in names] + py
    write(rows, a.out)
    print(f"{len(rows)} packages, licenses in {a.out}")


if __name__ == "__main__":
    main()
