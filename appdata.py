# -*- coding: utf-8 -*-
"""
数据目录解析与双向同步。

目标：无论从开发目录运行（本地环境）还是从打包后的 exe 运行（包体），
用户的偏好设置、历史记录、界面 / 窗口状态都指向同一份数据，且不因重新打包而丢失。

策略：
  1. 主数据目录：包体 → %LOCALAPPDATA%\\PromptEnhancer\\data；开发环境 → 项目根 data/
  2. 启动时在两个目录之间按「文件修改时间较新者胜出」双向同步（history.db 用 sqlite 在线备份 API）
  3. 每次写入后把变更镜像到另一个目录，保证两边始终收敛
"""

import os
import shutil
import sqlite3
import sys

APP_NAME = "提示词增强器"
DIR_NAME = "PromptEnhancer"
DATA_FILES = ("config.json", "history.db", "ui_state.json")


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def app_root():
    """可执行文件（或开发入口脚本）所在目录"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def bundle_root():
    """静态资源所在目录（打包后为 PyInstaller 临时解压目录）"""
    return getattr(sys, "_MEIPASS", app_root())


def portable_data_dir():
    return os.path.join(app_root(), "data")


def user_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, DIR_NAME, "data")


def resolve_data_dirs():
    """返回 (主数据目录, 镜像目录)"""
    env = os.environ.get("PROMPT_ENHANCER_DATA_DIR")
    if env:
        os.makedirs(env, exist_ok=True)
        return env, None
    if is_frozen():
        return user_data_dir(), portable_data_dir()
    return portable_data_dir(), user_data_dir()


def ensure(path):
    os.makedirs(path, exist_ok=True)
    return path


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return -1.0


def copy_db(src, dst):
    """在线拷贝 sqlite 数据库（不中断正在运行的连接）"""
    tmp = dst + ".tmp"
    try:
        s = sqlite3.connect(src)
        d = sqlite3.connect(tmp)
        try:
            s.backup(d)
        finally:
            d.close()
            s.close()
        os.replace(tmp, dst)
        return True
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def copy_file(src, dst):
    if src.endswith(".db"):
        return copy_db(src, dst)
    try:
        tmp = dst + ".tmp"
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        return True
    except Exception:
        return False


def sync_pair(primary, secondary):
    """按更新时间在两目录间同步数据文件；返回同步动作列表"""
    actions = []
    if not secondary:
        return actions
    ensure(primary)
    try:
        ensure(secondary)
    except OSError:
        return actions
    if os.path.abspath(primary) == os.path.abspath(secondary):
        return actions

    for name in DATA_FILES:
        p = os.path.join(primary, name)
        s = os.path.join(secondary, name)
        pe, se = os.path.exists(p), os.path.exists(s)
        if pe and se:
            if _mtime(p) > _mtime(s) + 0.5:
                if copy_file(p, s):
                    actions.append("%s → %s（较新）" % (name, os.path.basename(os.path.dirname(s))))
            elif _mtime(s) > _mtime(p) + 0.5:
                if copy_file(s, p):
                    actions.append("%s ← %s（较新）" % (name, os.path.basename(os.path.dirname(s))))
        elif pe and not se:
            if copy_file(p, s):
                actions.append("%s → 镜像目录（新建）" % name)
        elif se and not pe:
            if copy_file(s, p):
                actions.append("%s ← 镜像目录（恢复）" % name)
    return actions


def mirror(primary, secondary):
    """写入后把数据文件镜像到另一目录"""
    if not secondary or not os.path.isdir(secondary):
        return
    if os.path.abspath(primary) == os.path.abspath(secondary):
        return
    for name in DATA_FILES:
        p = os.path.join(primary, name)
        if os.path.exists(p):
            copy_file(p, os.path.join(secondary, name))


def data_info(primary, secondary, actions=None):
    def stat(d):
        if not d:
            return None
        files = {}
        for name in DATA_FILES:
            f = os.path.join(d, name)
            files[name] = {
                "exists": os.path.exists(f),
                "size": os.path.getsize(f) if os.path.exists(f) else 0,
                "mtime": _mtime(f),
            }
        return {"path": d, "files": files}

    return {
        "mode": "packaged" if is_frozen() else "dev",
        "primary": stat(primary),
        "mirror": stat(secondary),
        "sync_actions": actions or [],
    }
