#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键创建 / 更新桌面快捷方式（零第三方依赖，仅用标准库）。

放置位置：<包体根目录 或 项目根目录>/tools/create_shortcut.py
典型调用：
    python tools/create_shortcut.py                 # 创建或更新快捷方式
    python tools/create_shortcut.py --check         # 只检查当前状态，不写入
    python tools/create_shortcut.py --force         # 已正确时也强制重写
    python tools/create_shortcut.py --launch        # 创建后立即启动程序
    python tools/create_shortcut.py --root "D:\\xx\\PromptEnhancer"   # 指定根目录（排错用）
    python tools/create_shortcut.py --desktop "D:\\tmp\\desktop"      # 指定桌面目录（自测用）
    python tools/create_shortcut.py --json          # 输出机器可读结果

设计要点：
  * 根目录自动识别（脚本所在目录的上级目录，或 exe / launcher.py 所在目录），不写死任何绝对路径
  * 优先指向 PromptEnhancer.exe；没有 exe 时退回 python(w) + launcher.py
  * 幂等：同一路径只存在一个快捷方式；已存在且正确时提示“未重复创建”，不正确时原地更新
  * 只需普通用户权限，不写 Program Files、不改注册表
  * 所有失败都转换为可读的中文说明，并返回非 0 退出码

退出码：0 成功或已存在 / 1 失败 / 2 当前系统暂不支持
"""

import argparse
import glob
import json
import os
import stat
import subprocess
import sys
import tempfile

APP_NAME = "提示词增强器"
APP_COMMENT = "本地提示词优化工具（数据不出本机）"
LINK_NAME = "提示词增强器.lnk"          # Windows
COMMAND_NAME = "提示词增强器.command"    # macOS
DESKTOP_ENTRY = "prompt-enhancer.desktop"  # Linux
EXE_NAME = "PromptEnhancer.exe"
LAUNCHER = "launcher.py"
ICON_NAMES = ("icon.ico", "icon.png", "icon.icns")

EXIT_OK, EXIT_FAIL, EXIT_UNSUPPORTED = 0, 1, 2


class ShortcutError(Exception):
    """可读错误：直接展示给用户"""


# --------------------------------------------------------------------------- #
# 路径识别
# --------------------------------------------------------------------------- #
def looks_like_app(root):
    if not root or not os.path.isdir(root):
        return False
    if os.path.isfile(os.path.join(root, EXE_NAME)):
        return True
    if glob.glob(os.path.join(root, "*.exe")):
        return True
    return os.path.isfile(os.path.join(root, LAUNCHER))


def app_root(explicit=None):
    """定位解压根目录：不依赖当前工作目录，也不写死绝对路径"""
    # 显式指定（--root 或环境变量）时不做回退，错了就直接告诉用户
    chosen = explicit or os.environ.get("PROMPT_ENHANCER_ROOT")
    if chosen:
        chosen = os.path.abspath(chosen)
        if not os.path.isdir(chosen):
            raise ShortcutError("指定的程序根目录不存在：%s" % chosen)
        if not looks_like_app(chosen):
            raise ShortcutError(
                "指定的目录里没有找到主程序（应为 %s 或 %s）：\n  %s\n"
                "请指向解压后的 PromptEnhancer 目录。"
                % (EXE_NAME, LAUNCHER, chosen)
            )
        return chosen

    candidates = []
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    # 脚本位于 <root>/tools/ 下时，根目录是它的上一级
    if os.path.basename(here).lower() == "tools":
        candidates += [parent, here]
    else:
        candidates += [here, parent]
    candidates.append(os.getcwd())

    seen = set()
    for c in candidates:
        key = os.path.normcase(c)
        if key in seen:
            continue
        seen.add(key)
        if looks_like_app(c):
            return c
    raise ShortcutError(
        "没能定位到程序根目录。已尝试：\n  %s\n"
        "请把 create_shortcut.py 放在包体的 tools\\ 目录下再运行，"
        "或用 --root 指定解压后的根目录。"
        % "\n  ".join(candidates[:4])
    )


def find_icon(root, exe=""):
    """图标：优先 assets/icon.ico，其次打包资源的 _internal/assets，最后用 exe 自带图标"""
    for sub in ("assets", os.path.join("_internal", "assets")):
        for name in ICON_NAMES:
            p = os.path.join(root, sub, name)
            if os.path.isfile(p):
                return p
    if exe and os.path.isfile(exe):
        return exe  # Windows 支持 "exe,0" 形式，取可执行文件自带图标
    return ""


def python_for_launcher():
    """启动 .py 主脚本用的解释器：Windows 优先 pythonw（不弹黑框）"""
    py = sys.executable or "python"
    if os.name == "nt":
        pw = os.path.join(os.path.dirname(py), "pythonw.exe")
        if os.path.isfile(pw):
            return pw
    return py


def detect_target(root):
    """返回 {target, arguments, workdir, icon, description, kind}"""
    exe = os.path.join(root, EXE_NAME)
    if not os.path.isfile(exe):
        exes = [p for p in sorted(glob.glob(os.path.join(root, "*.exe")))
                if "unins" not in os.path.basename(p).lower()
                and "setup" not in os.path.basename(p).lower()]
        exe = exes[0] if exes else ""

    if exe:
        return {
            "target": exe, "arguments": "", "workdir": root,
            "icon": find_icon(root, exe), "description": "%s · %s" % (APP_NAME, APP_COMMENT),
            "kind": "exe",
        }

    launcher = os.path.join(root, LAUNCHER)
    if os.path.isfile(launcher):
        py = python_for_launcher()
        return {
            "target": py, "arguments": '"%s"' % launcher, "workdir": root,
            "icon": find_icon(root, ""), "description": "%s · %s（脚本入口）" % (APP_NAME, APP_COMMENT),
            "kind": "script",
        }

    raise ShortcutError(
        "在根目录中没有找到可启动的主程序：\n  %s\n"
        "期望存在 %s 或 %s。若你解压后的目录结构不同，请用 --root 指定正确目录。"
        % (root, EXE_NAME, LAUNCHER)
    )


def desktop_dir(explicit=None):
    if explicit:
        return os.path.abspath(explicit)
    env = os.environ.get("PROMPT_ENHANCER_DESKTOP_DIR")
    if env:
        return os.path.abspath(env)
    if os.name == "nt":
        # 先问系统（桌面常被重定向到 D:\Desktop、OneDrive 等位置），再退回常见路径
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-Command", "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                             "[Environment]::GetFolderPath('Desktop')"],
                capture_output=True, text=True, timeout=20)
            val = (out.stdout or "").strip().splitlines()
            if val and val[0].strip() and os.path.isdir(val[0].strip()):
                return val[0].strip()
        except Exception:
            pass
        for base in (os.environ.get("USERPROFILE"), os.path.expanduser("~")):
            if not base:
                continue
            for sub in ("Desktop", os.path.join("OneDrive", "Desktop")):
                p = os.path.join(base, sub)
                if os.path.isdir(p):
                    return p
        return os.path.join(os.path.expanduser("~"), "Desktop")
    return os.path.join(os.path.expanduser("~"), "Desktop")


# --------------------------------------------------------------------------- #
# Windows：.lnk（PowerShell COM，失败回退 cscript + VBScript）
# --------------------------------------------------------------------------- #
def _ps_str(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _run_ps(script, timeout=60):
    fd, path = tempfile.mkstemp(prefix="pe_sc_", suffix=".ps1")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(script)
        return subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _vbs_str(value):
    return '"' + str(value or "").replace('"', '""') + '"'


def friendly_error(stderr="", stdout=""):
    text = (stderr or "") + " " + (stdout or "")
    low = text.lower()
    if ("unauthorizedaccess" in low or "拒绝访问" in text
            or "0x80070005" in low or "access is denied" in low):
        return ("权限不足，无法写入桌面目录。\n"
                "请确认：① 用解压出来的目录（不要放在 C:\\Program Files 等受保护目录）；"
                "② 当前用户对桌面有写权限；③ 安全软件没有拦截脚本创建快捷方式。")
    if "0x80070422" in low or "已被禁用" in text or "disabled" in low:
        return "系统禁用了 WScript.Shell 组件（多为组策略限制），无法自动创建快捷方式，请手动创建。"
    if "is not recognized" in low or "找不到" in text or ("无法将" in text and "powershell" in low):
        return "系统缺少 PowerShell / cscript 组件，无法自动创建快捷方式，请手动创建。"
    if "timed out" in low or "超时" in text:
        return "创建操作超时，请关闭占用桌面的程序后重试。"
    for line in (stderr or "").splitlines():
        line = line.strip()
        if line and not line.startswith("+"):
            return line
    return "创建快捷方式失败（未知原因）"


def read_lnk(path):
    """读取已有快捷方式的目标 / 参数 / 图标 / 工作目录"""
    script = (
        "$ErrorActionPreference='Stop'\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$sc = $ws.CreateShortcut(%s)\n"
        "@{ t = $sc.TargetPath; a = $sc.Arguments; i = $sc.IconLocation; w = $sc.WorkingDirectory }"
        " | ConvertTo-Json -Compress\n" % _ps_str(path)
    )
    try:
        proc = _run_ps(script, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip().splitlines()[0])
            return {"target": data.get("t"), "arguments": data.get("a"),
                    "icon": data.get("i"), "workdir": data.get("w")}
    except Exception:
        pass
    return None


def _write_vbs(path, tgt, icon, prev_err=""):
    """回退方案：用 cscript + VBScript 写 .lnk（PowerShell 被禁用 / 不可用时）"""
    vbs = (
        'Set ws = CreateObject("WScript.Shell")\n'
        'Set sc = ws.CreateShortcut(%s)\n'
        'sc.TargetPath = %s\n'
        'sc.Arguments = %s\n'
        'sc.WorkingDirectory = %s\n'
        'sc.Description = %s\n'
        'sc.IconLocation = %s\n'
        'sc.WindowStyle = 1\n'
        'sc.Save\n' % (_vbs_str(path), _vbs_str(tgt["target"]), _vbs_str(tgt["arguments"]),
                       _vbs_str(tgt["workdir"]), _vbs_str(tgt["description"]), _vbs_str(icon))
    )
    fd, vpath = tempfile.mkstemp(prefix="pe_sc_", suffix=".vbs")
    os.close(fd)
    try:
        # Windows 脚本宿主按 ANSI / UTF-16 读取，中文必须写成 UTF-16（带 BOM）
        with open(vpath, "w", encoding="utf-16") as f:
            f.write(vbs)
        proc = subprocess.run(["cscript", "//nologo", vpath],
                              capture_output=True, text=True, timeout=60,
                              encoding="utf-8", errors="replace")
        if proc.returncode == 0 and os.path.exists(path):
            return True, ""
        return False, friendly_error((proc.stderr or "") + (proc.stdout or "") or prev_err)
    except FileNotFoundError:
        return False, prev_err or "系统缺少 PowerShell 与 cscript，无法自动创建快捷方式，请手动创建。"
    except Exception as exc:  # noqa: BLE001
        return False, friendly_error(str(exc) or prev_err)
    finally:
        try:
            os.remove(vpath)
        except OSError:
            pass


def _try_write(path, tgt):
    """PowerShell 优先，失败回退 VBScript；返回 (是否报告成功, 错误说明)"""
    icon = (tgt["icon"] + ",0") if tgt["icon"] else ""
    ps = (
        "$ErrorActionPreference='Stop'\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$sc = $ws.CreateShortcut(%s)\n"
        "$sc.TargetPath = %s\n"
        "$sc.Arguments = %s\n"
        "$sc.WorkingDirectory = %s\n"
        "$sc.Description = %s\n"
        "$sc.IconLocation = %s\n"
        "$sc.WindowStyle = 1\n"
        "$sc.Save()\n" % (_ps_str(path), _ps_str(tgt["target"]), _ps_str(tgt["arguments"]),
                          _ps_str(tgt["workdir"]), _ps_str(tgt["description"]), _ps_str(icon))
    )
    try:
        proc = _run_ps(ps, timeout=60)
        if proc.returncode == 0 and os.path.exists(path):
            return True, ""
        err = friendly_error(proc.stderr, proc.stdout)
    except subprocess.TimeoutExpired:
        err = friendly_error("超时")
    except FileNotFoundError:
        err = ""  # 没有 PowerShell，直接走 VBScript
    except Exception as exc:  # noqa: BLE001
        err = friendly_error(str(exc))

    ok, err2 = _write_vbs(path, tgt, icon, err)
    if ok:
        return True, ""
    return False, err2 or err or "创建快捷方式失败"


def _verify_lnk(path, tgt):
    """写完后回读校验；读不到（COM 读取不可用）时视为无法校验，返回 None"""
    cur = read_lnk(path)
    if not cur:
        return None
    return os.path.normcase(cur["target"] or "") == os.path.normcase(tgt["target"])


def write_lnk(path, tgt):
    """写入 .lnk：PowerShell → VBScript；写完后回读校验，
    若内容仍是旧的（覆盖被安全策略拒绝），则删除旧文件后重建。"""
    existed = os.path.exists(path)
    ok, err = _try_write(path, tgt)
    if ok:
        verified = _verify_lnk(path, tgt)
        if verified is not False:
            return True, ""

    if not existed:
        return False, err or "创建快捷方式失败"

    # 覆盖写入没生效：删掉旧的再建一次
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as exc:
            return False, err or ("无法覆盖已存在的快捷方式：%s" % exc)
        ok2, err2 = _try_write(path, tgt)
        if ok2 and _verify_lnk(path, tgt) is not False:
            return True, ""
        return False, err2 or err or "创建快捷方式失败"
    return False, err or "创建快捷方式失败"


# --------------------------------------------------------------------------- #
# macOS：.command 启动器（+ 可选的 Finder 别名）
# --------------------------------------------------------------------------- #
def mac_create(path, tgt):
    script = (
        '#!/bin/bash\n'
        'cd "%s" || exit 1\n'
        'exec %s %s "$@"\n' % (tgt["workdir"], _sh_q(tgt["target"]), tgt["arguments"])
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(path, 0o755)
    note = ""
    app = os.path.join(tgt["workdir"], "PromptEnhancer.app")
    if os.path.isdir(app):  # 若同时提供 .app，尝试在桌面做一个 Finder 别名
        alias = os.path.join(os.path.dirname(path), "PromptEnhancer.app")
        osa = ('tell application "Finder" to make alias file to POSIX file "%s" at POSIX file "%s"'
               % (app, os.path.dirname(path)))
        r = subprocess.run(["osascript", "-e", osa], capture_output=True, text=True)
        if r.returncode != 0:
            note = "（Finder 别名未创建：%s）" % (r.stderr.strip().splitlines() or ["未知"])[-1]
        else:
            note = "（已在桌面创建 Finder 别名）"
            return {"path": alias, "note": note}
    return {"path": path, "note": note}


def _sh_q(value):
    return "'" + str(value).replace("'", "'\\''") + "'"


# --------------------------------------------------------------------------- #
# Linux：.desktop（桌面 + 应用菜单）
# --------------------------------------------------------------------------- #
def linux_desktop_dir():
    cfg = os.path.join(os.path.expanduser("~"), ".config", "user-dirs.dirs")
    if os.path.isfile(cfg):
        try:
            with open(cfg, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR="):
                        val = line.split("=", 1)[1].strip().strip('"')
                        val = val.replace("$HOME", os.path.expanduser("~"))
                        if os.path.isdir(val):
                            return val
        except OSError:
            pass
    p = os.path.join(os.path.expanduser("~"), "Desktop")
    return p if os.path.isdir(p) else os.path.expanduser("~")


def linux_create(path, tgt):
    exec_line = _sh_q(tgt["target"])
    if tgt["arguments"]:
        exec_line += " " + tgt["arguments"]
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=%s\n"
        "Comment=%s\n"
        "Exec=%s\n"
        "Path=%s\n"
        "Icon=%s\n"
        "Terminal=false\n"
        "Categories=Utility;Development;\n"
        "StartupNotify=true\n" % (APP_NAME, APP_COMMENT, exec_line, tgt["workdir"], tgt["icon"])
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def check_windows(link, tgt):
    exists = os.path.exists(link)
    cur = read_lnk(link) if exists else None
    if not cur:
        return {"exists": exists, "correct": False, "current": None}
    same_target = os.path.normcase(cur["target"] or "") == os.path.normcase(tgt["target"])
    same_icon = (not tgt["icon"]) or (cur["icon"] or "").lower().startswith(tgt["icon"].lower())
    same_args = (cur["arguments"] or "") == (tgt["arguments"] or "")
    return {"exists": True, "correct": bool(same_target and same_icon and same_args),
            "current": cur}


def ensure_windows(link, tgt, force):
    info = check_windows(link, tgt)
    if info["exists"] and info["correct"] and not force:
        return {"status": "exists", "path": link,
                "message": "桌面快捷方式已存在且指向正确，未重复创建：%s" % link}
    ok, err = write_lnk(link, tgt)
    if not ok:
        return {"status": "failed", "path": link, "message": err or "创建快捷方式失败"}
    after = check_windows(link, tgt)
    if not after["correct"]:
        return {"status": "failed", "path": link,
                "message": "快捷方式已写入但校验未通过，请检查目标文件是否存在：%s" % tgt["target"]}
    status = "updated" if info["exists"] else "created"
    msg = ("已在桌面创建快捷方式：%s" % link if status == "created"
           else "已更新现有快捷方式（指向/图标/工作目录已刷新）：%s" % link)
    return {"status": status, "path": link, "message": msg}


def ensure_unix(root, tgt, desktop, force, system):
    if system == "darwin":
        path = os.path.join(desktop, COMMAND_NAME)
        if os.path.exists(path) and not force:
            with open(path, encoding="utf-8") as f:
                if tgt["target"] in f.read():
                    return {"status": "exists", "path": path,
                            "message": "桌面启动器已存在且指向正确，未重复创建：%s" % path}
        res = mac_create(path, tgt)
        return {"status": "updated" if os.path.exists(path) else "created",
                "path": res["path"], "message": "已在桌面创建启动器：%s %s" % (path, res["note"])}

    entry = os.path.join(desktop, DESKTOP_ENTRY)
    menu = os.path.join(os.path.expanduser("~"), ".local", "share", "applications", DESKTOP_ENTRY)
    existed = os.path.exists(entry)
    path = linux_create(entry, tgt)
    try:
        os.makedirs(os.path.dirname(menu), exist_ok=True)
        linux_create(menu, tgt)
    except OSError:
        menu = ""
    note = "（同时已登记到应用菜单）" if menu else ""
    return {"status": "updated" if existed else "created", "path": path,
            "message": "已在桌面创建快捷方式：%s%s" % (path, note)}


def launch(result_path, tgt):
    try:
        if os.name == "nt":
            os.startfile(result_path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", result_path])
        else:
            subprocess.Popen(["xdg-open", result_path])
        return True
    except Exception:  # noqa: BLE001
        return False


def run(args):
    root = app_root(args.root)
    tgt = detect_target(root)
    desktop = desktop_dir(args.desktop)
    if not os.path.isdir(desktop):
        raise ShortcutError("桌面目录不存在或不可访问：%s\n请用 --desktop 指定一个可写目录。" % desktop)
    if not os.path.isfile(tgt["target"]):
        raise ShortcutError("主程序文件不存在：%s\n请确认解压完整后重试。" % tgt["target"])

    system = sys.platform
    if os.name == "nt":
        link = os.path.join(desktop, LINK_NAME)
        if args.check:
            info = check_windows(link, tgt)
            return {"status": "exists" if info["exists"] and info["correct"] else (
                "mismatch" if info["exists"] else "missing"), "path": link,
                    "message": ("桌面快捷方式已存在且正确：%s" % link) if info["correct"]
                    else ("桌面快捷方式已存在但指向不正确：%s" % link) if info["exists"]
                    else "桌面快捷方式尚未创建", "root": root, "target": tgt, "desktop": desktop}
        res = ensure_windows(link, tgt, args.force)
    elif system == "darwin" or system.startswith("linux"):
        if args.check:
            probe = os.path.join(desktop, COMMAND_NAME if system == "darwin" else DESKTOP_ENTRY)
            ok = os.path.exists(probe)
            return {"status": "exists" if ok else "missing", "path": probe,
                    "message": ("桌面快捷方式已存在：%s" % probe) if ok else "桌面快捷方式尚未创建",
                    "root": root, "target": tgt, "desktop": desktop}
        res = ensure_unix(root, tgt, desktop, args.force, system)
    else:
        raise ShortcutError("暂不支持的操作系统：%s（可手动为 %s 创建快捷方式）" % (system, tgt["target"]))

    res.update({"root": root, "target": tgt, "desktop": desktop})
    if args.launch and res["status"] != "failed":
        res["launched"] = launch(res["path"], tgt)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="一键创建 %s 桌面快捷方式" % APP_NAME)
    ap.add_argument("--root", help="程序根目录（默认自动识别）")
    ap.add_argument("--desktop", help="桌面目录（默认自动识别，可用于自测）")
    ap.add_argument("--check", action="store_true", help="只检查状态，不创建")
    ap.add_argument("--force", action="store_true", help="即使已正确也强制重写")
    ap.add_argument("--launch", action="store_true", help="创建后立即启动程序")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args(argv)

    try:
        res = run(args)
    except ShortcutError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "message": str(exc)}, ensure_ascii=False))
        else:
            print("【%s】无法创建桌面快捷方式" % APP_NAME)
            print("----------------------------------------")
            print(str(exc))
        return EXIT_FAIL
    except Exception as exc:  # noqa: BLE001
        if args.json:
            print(json.dumps({"status": "failed", "message": "内部错误：%s" % exc}, ensure_ascii=False))
        else:
            print("【%s】创建快捷方式时发生内部错误：%s" % (APP_NAME, exc))
        return EXIT_FAIL

    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        tgt = res["target"]
        print("【%s】桌面快捷方式" % APP_NAME)
        print("----------------------------------------")
        print("程序根目录：%s" % res["root"])
        print("桌面目录　：%s" % res["desktop"])
        print("启动目标　：%s %s" % (tgt["target"], tgt["arguments"]))
        print("工作目录　：%s" % tgt["workdir"])
        print("图标　　　：%s" % (tgt["icon"] or "（使用可执行文件自带图标）"))
        print("结果　　　：%s" % res["message"])
        if res.get("launched"):
            print("已尝试启动程序。")
    return EXIT_FAIL if res["status"] == "failed" else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
