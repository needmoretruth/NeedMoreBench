# Build NeedMoreBench for Windows from the gvsbuild GTK (run from the repository root, GTK unpacked in $Gtk).
#   packaging/windows/build.ps1 -Version <x.y.z> -Gtk C:\gtk
#   -> dist\NeedMoreBench-<version>-windows-x64-setup.exe and dist\NeedMoreBench-<version>-windows-x64.zip
# Steps: PyGObject from the GTK zip, tests, licenses, icons, PyInstaller, smoke, installer, portable zip.
param([string]$Version = "dev", [string]$Gtk = "C:\gtk")
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$env:PATH = "$Gtk\bin;$env:PATH"
$env:XDG_DATA_DIRS = "$Gtk\share"
# Python does not search PATH for the DLLs an extension needs; PyGObject adds this folder itself
$env:PYGI_DLL_PATH = "$Gtk\bin"

python -m pip install --quiet --upgrade pip
python -m pip install --quiet (Get-ChildItem "$Gtk\wheels\*.whl").FullName
python -m pip install --quiet --require-hashes -r packaging\requirements-bundle.txt
python -m pip install --quiet -r packaging\requirements-build.txt

python -m pytest -q -p no:cacheprovider

python packaging\licenses.py --gtk $Gtk --out build\licenses
python packaging\icons.py
# opencode for free models out of the box (Y1): the pinned release, checksum checked, next to the app as opencode\
python packaging\fetch_opencode.py windows-x64 build\opencode
python -m PyInstaller --noconfirm --log-level WARN --distpath dist --workpath build\pyinstaller packaging\needmorebench.spec

# smoke: the built app opens its screens, saves a picture of each and exits with 0 (a windowed app: its log is a file)
New-Item -ItemType Directory -Force smoke | Out-Null
$p = Start-Process -FilePath dist\NeedMoreBench\NeedMoreBench.exe -PassThru -Wait `
  -ArgumentList "--smoke", "`"$PWD\smoke`"", "--record", "tests\data\smoke.nmb.jsonl"
Get-Content smoke\smoke.log -ErrorAction SilentlyContinue
if ($p.ExitCode -ne 0) { throw "smoke failed with exit code $($p.ExitCode)" }

if (-not (Get-Command makensis -ErrorAction SilentlyContinue)) {
  choco install nsis -y --no-progress | Out-Null
  $env:PATH = "${env:ProgramFiles(x86)}\NSIS;$env:PATH"
}
makensis /V2 "/DVERSION=$Version" "/DSRC=$PWD\dist\NeedMoreBench" "/DICON=$PWD\build\icons\needmorebench.ico" `
  "/DOUT=$PWD\dist\NeedMoreBench-$Version-windows-x64-setup.exe" packaging\windows\installer.nsi
Compress-Archive -Path dist\NeedMoreBench -DestinationPath "dist\NeedMoreBench-$Version-windows-x64.zip" -Force
Write-Output "built dist\NeedMoreBench-$Version-windows-x64-setup.exe"
