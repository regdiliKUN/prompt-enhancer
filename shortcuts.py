# -*- coding: utf-8 -*-
"""
桌面快捷方式创建 / 检查 / 启动（Windows，PowerShell COM 实现，无第三方依赖）。

幂等：已存在且指向正确目标时不重复创建，仅返回提示；
      已存在但目标或图标陈旧时原地更新。
可测：通过环境变量覆盖桌面目录与目标可执行文件，便于本地自测。
"""

import json
import os
import subprocess
import sys
import tempfile

APP_NAME = "提示词增强器"
LINK_NAME = "提示词增强器.lnk"


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #
def desktop_dir():
    override = os.environ.get("PROMPT_ENHANCER_DESKTOP_DIR")
    if override:
        return override
    if os.name != "nt":
        return os.path.join(os.path.expanduser("~"), "Desktop")
    try:
        out = _run_ps("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                      "[Environment]::GetFolderPath('Desktop')")
        val = (out.stdout or "").strip().splitlines()
        if val and val[0] and os.path.isdir(val[0]):
            return val[0]
    except Exception:
        pass
    for base in (os.environ.get("USERPROFILE"), os.path.expanduser("~")):
        if base:
            p = os.path.join(base, "Desktop")
            if os.path.isdir(p):
                return p
    return os.path.join(os.path.expanduser("~"), "Desktop")


def icon_path():
    bundle = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for cand in (
        os.path.join(bundle, "assets", "icon.ico"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico"),
    ):
        if os.path.isfile(cand):
            return cand
    return ""


def resolve_target():
    """返回 {target, arguments, workdir, icon, description, kind}"""
    override = os.environ.get("PROMPT_ENHANCER_SHORTCUT_TARGET")
    icon = icon_path()
    if override:
        return {
            "target": override, "arguments": "", "workdir": os.path.dirname(override),
            "icon": icon, "description": APP_NAME, "kind": "override",
        }
    if getattr(sys, "frozen", False):
        return {
            "target": sys.executable, "arguments": "", "workdir": os.path.dirname(sys.executable),
            "icon": icon, "description": "%s（本地提示词优化工具）" % APP_NAME, "kind": "exe",
        }
    here = os.path.dirname(os.path.abspath(__file__))
    py = sys.executable
    if os.name == "nt":  # 开发环境优先使用无控制台的 pythonw
        pw = os.path.join(os.path.dirname(py), "pythonw.exe")
        if os.path.isfile(pw):
            py = pw
    return {
        "target": py,
        "arguments": '"%s"' % os.path.join(here, "launcher.py"),
        "workdir": here,
        "icon": icon,
        "description": "%s（开发环境入口）" % APP_NAME,
        "kind": "python",
    }


def link_path():
    return os.path.join(desktop_dir(), LINK_NAME)


# --------------------------------------------------------------------------- #
# PowerShell 辅助
# --------------------------------------------------------------------------- #
def _ps_str(value):
    return "'" + str(value).replace("'", "''") + "'"


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


def _friendly_error(stderr, stdout=""):
    text = (stderr or "") + " " + (stdout or "")
    low = text.lower()
    if "unauthorizedaccess" in low or "拒绝访问" in text or "0x80070005" in low or "access is denied" in low:
        return "权限不足：当前用户无法写入桌面目录，或安全策略拦截了快捷方式创建。请以普通用户身份重新登录后再试，或改用「以管理员身份运行」启动本程序。"
    if "0x80070422" in low or "已被禁用" in text or "disabled" in low:
        return "系统禁用了 WScript.Shell 组件（组策略限制），无法自动创建快捷方式。请联系管理员或手动创建。"
    if "not recognized" in low or "找不到" in text or "无法将" in text and "powershell" in low:
        return "未找到 PowerShell，无法自动创建快捷方式。"
    if "timed out" in low or "超时" in text:
        return "创建快捷方式超时，请重试。"
    first = ""
    for line in (stderr or "").splitlines():
        line = line.strip()
        if line and not line.startswith("+"):
            first = line
            break
    return first or "创建快捷方式失败（未知原因）"


# --------------------------------------------------------------------------- #
# 检查 / 创建
# --------------------------------------------------------------------------- #
def inspect():
    """读取桌面快捷方式当前状态"""
    lnk = link_path()
    info = {
        "exists": os.path.exists(lnk),
        "path": lnk,
        "desktop": desktop_dir(),
        "target": None,
        "arguments": None,
        "icon": None,
        "matches": False,
        "message": "",
    }
    if not info["exists"]:
        info["message"] = "桌面快捷方式尚未创建"
        return info

    tgt = resolve_target()
    script = (
        "$ErrorActionPreference='Stop'\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$sc = $ws.CreateShortcut(%s)\n"
        "$obj = @{ target = $sc.TargetPath; arguments = $sc.Arguments; icon = $sc.IconLocation; workdir = $sc.WorkingDirectory }\n"
        "$obj | ConvertTo-Json -Compress\n" % _ps_str(lnk)
    )
    try:
        proc = _run_ps(script, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip().splitlines()[0])
            info["target"] = data.get("target")
            info["arguments"] = data.get("arguments")
            info["icon"] = data.get("icon")
    except Exception:
        pass
    same_target = bool(info["target"]) and os.path.normcase(info["target"]) == os.path.normcase(tgt["target"])
    same_icon = (not tgt["icon"]) or (info["icon"] or "").lower().startswith(tgt["icon"].lower())
    info["matches"] = bool(same_target and same_icon)
    if info["matches"]:
        info["message"] = "桌面快捷方式已存在，指向：%s" % (info["target"] or "未知")
    else:
        info["message"] = "桌面已有快捷方式（当前指向：%s）。若其目标仍有效则不会自动覆盖；目标已失效时点击按钮会自动修复" % (info["target"] or "未知")
    return info


def status():
    """只返回桌面快捷方式的当前状态，不写入任何文件"""
    info = inspect()
    if not info["exists"]:
        st = "missing"
    elif info["matches"]:
        st = "exists"
    else:
        st = "mismatch"
    return {"status": st, "path": info["path"], "message": info["message"], "target": resolve_target()}


def ensure(create=True, force=False):
    """确保桌面快捷方式存在且指向正确目标。

    force=True 时（用户显式点击「创建桌面快捷方式」），即使已有快捷方式指向
    另一个有效程序也原地覆盖更新；界面按钮默认 force=False，避免开发环境与
    包体互相抢夺同一个快捷方式。
    """
    tgt = resolve_target()
    if os.name != "nt":
        return {"status": "unsupported", "path": None,
                "message": "当前系统不是 Windows，暂不支持自动创建桌面快捷方式", "target": tgt}

    info = inspect()
    lnk = info["path"]
    if info["exists"] and info["matches"]:
        return {"status": "exists", "path": lnk, "message": "快捷方式已存在，未重复创建（%s）" % lnk, "target": tgt}
    if info["exists"] and not force and info["target"] and os.path.isfile(info["target"]):
        # 已有快捷方式且其目标仍然有效（例如指向本应用的另一份安装），不互相覆盖
        return {"status": "exists_other", "path": lnk,
                "message": "桌面已有快捷方式且指向有效程序（%s），未做改动；如需指向当前程序，请先删除该快捷方式再点击创建"
                           % info["target"], "target": tgt}
    # 不存在，或已存在但原目标已失效（程序被移动 / 卸载）→ 新建或原地更新
    if not create:
        return {"status": "missing", "path": lnk, "message": "快捷方式尚未创建", "target": tgt}

    if not os.path.isdir(info["desktop"]):
        return {"status": "failed", "path": lnk,
                "message": "桌面目录不存在或不可访问：%s" % info["desktop"], "target": tgt}

    if not os.path.isfile(tgt["target"]):
        return {"status": "failed", "path": lnk,
                "message": "找不到要指向的可执行文件：%s" % tgt["target"], "target": tgt}

    script = (
        "$ErrorActionPreference='Stop'\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$sc = $ws.CreateShortcut(%s)\n"
        "$sc.TargetPath = %s\n"
        "$sc.Arguments = %s\n"
        "$sc.WorkingDirectory = %s\n"
        "$sc.Description = %s\n"
        "$sc.WindowStyle = 1\n"
        "$sc.Save()\n" % (
            _ps_str(lnk), _ps_str(tgt["target"]), _ps_str(tgt["arguments"]),
            _ps_str(tgt["workdir"]), _ps_str(tgt["description"]),
        )
    )
    icon = tgt["icon"]
    if icon:
        script = script.replace("$sc.Save()", "$sc.IconLocation = %s\n$sc.Save()" % _ps_str(icon + ",0"))

    try:
        proc = _run_ps(script, timeout=60)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "path": lnk, "message": _friendly_error("超时"), "target": tgt}
    except FileNotFoundError:
        return {"status": "failed", "path": lnk, "message": _friendly_error("未找到 powershell"), "target": tgt}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "path": lnk, "message": _friendly_error(str(exc)), "target": tgt}

    if proc.returncode != 0 or not os.path.exists(lnk):
        return {"status": "failed", "path": lnk,
                "message": _friendly_error(proc.stderr, proc.stdout), "target": tgt}

    after = inspect()
    status = "updated" if info["exists"] else "created"
    if not after["matches"]:
        status = "updated"
    msg = "已在桌面创建快捷方式：%s" % lnk if status == "created" else "已把现有快捷方式更新为当前程序：%s" % lnk
    return {"status": status, "path": lnk, "message": msg, "target": tgt}


def launch(path=None):
    """通过快捷方式启动程序；失败时回退为直接启动目标"""
    lnk = path or link_path()
    result = {"path": lnk, "method": None, "ok": False, "message": ""}
    if os.path.exists(lnk) and os.name == "nt":
        try:
            os.startfile(lnk)  # noqa: S606
            result.update(method="shortcut", ok=True, message="已通过桌面快捷方式启动：%s" % lnk)
            return result
        except Exception as exc:  # noqa: BLE001
            result["message"] = str(exc)
    tgt = resolve_target()
    try:
        if os.name == "nt":
            os.startfile(tgt["target"])
        else:
            subprocess.Popen([tgt["target"]])
        result.update(method="target", ok=True, message="已直接启动：%s" % tgt["target"])
    except Exception as exc:  # noqa: BLE001
        result.update(method="failed", ok=False, message="启动失败：%s" % exc)
    return result
