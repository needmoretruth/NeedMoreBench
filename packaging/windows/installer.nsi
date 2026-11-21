; Windows installer of NeedMoreBench: installs for the current user (no administrator rights), adds a Start menu
; entry and an uninstaller. Built by CI:  makensis /DVERSION=<x.y.z> /DSRC=<PyInstaller folder> /DICON=<.ico> /DOUT=<setup.exe> installer.nsi
Unicode true
!include "MUI2.nsh"

Name "NeedMoreBench"
OutFile "${OUT}"
InstallDir "$LOCALAPPDATA\Programs\NeedMoreBench"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_FINISHPAGE_RUN "$INSTDIR\NeedMoreBench.exe"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Korean"

!define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\NeedMoreBench"

Section "Install"
  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\_internal"
  File /r "${SRC}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\NeedMoreBench.lnk" "$INSTDIR\NeedMoreBench.exe"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "NeedMoreBench"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST}" "Publisher" "needmoretruth"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\NeedMoreBench.exe"
  WriteRegStr HKCU "${UNINST}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\NeedMoreBench.lnk"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\NeedMoreBench.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINST}"
SectionEnd
