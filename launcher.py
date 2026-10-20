#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动入口：打包后的 exe、桌面快捷方式、开发环境都指向这里。

单实例保护：若端口已被占用（程序已在运行），只打开界面窗口后退出，不会启动第二份服务。
"""

import argparse
import os
import socket
import sys
import traceback
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def port_in_use(host, port, timeout=0.6):
    try:
        with socket.socket() as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def write_error_log(exc_text):
    try:
        import appdata
        d = appdata.resolve_data_dirs()[0]
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "launcher_error.log"), "w", encoding="utf-8") as f:
            f.write(exc_text)
    except Exception:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="提示词增强器启动器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8756)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)

    url = "http://%s:%d/" % (args.host, args.port)
    if port_in_use(args.host, args.port):
        print("程序已在运行：%s（本次不再重复启动服务）" % url)
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
        print(text)
        sys.exit(1)
