#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包脚本：把提示词增强器打包为 Windows 桌面应用（PyInstaller 单目录 exe）。

用法：
    python build_package.py                       # 输出到 I:\\workbuddyAI\\prompt-enhancer
    python build_package.py --out D:\\somewhere    # 自定义输出目录
    python build_package.py --console             # 打带控制台的 exe（便于排错）

安全保证：构建前会把包体目录中已存在的 data/（便携数据）备份到
<输出目录>/data_backup_<时间戳>/，构建完成后原样恢复，重新打包不会丢数据。
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = r"I:\workbuddyAI\prompt-enhancer"
APP_NAME = "PromptEnhancer"
PY_MANAGED = r"C:\Users\xukunhang\.workbuddy\binaries\python\versions\3.13.12\python.exe"


def ensure_icon():
    ico = os.path.join(ROOT, "assets", "icon.ico")
    if os.path.isfile(ico):
        return ico
    py = PY_MANAGED if os.path.isfile(PY_MANAGED) else sys.executable
    r = subprocess.run([py, os.path.join(ROOT, "tools", "make_icon.py")],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    if not os.path.isfile(ico):
        raise SystemExit("图标生成失败")
    return ico


def copy_shortcut_entries(app_dir):
    """把「一键创建桌面快捷方式」入口放进包体根目录，用户解压后双击即用"""
    tools_dst = os.path.join(app_dir, "tools")
    os.makedirs(tools_dst, exist_ok=True)
    for name in ("create_shortcut.py", "create_shortcut.sh"):
        src = os.path.join(ROOT, "tools", name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(tools_dst, name))
    # bat 必须是 CRLF 换行，否则 cmd 解析 goto/标签会异常
    for name in ("CreateShortcut.bat", "创建桌面快捷方式.bat"):
        src = os.path.join(ROOT, name)
        if not os.path.isfile(src):
            continue
        with open(src, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        with open(os.path.join(app_dir, name), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(text.replace("\r\n", "\n").replace("\n", "\r\n"))


def backup_and_restore(app_dir, func):
    data_dir = os.path.join(app_dir, "data")
    backup = None
    if os.path.isdir(data_dir):
        backup = os.path.join(os.path.dirname(app_dir),
                              "data_backup_%s" % time.strftime("%Y%m%d_%H%M%S"))
        shutil.move(data_dir, backup)
        print("已备份便携数据 → %s" % backup)
    try:
        func()
    finally:
        if backup and not os.path.isdir(data_dir):
            shutil.move(backup, data_dir)
            print("已恢复便携数据 → %s" % data_dir)


def build(out_dir, console):
    py = r"C:\Users\xukunhang\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
    if not os.path.isfile(py):
        py = sys.executable
        try:
            import PyInstaller  # noqa: F401
        except ImportError:
            raise SystemExit("未找到 PyInstaller，请先安装：pip install pyinstaller")

    os.makedirs(out_dir, exist_ok=True)
    build_dir = os.path.join(out_dir, "build")
    cmd = [
        py, "-m", "PyInstaller", "--noconfirm",
        "--name", APP_NAME,
        "--onedir",
        "--icon", ensure_icon(),
        "--add-data", os.path.join(ROOT, "web") + ";web",
        "--add-data", os.path.join(ROOT, "assets") + ";assets",
        "--distpath", out_dir,
        "--workpath", build_dir,
        "--specpath", build_dir,
    ]
    cmd.append("--console" if console else "--noconsole")
    cmd.append(os.path.join(ROOT, "launcher.py"))
    print("执行：%s" % " ".join('"%s"' % c if " " in c else c for c in cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit("打包失败（exit %d）" % r.returncode)


def main():
    ap = argparse.ArgumentParser(description="打包提示词增强器为 Windows 桌面应用")
    ap.add_argument("--out", default=OUT_DEFAULT, help="输出目录（默认 %s）" % OUT_DEFAULT)
    ap.add_argument("--console", action="store_true", help="打包为带控制台的 exe，便于排错")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    app_dir = os.path.join(out_dir, APP_NAME)
    exe = os.path.join(app_dir, APP_NAME + ".exe")

    backup_and_restore(app_dir, lambda: build(out_dir, args.console))

    if not os.path.isfile(exe):
        raise SystemExit("打包完成但未找到 exe：%s" % exe)

    copy_shortcut_entries(app_dir)
    shutil.copy2(os.path.join(ROOT, "README.md"), os.path.join(app_dir, "README.md"))
    with open(os.path.join(app_dir, "启动说明.txt"), "w", encoding="utf-8") as f:
        f.write(
            "提示词增强器（本地运行，不上传数据）\n"
            "====================================\n\n"
            "【最推荐】第一步就做这件事：\n"
            "  双击本目录下的「创建桌面快捷方式.bat」（或 CreateShortcut.bat），\n"
            "  桌面会自动出现带图标的「提示词增强器」，以后双击它即可启动。\n"
            "  重复双击只会刷新，不会产生第二个快捷方式。\n\n"
            "其他启动方式：\n"
            "1. 双击 PromptEnhancer.exe 启动，会自动打开浏览器界面；\n"
            "   界面右上角蓝色按钮「一键启动 · 创建桌面快捷方式」也能创建桌面图标。\n"
            "2. 命令行创建：PromptEnhancer.exe --create-shortcut\n"
            "   查看状态：PromptEnhancer.exe --shortcut-status\n\n"
            "说明：\n"
            "3. 快捷方式指向本目录下的 PromptEnhancer.exe，工作目录为本目录，\n"
            "   图标取 assets/icon.ico；移动整个目录后重新双击 bat 即可自动更新指向。\n"
            "4. 只需普通用户权限；失败时会给出可读提示，并写入\n"
            "   %LOCALAPPDATA%\\PromptEnhancer\\data\\shortcut_result.log。\n"
            "5. 你的偏好设置、历史记录、窗口状态保存在：\n"
            "   %LOCALAPPDATA%\\PromptEnhancer\\data（并与包体目录 data/ 保持同步），\n"
            "   重新打包、移动或重装都不会丢失。\n"
            "6. 首次使用前请确认本地推理服务已启动（默认 Ollama：http://127.0.0.1:11434）。\n"
        )
    size_mb = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fs in os.walk(app_dir) for f in fs
    ) / 1024 / 1024
    print("\n打包完成：%s（约 %.1f MB）" % (exe, size_mb))
    print("自测步骤：")
    print("  1) 双击包体根目录的「创建桌面快捷方式.bat」→ 桌面出现「提示词增强器」")
    print("  2) 再双击一次 → 提示已存在，且不产生第二个快捷方式")
    print("  3) 双击桌面快捷方式 → 程序正常启动（服务起来并打开界面）")
    print("  4) 把整个目录挪到别处，再双击 bat → 快捷方式指向自动更新为新的 exe 路径")
    print("  5) 命令行：%s --shortcut-status / --create-shortcut --no-dialog" % os.path.basename(exe))


if __name__ == "__main__":
    main()
