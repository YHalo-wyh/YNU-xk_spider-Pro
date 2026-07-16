
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"

Var RemoveUserDataCheckbox
Var RemoveUserDataState

Name "YNU选课助手 Pro"
OutFile "YNU.Pro_v2.6.0_Setup.exe"
InstallDir "$LOCALAPPDATA\YNU选课助手Pro"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YNU选课助手Pro" "UninstallString"
RequestExecutionLevel user

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
UninstPage custom un.RemoveUserDataPage un.RemoveUserDataPageLeave
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Function un.RemoveUserDataPage
    !insertmacro MUI_HEADER_TEXT "个人数据" "选择是否清理账号配置和选课状态"
    nsDialogs::Create 1018
    Pop $0
    ${If} $0 == error
        Abort
    ${EndIf}

    ${NSD_CreateLabel} 0 0 100% 30u "默认会保留登录配置和待选课程状态，方便重新安装后继续使用。安装目录内的运行日志会随程序一起删除。"
    Pop $0
    ${NSD_CreateCheckbox} 0 44u 100% 14u "同时删除个人配置和选课状态"
    Pop $RemoveUserDataCheckbox
    ${NSD_Uncheck} $RemoveUserDataCheckbox

    nsDialogs::Show
FunctionEnd

Function un.RemoveUserDataPageLeave
    ${NSD_GetState} $RemoveUserDataCheckbox $RemoveUserDataState
FunctionEnd

Section "Install"
    ; Clean old runtime files first to avoid mixed Python/dependency DLLs after upgrades.
    ; Keep user data such as xk_spider/config.json and logs intact.
    Delete "$INSTDIR\YNU选课助手Pro.exe"
    Delete "$INSTDIR\Watchdog.exe"
    RMDir /r "$INSTDIR\_internal"

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
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YNU选课助手Pro" "InstallLocation" "$INSTDIR"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\YNU选课助手Pro"
    Delete "$DESKTOP\YNU选课助手Pro.lnk"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\YNU选课助手Pro"

    ; Personal data is retained unless the user explicitly opts in.
    StrCmp $RemoveUserDataState ${BST_CHECKED} 0 keep_user_data
    RMDir /r "$APPDATA\YNU选课助手Pro"
keep_user_data:
SectionEnd
