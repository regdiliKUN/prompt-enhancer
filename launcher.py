#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动入口：打包后的 exe、桌面快捷方式、开发环境都指向这里。

单实例保护：若端口已被占用（程序已在运行），只打开界面窗口后退出，不会启动第二份服务。

仅创建快捷方式（供包体根目录的 CreateShortcut.bat 调用，无需 Python 环境）：
    PromptEnhancer.exe --create-shortcut          # 创建/更新后弹窗提示结果
    PromptEnhancer.exe --create-shortcut --launch  # 创建后顺带启动程序
    PromptEnhancer.exe --shortcut-status          # 只查看当前状态
    PromptEnhancer.exe --create-shortcut --no-dialog   # 不弹窗（自动化/脚本用）
"""

import argparse
import os
import socket
import sys
import traceback
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_TITLE = "提示词增强器"


def port_in_use(host, port, timeout=0.6):
    try:
        with socket.socket() as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def safe_print(text):
    try:
        print(text)
    except Exception:
        pass


def write_error_log(exc_text, name="launcher_error.log"):
    try:
        import appdata
        d = appdata.resolve_data_dirs()[0]
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(exc_text)
    except Exception:
        pass


def notify(text, ok=True, dialog=True):
    """无控制台 exe 用系统弹窗反馈；--no-dialog 时只写日志与标准输出"""
    safe_print(text)
    if not dialog or os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, APP_TITLE, 0x40 if ok else 0x10)
    except Exception:
        pass


def shortcut_command(create=True, launch_after=False, dialog=True):
    """创建 / 更新桌面快捷方式（不启动服务）"""
    try:
        import shortcuts
    except Exception as exc:  # noqa: BLE001
        notify("无法加载快捷方式模块：%s" % exc, False, dialog)
        return 1

    try:
        if os.name != "nt":
            notify("当前系统不是 Windows，请改用包体内 tools/create_shortcut.sh\n"
                   "（macOS 生成 .command 启动器，Linux 生成 .desktop 快捷方式）。", False, dialog)
            return 2
        # 显式点击「创建」时用 force=True：即使桌面已存在指向其他有效程序的
        # 快捷方式也原地覆盖更新（幂等，不会产生第二个文件）
        res = shortcuts.ensure(create=True, force=True) if create else shortcuts.status()
    except Exception as exc:  # noqa: BLE001
        res = {"status": "failed", "path": None, "message": "创建快捷方式时出错：%s" % exc}

    ok = res.get("status") in ("created", "updated", "exists")
    if not create and res.get("status") != "failed":
        ok = True  # 仅查询状态：未创建/待更新都算正常反馈
    text = res.get("message") or "操作完成"
    detail = ""
    if res.get("path"):
        detail += "\n快捷方式：%s" % res["path"]
    tgt = res.get("target") or {}
    if tgt.get("target"):
        detail += "\n启动目标：%s %s" % (tgt["target"], tgt.get("arguments", ""))
        detail += "\n工作目录：%s" % tgt.get("workdir", "")
    if not ok:
        detail += "\n\n若反复失败，可手动创建：右键桌面 → 新建 → 快捷方式，"
        detail += "目标填入上方「启动目标」。"
    notify(text + detail, ok, dialog)
    write_error_log("%s\n%s\n" % (text, detail), "shortcut_result.log")

    if launch_after and ok:
        try:
            r = shortcuts.launch()
            if not r.get("ok"):
                notify(r.get("message") or "启动失败", False, dialog)
        except Exception as exc:  # noqa: BLE001
            notify("启动失败：%s" % exc, False, dialog)
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="提示词增强器启动器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8756)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--create-shortcut", action="store_true",
                        help="创建或更新桌面快捷方式后退出（不启动服务）")
    parser.add_argument("--shortcut-status", action="store_true",
                        help="只查看桌面快捷方式状态后退出")
    parser.add_argument("--launch", action="store_true",
                        help="与 --create-shortcut 同用：创建后立即启动程序")
    parser.add_argument("--no-dialog", action="store_true",
                        help="不弹出结果对话框（仅供脚本/自动化调用）")
    args = parser.parse_args(argv)

    # 自动化 / CI 场景可用环境变量 PROMPT_ENHANCER_NO_DIALOG=1 关闭弹窗
    dialog = not args.no_dialog and os.environ.get("PROMPT_ENHANCER_NO_DIALOG") != "1"
    if args.shortcut_status:
        return shortcut_command(create=False, dialog=dialog)
    if args.create_shortcut:
        return shortcut_command(create=True, launch_after=args.launch, dialog=dialog)

    url = "http://%s:%d/" % (args.host, args.port)
    if port_in_use(args.host, args.port):
        safe_print("程序已在运行：%s（本次不再重复启动服务）" % url)
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    import server
    server.run_server(args.host, args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        text = traceback.format_exc()
        write_error_log(text)
        safe_print(text)
        sys.exit(1)
