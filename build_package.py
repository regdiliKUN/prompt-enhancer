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

    shutil.copy2(os.path.join(ROOT, "README.md"), os.path.join(app_dir, "README.md"))
    with open(os.path.join(app_dir, "启动说明.txt"), "w", encoding="utf-8") as f:
        f.write(
            "提示词增强器（本地运行，不上传数据）\n"
            "====================================\n\n"
            "1. 双击 PromptEnhancer.exe 即可启动，会自动打开浏览器界面。\n"
            "2. 打开界面后，点击右上角蓝色按钮「一键启动 · 创建桌面快捷方式」，\n"
            "   即可在桌面创建带图标的快捷方式，之后双击桌面图标即可直接启动。\n"
            "3. 重复点击不会产生重复快捷方式；快捷方式指向变化时会自动更新。\n"
            "4. 你的偏好设置、历史记录、窗口状态保存在：\n"
            "   %LOCALAPPDATA%\\PromptEnhancer\\data（并与包体目录 data/ 保持同步），\n"
            "   重新打包、移动或重装都不会丢失。\n"
            "5. 首次使用前请确认本地推理服务已启动（默认 Ollama：http://127.0.0.1:11434）。\n"
        )
    size_mb = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fs in os.walk(app_dir) for f in fs
    ) / 1024 / 1024
    print("\n打包完成：%s（约 %.1f MB）" % (exe, size_mb))
    print("自测步骤：")
    print("  1) 运行：%s --no-browser --port 8757" % exe)
    print("  2) 打开 http://127.0.0.1:8757/ 点击右上角「一键启动 · 创建桌面快捷方式」")
    print("  3) 重复点击验证不重复创建；桌面双击快捷方式验证可启动")


if __name__ == "__main__":
    main()
