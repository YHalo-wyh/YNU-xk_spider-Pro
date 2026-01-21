
!include "MUI2.nsh"

Name "YNU选课助手 Pro"
OutFile "YNU选课助手Pro_Setup.exe"
InstallDir "$LOCALAPPDATA\YNU选课助手Pro"
RequestExecutionLevel user

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\YNU选课助手Pro\*.*"
    
    ; 创建快捷方式
    CreateDirectory "$SMPROGRAMS\YNU选课助手Pro"
    CreateShortcut "$SMPROGRAMS\YNU选课助手Pro\YNU选课助手Pro.lnk" "$INSTDIR\YNU选课助手Pro.exe"
    CreateShortcut "$DESKTOP\YNU选课助手Pro.lnk" "$INSTDIR\YNU选课助手Pro.exe"
    
    ; 写入卸载信息（使用 HKCU 而不是 HKLM，不需要管理员权限）
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YNU选课助手Pro" "DisplayName" "YNU选课助手 Pro"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YNU选课助手Pro" "UninstallString" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\YNU选课助手Pro"
    Delete "$DESKTOP\YNU选课助手Pro.lnk"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YNU选课助手Pro"
SectionEnd
