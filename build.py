"""
打包为独立exe + 创建安装包
"""
import os
import sys
import shutil
import subprocess

def check_and_install(package):
    """检查并安装包"""
    try:
        __import__(package)
        return True
    except ImportError:
        print(f"[*] 安装 {package}...")
        subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
        return True

def build_exe():
    """打包为exe"""
    print("\n" + "=" * 50)
    print("步骤 1: 打包为 EXE")
    print("=" * 50)
    
    check_and_install("pyinstaller")
    
    # 清理旧文件
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
    
    for f in os.listdir("."):
        if f.endswith(".spec"):
            os.remove(f)
    
    # PyInstaller 参数 - 打包所有依赖
    args = [
        "run_gui.py",
        "--name=YNU选课助手Pro",
        "--onedir",            # 打包到一个目录（比onefile快且稳定）
        "--windowed",          # 无控制台
        "--noconfirm",
        "--clean",
        # 数据文件
        "--add-data=xk_spider;xk_spider",
        # 收集所有依赖
        "--collect-all=ddddocr",
        "--collect-all=onnxruntime",
        "--collect-all=certifi",
        # 隐藏导入
        "--hidden-import=PyQt5.sip",
        "--hidden-import=PIL._tkinter_finder",
        "--hidden-import=certifi",
    ]
    
    if os.path.exists("icon.ico"):
        args.append("--icon=icon.ico")
    
    print("[*] 正在打包，请稍候（可能需要几分钟）...")
    
    from PyInstaller.__main__ import run
    run(args)
    
    if os.path.exists("dist/YNU选课助手Pro"):
        print("[OK] EXE 打包成功！")
        return True
    else:
        print("[ERROR] 打包失败")
        return False

def create_installer():
    """创建安装包（使用 NSIS 或简单的自解压包）"""
    print("\n" + "=" * 50)
    print("步骤 2: 创建安装包")
    print("=" * 50)
    
    dist_dir = "dist/YNU选课助手Pro"
    if not os.path.exists(dist_dir):
        print("[ERROR] 未找到打包目录")
        return False
    
    # 创建 NSIS 安装脚本
    nsis_script = """
!include "MUI2.nsh"

Name "YNU选课助手 Pro"
OutFile "YNU选课助手Pro_Setup.exe"
InstallDir "$PROGRAMFILES\\YNU选课助手Pro"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\\YNU选课助手Pro\\*.*"
    
    ; 创建快捷方式
    CreateDirectory "$SMPROGRAMS\\YNU选课助手Pro"
    CreateShortcut "$SMPROGRAMS\\YNU选课助手Pro\\YNU选课助手Pro.lnk" "$INSTDIR\\YNU选课助手Pro.exe"
    CreateShortcut "$DESKTOP\\YNU选课助手Pro.lnk" "$INSTDIR\\YNU选课助手Pro.exe"
    
    ; 写入卸载信息
    WriteUninstaller "$INSTDIR\\Uninstall.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\YNU选课助手Pro" "DisplayName" "YNU选课助手 Pro"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\YNU选课助手Pro" "UninstallString" "$INSTDIR\\Uninstall.exe"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\\YNU选课助手Pro"
    Delete "$DESKTOP\\YNU选课助手Pro.lnk"
    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\YNU选课助手Pro"
SectionEnd
"""
    
    # 保存 NSIS 脚本 (使用 UTF-8 BOM 编码以支持中文)
    with open("installer.nsi", "w", encoding="utf-8-sig") as f:
        f.write(nsis_script)
    
    # 检查是否安装了 NSIS
    nsis_path = None
    possible_paths = [
        r"D:\NSIS\makensis.exe",
        r"C:\Program Files (x86)\NSIS\makensis.exe",
        r"C:\Program Files\NSIS\makensis.exe",
    ]
    for p in possible_paths:
        if os.path.exists(p):
            nsis_path = p
            break
    
    if nsis_path:
        print("[*] 使用 NSIS 创建安装包...")
        try:
            subprocess.run([nsis_path, "installer.nsi"], check=True)
            if os.path.exists("YNU选课助手Pro_Setup.exe"):
                shutil.move("YNU选课助手Pro_Setup.exe", "dist/YNU选课助手Pro_Setup.exe")
                print("[OK] 安装包创建成功: dist/YNU选课助手Pro_Setup.exe")
                return True
        except Exception as e:
            print(f"[WARN] NSIS 打包失败: {e}")
    
    # 如果没有 NSIS，创建 ZIP 便携版
    print("[*] 创建 ZIP 便携版...")
    shutil.make_archive("dist/YNU选课助手Pro_Portable", "zip", "dist", "YNU选课助手Pro")
    print("[OK] 便携版创建成功: dist/YNU选课助手Pro_Portable.zip")
    
    # 提示安装 NSIS
    print("\n[提示] 如需创建安装包，请安装 NSIS:")
    print("       下载地址: https://nsis.sourceforge.io/Download")
    print("       安装后重新运行此脚本即可生成安装包")
    
    return True

def main():
    print("=" * 50)
    print("  YNU选课助手 Pro - 打包工具")
    print("=" * 50)
    print("\n此脚本将：")
    print("1. 将程序打包为独立 EXE（包含所有依赖）")
    print("2. 创建安装包或便携版 ZIP")
    print("\n按 Enter 开始，Ctrl+C 取消...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n已取消")
        return
    
    # 打包 EXE
    if not build_exe():
        return
    
    # 创建安装包
    create_installer()
    
    # 显示结果
    print("\n" + "=" * 50)
    print("打包完成！")
    print("=" * 50)
    
    dist_files = []
    if os.path.exists("dist"):
        for f in os.listdir("dist"):
            path = os.path.join("dist", f)
            if os.path.isfile(path):
                size = os.path.getsize(path) / (1024 * 1024)
                dist_files.append(f"  - {f} ({size:.1f} MB)")
            elif os.path.isdir(path):
                dist_files.append(f"  - {f}/ (文件夹)")
    
    print("\n生成的文件:")
    for f in dist_files:
        print(f)
    
    print("\n使用方法:")
    print("  便携版: 解压 ZIP 后运行 YNU选课助手Pro.exe")
    print("  安装版: 运行 Setup.exe 安装后从开始菜单启动")

if __name__ == "__main__":
    main()
