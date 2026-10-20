#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提示词增强器 - 本地轻量 Web 服务

仅使用 Python 标准库实现（无第三方依赖）：
  - 静态页面托管
  - 配置读写（推理服务地址 / 模型 / 采样参数 / 系统提示词模板）
  - 推理服务探测：Ollama 原生接口 与 OpenAI 兼容接口（llama.cpp、vLLM、LM Studio 等）
  - SSE 流式优化接口
  - 优化历史记录（SQLite）：检索 / 复用 / 删除

全程本地运行，默认仅监听 127.0.0.1，不向任何外部地址发送数据。
"""

import argparse
import http.server
import json
import os
import socketserver
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import appdata  # noqa: E402
import shortcuts  # noqa: E402

BASE_DIR = appdata.app_root()          # 可执行文件 / 入口脚本所在目录
BUNDLE_DIR = appdata.bundle_root()     # 静态资源目录（打包后为 _MEIPASS）
WEB_DIR = os.path.join(BUNDLE_DIR, "web")
DATA_DIR, MIRROR_DIR = appdata.resolve_data_dirs()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
DB_PATH = os.path.join(DATA_DIR, "history.db")
UI_STATE_PATH = os.path.join(DATA_DIR, "ui_state.json")
SYNC_ACTIONS = []
APP_URL = "http://127.0.0.1:8756/"

DEFAULT_SYSTEM_TEMPLATE = """你是一位专业的提示词工程专家，负责把用户给出的原始提示词重写为高质量、可直接投喂给 AI 的提示词。

【核心原则】
1. 忠实原意：完整保留用户原有的意图、任务目标与全部已给出的约束条件（字数、风格、技术栈、禁用项、角色设定等），不得删改、弱化或曲解。
2. 只做减法与补全：删除寒暄客套、重复啰嗦、情绪化与无关表述；严禁擅自新增用户未提出的需求、假设、步骤或限制。
3. 消除歧义：把含糊指代、口语化表达改写为准确、可衡量、无歧义的专业描述。
4. 合理补全：当缺少任务背景、目标受众、输出格式、评判标准等关键信息时，用占位符（如 [请补充：目标读者]）提示补充，绝不编造具体内容。
5. 结构化：用清晰层级组织内容（必要时使用「角色 / 背景 / 任务 / 约束 / 输出格式」等短标题或编号），避免大段无结构文字。
6. 语言一致：输出语言必须与用户输入的原始提示词语言保持一致；用户用中文写就输出中文，用英文写就输出英文。
7. 原样保留：原文中出现的代码、变量名、路径、URL、数据、专有名词必须逐字保留，不得改写或省略。
8. 缺一不可：原文中每一条明确约束都必须出现在优化结果中，宁可啰嗦也不能遗漏约束。

【输出要求】
- 只输出优化后的提示词正文。
- 不要输出任何解释、分析、前后缀说明，不要使用 ``` 代码块围栏，不要出现「优化后的提示词如下」这类引导语。"""

PRESETS = [
    {
        "key": "general",
        "name": "通用优化",
        "desc": "保留原意、去除冗余、补全缺失上下文与输出格式",
        "instruction": "按通用标准优化：明确任务目标、补全缺失背景与输出格式要求，保持在合理长度内，不过度展开。",
    },
    {
        "key": "code",
        "name": "代码编写",
        "desc": "补全语言/框架/版本、输入输出契约、边界与错误处理",
        "instruction": (
            "侧重代码场景：补全编程语言与框架版本、运行环境、输入输出契约（函数签名 / 参数类型 / 返回结构）、"
            "边界条件与异常处理的明确要求、代码风格与注释规范。"
            "输出格式要求中必须明确「给出完整可运行代码」以及是否需要附带使用示例与复杂度说明。"
        ),
    },
    {
        "key": "doc",
        "name": "文档撰写",
        "desc": "明确文档类型、目标读者、篇幅结构与语气风格",
        "instruction": (
            "侧重文档场景：补全文档类型（方案 / 报告 / 说明 / 周报等）、目标读者与阅读场景、篇幅与章节结构、"
            "语气与书面风格、术语一致性要求，以及标题层级 / 列表 / 表格等排版格式要求。"
        ),
    },
    {
        "key": "data",
        "name": "数据分析",
        "desc": "明确数据来源、指标口径、分析方法与结论形式",
        "instruction": (
            "侧重数据分析场景：补全数据来源与字段含义、分析目标与指标口径（计算方式需明确）、"
            "适用的统计或分析方法、缺失值与异常值处理约定，以及结论呈现形式（要点结论 / 表格 / 图表建议）。"
        ),
    },
    {
        "key": "translate",
        "name": "翻译润色",
        "desc": "明确源语言/目标语言、术语表、风格与格式保留",
        "instruction": (
            "侧重翻译与润色场景：明确源语言与目标语言、专业术语对照表、语气风格（正式 / 口语 / 学术 / 文学）、"
            "需要原样保留的专有名词与格式（换行、列表、代码块、标点），以及是否需要逐段对照输出或给出修改说明。"
        ),
    },
]

PRESET_MAP = {p["key"]: p for p in PRESETS}

DEFAULT_CONFIG = {
    "endpoint": "http://127.0.0.1:11434",
    "api": "auto",          # auto | ollama | openai
    "model": "",
    "api_key": "",
    "temperature": 0.3,
    "max_tokens": 1024,
    "timeout": 180,
    "system_template": DEFAULT_SYSTEM_TEMPLATE,
}

_config_lock = threading.Lock()

# 本地推理服务直连：忽略系统 / 环境变量中的 HTTP 代理，避免被代理拦截
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def local_open(req, timeout):
    return _NO_PROXY_OPENER.open(req, timeout=timeout)


# --------------------------------------------------------------------------- #
# 配置与存储
# --------------------------------------------------------------------------- #
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    with _config_lock:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    appdata.mirror(DATA_DIR, MIRROR_DIR)
    return merged


DEFAULT_UI_STATE = {
    "preset": "general",
    "extra": "",
    "extra_enabled": False,
    "split_ratio": 0.5,
    "window": {},
    "drawer": "",
    "draft": "",
}


def load_state():
    state = dict(DEFAULT_UI_STATE)
    try:
        with open(UI_STATE_PATH, "r", encoding="utf-8") as f:
            state.update(json.load(f))
    except Exception:
        pass
    return state


def save_state(patch):
    state = load_state()
    state.update(patch or {})
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(UI_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    appdata.mirror(DATA_DIR, MIRROR_DIR)
    return state


def db_conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def db_init():
    conn = db_conn()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                preset TEXT,
                model TEXT,
                temperature REAL,
                max_tokens INTEGER,
                source TEXT,
                result TEXT
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_time ON history(created_at DESC)")
        conn.commit()
    finally:
        conn.close()


def history_add(row):
    conn = db_conn()
    try:
        cur = conn.execute(
            "INSERT INTO history(created_at, preset, model, temperature, max_tokens, source, result)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                row["created_at"], row.get("preset", ""), row.get("model", ""),
                row.get("temperature"), row.get("max_tokens"),
                row.get("source", ""), row.get("result", ""),
            ),
        )
        conn.commit()
        hid = cur.lastrowid
    finally:
        conn.close()
    appdata.mirror(DATA_DIR, MIRROR_DIR)
    return hid


def history_search(q="", limit=200):
    conn = db_conn()
    try:
        sql = "SELECT * FROM history"
        args = []
        if q:
            sql += " WHERE source LIKE ? OR result LIKE ? OR preset LIKE ?"
            like = "%" + q + "%"
            args = [like, like, like]
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def history_delete(hid):
    conn = db_conn()
    try:
        conn.execute("DELETE FROM history WHERE id=?", (hid,))
        conn.commit()
    finally:
        conn.close()
    appdata.mirror(DATA_DIR, MIRROR_DIR)


def history_clear():
    conn = db_conn()
    try:
        conn.execute("DELETE FROM history")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='history'")
        conn.commit()
    finally:
        conn.close()
    appdata.mirror(DATA_DIR, MIRROR_DIR)


# --------------------------------------------------------------------------- #
# 推理服务探测
# --------------------------------------------------------------------------- #
def normalize_endpoint(endpoint, api_mode="auto"):
    """返回 (base_url, 强制的 api 类型或 None)"""
    e = (endpoint or "").strip().rstrip("/")
    if not e:
        return None, None
    if not e.startswith(("http://", "https://")):
        e = "http://" + e
    low = e.lower()
    force = None
    if low.endswith("/v1"):
        force = "openai"
        e = e[:-3]
    elif api_mode in ("ollama", "openai"):
        force = api_mode
    return e, force


def _http_json(url, timeout=5, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with local_open(req, timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw)


def probe(base, api_mode="auto", timeout=5):
    """探测推理服务：返回 (ok, api, models, message)"""
    order = []
    if api_mode == "ollama":
        order = ["ollama"]
    elif api_mode == "openai":
        order = ["openai"]
    else:
        order = ["ollama", "openai"]

    errors = []
    for kind in order:
        try:
            if kind == "ollama":
                data = _http_json(base + "/api/tags", timeout=timeout)
                models = [m.get("name") or m.get("model") for m in (data.get("models") or [])]
                models = [m for m in models if m]
                return True, "ollama", models, "已连接到 Ollama 服务"
            else:
                headers = {}
                data = _http_json(base + "/v1/models", timeout=timeout, headers=headers)
                models = [m.get("id") or m.get("name") for m in (data.get("data") or [])]
                models = [m for m in models if m]
                return True, "openai", models, "已连接到 OpenAI 兼容服务"
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                errors.append("%s：需要鉴权（HTTP %s）" % ("Ollama" if kind == "ollama" else "OpenAI 兼容", exc.code))
            else:
                errors.append("%s：HTTP %s" % ("Ollama" if kind == "ollama" else "OpenAI 兼容", exc.code))
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            errors.append("%s：%s" % ("Ollama" if kind == "ollama" else "OpenAI 兼容", reason))
        except json.JSONDecodeError:
            errors.append("响应不是合法 JSON")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    return False, None, [], "；".join(errors) or "未能识别推理服务类型"


def friendly_error(msg):
    m = (msg or "").lower()
    if "refused" in m or "拒绝" in msg or "10061" in msg or "111" in m:
        return "无法连接推理服务（连接被拒绝）。请确认本地推理服务已启动，且地址与端口填写正确。"
    if "timed out" in m or "timeout" in m or "超时" in msg:
        return "连接推理服务超时。请确认服务已启动、地址正确，或适当调大超时时间。"
    if "not found" in m or "does not exist" in m:
        return "模型不存在或未加载。请先在推理服务中拉取/加载该模型（如 ollama pull <模型名>）。"
    return msg


# --------------------------------------------------------------------------- #
# 提示词组装与推理调用
# --------------------------------------------------------------------------- #
def build_system_prompt(cfg, preset_key, extra):
    parts = [(cfg.get("system_template") or DEFAULT_SYSTEM_TEMPLATE).strip()]
    preset = PRESET_MAP.get(preset_key)
    if preset:
        parts.append("【本次场景预设：%s】\n%s" % (preset["name"], preset["instruction"]))
    if extra and extra.strip():
        parts.append("【用户补充要求（优先于其他建议，但仍不得违背上述核心原则）】\n%s" % extra.strip())
    parts.append("待优化的原始提示词会在下一条消息中给出，请严格按上述规则输出优化后的提示词正文。")
    return "\n\n".join(parts)


def build_user_prompt(raw):
    return "请优化下面这段原始提示词：\n\n<原始提示词>\n%s\n</原始提示词>" % raw


def build_payload(api, model, system, user, temperature, max_tokens, stream=True):
    if api == "ollama":
        return {
            "model": model,
            "system": system,
            "prompt": user,
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }


def stream_upstream(api, base, payload, api_key, timeout):
    """产出文本增量；在网络/协议出错时抛出 Exception。"""
    if api == "ollama":
        url = base + "/api/generate"
    else:
        url = base + "/v1/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    resp = local_open(req, timeout)
    try:
        for raw_line in resp:
            if isinstance(raw_line, bytes):
                line = raw_line.decode("utf-8", "replace").strip()
            else:
                line = str(raw_line).strip()
            if not line:
                continue
            if api == "ollama":
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    raise RuntimeError(str(obj["error"]))
                chunk = obj.get("response") or ""
                if chunk:
                    yield chunk
                if obj.get("done"):
                    break
            else:
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    err = obj["error"]
                    raise RuntimeError(err.get("message") if isinstance(err, dict) else str(err))
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                chunk = delta.get("content") or ""
                if chunk:
                    yield chunk
    finally:
        try:
            resp.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# HTTP 服务
# --------------------------------------------------------------------------- #
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "PromptEnhancer/1.0"

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # ---------- 工具 ----------
    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, relpath, ctype):
        path = os.path.join(WEB_DIR, relpath)
        if not os.path.isfile(path):
            self._json({"error": "not found"}, 404)
            return
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._file("index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self._file("app.js", "application/javascript; charset=utf-8")
        if path == "/styles.css":
            return self._file("styles.css", "text/css; charset=utf-8")
        if path == "/api/health":
            return self._json({"ok": True, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        if path == "/api/config":
            cfg = load_config()
            cfg["_presets"] = PRESETS
            cfg["_app"] = {
                "packaged": appdata.is_frozen(),
                "exe": sys.executable if appdata.is_frozen() else "",
                "url": APP_URL,
                "data": appdata.data_info(DATA_DIR, MIRROR_DIR, SYNC_ACTIONS),
            }
            return self._json(cfg)
        if path == "/api/presets":
            return self._json({"presets": PRESETS})
        if path == "/api/models":
            return self._handle_models()
        if path == "/api/history":
            q = self._query("q")
            return self._json({"items": history_search(q)})
        if path == "/api/system-template/default":
            return self._json({"system_template": DEFAULT_SYSTEM_TEMPLATE})
        if path == "/api/state":
            return self._json({"ok": True, "state": load_state()})
        if path == "/api/shortcut":
            return self._json(shortcuts.inspect())
        if path == "/api/datainfo":
            return self._json(appdata.data_info(DATA_DIR, MIRROR_DIR, SYNC_ACTIONS))
        return self._json({"error": "not found"}, 404)

    def _query(self, key):
        if "?" not in self.path:
            return ""
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        return (qs.get(key) or [""])[0]

    def _handle_models(self):
        cfg = load_config()
        base, force = normalize_endpoint(cfg.get("endpoint"), cfg.get("api", "auto"))
        if not base:
            return self._json({"ok": False, "models": [], "message": "尚未配置推理服务地址"})
        ok, api, models, message = probe(base, force, timeout=5)
        return self._json({
            "ok": ok, "api": api, "models": models, "base": base,
            "message": message if ok else friendly_error(message),
            "configured_model": cfg.get("model", ""),
        })

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        body = self._body()
        if path == "/api/config":
            allowed = ["endpoint", "api", "model", "api_key", "temperature", "max_tokens", "timeout", "system_template"]
            patch = {k: body.get(k) for k in allowed if k in body}
            cfg = save_config(patch)
            return self._json({"ok": True, "config": {k: cfg[k] for k in allowed}})
        if path == "/api/models":
            base, force = normalize_endpoint(body.get("endpoint") or "", body.get("api") or "auto")
            if not base:
                return self._json({"ok": False, "models": [], "message": "请填写推理服务地址"})
            ok, api, models, message = probe(base, force, timeout=float(body.get("timeout") or 6))
            return self._json({"ok": ok, "api": api, "models": models, "base": base,
                               "message": message if ok else friendly_error(message)})
        if path == "/api/optimize":
            return self._handle_optimize(body)
        if path == "/api/state":
            return self._json({"ok": True, "state": save_state(body.get("state") or {})})
        if path == "/api/shortcut":
            res = shortcuts.ensure(create=bool(body.get("create", True)))
            if body.get("launch") and res["status"] in ("created", "updated", "exists"):
                res["launch"] = shortcuts.launch(res.get("path"))
            return self._json(res)
        if path == "/api/launch":
            res = shortcuts.launch()
            if not res["ok"]:
                try:
                    webbrowser.open(APP_URL)
                    res["fallback_url"] = APP_URL
                except Exception:  # noqa: BLE001
                    pass
            return self._json(res)
        if path == "/api/history":
            row = {
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "preset": body.get("preset", ""),
                "model": body.get("model", ""),
                "temperature": body.get("temperature"),
                "max_tokens": body.get("max_tokens"),
                "source": body.get("source", ""),
                "result": body.get("result", ""),
            }
            if not row["source"] and not row["result"]:
                return self._json({"ok": False, "message": "内容为空"}, 400)
            return self._json({"ok": True, "id": history_add(row)})
        return self._json({"error": "not found"}, 404)

    # ---------- DELETE ----------
    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/history":
            history_clear()
            return self._json({"ok": True})
        if path.startswith("/api/history/"):
            try:
                hid = int(path.rsplit("/", 1)[1])
            except ValueError:
                return self._json({"ok": False}, 400)
            history_delete(hid)
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)

    # ---------- SSE 优化 ----------
    def _handle_optimize(self, body):
        cfg = load_config()
        raw = (body.get("prompt") or "").strip()
        if not raw:
            return self._json({"ok": False, "message": "请先输入需要优化的原始提示词"}, 400)

        endpoint = body.get("endpoint") or cfg.get("endpoint") or ""
        api_mode = body.get("api") or cfg.get("api") or "auto"
        model = (body.get("model") or cfg.get("model") or "").strip()
        temperature = float(body.get("temperature") if body.get("temperature") is not None else cfg.get("temperature", 0.3))
        max_tokens = int(body.get("max_tokens") or cfg.get("max_tokens") or 1024)
        timeout = float(body.get("timeout") or cfg.get("timeout") or 180)
        api_key = body.get("api_key") or cfg.get("api_key") or ""
        preset_key = body.get("preset") or "general"
        extra = body.get("extra") or ""

        base, force = normalize_endpoint(endpoint, api_mode)
        if not base:
            return self._json({"ok": False, "message": "尚未配置推理服务地址，请先在设置中填写"}, 400)

        detected_api = force
        if not detected_api:
            ok, detected_api, _models, _msg = probe(base, "auto", timeout=6)
            if not ok:
                detected_api = "openai"
        if not model:
            ok, _api, models, _msg = probe(base, detected_api, timeout=6)
            if ok and models:
                model = models[0]
            else:
                return self._json({"ok": False, "message": "尚未选择模型，请在设置中选择或填写模型名称"}, 400)

        system = build_system_prompt(cfg, preset_key, extra)
        user = build_user_prompt(raw)
        payload = build_payload(detected_api, model, system, user, temperature, max_tokens, stream=True)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emit(event, obj):
            line = "event: %s\ndata: %s\n\n" % (event, json.dumps(obj, ensure_ascii=False))
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

        started = time.time()
        try:
            emit("meta", {"api": detected_api, "model": model, "base": base})
            emit("status", {"stage": "loading", "text": "正在连接推理服务 / 加载模型…"})
            buf = []
            first = True
            for chunk in stream_upstream(detected_api, base, payload, api_key, timeout):
                if first:
                    emit("status", {"stage": "generating", "text": "模型已就绪，正在生成…"})
                    first = False
                buf.append(chunk)
                emit("delta", {"text": chunk})
            text = "".join(buf).strip()
            hid = None
            if text:
                hid = history_add({
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "preset": PRESET_MAP.get(preset_key, {}).get("name", preset_key),
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "source": raw,
                    "result": text,
                })
            emit("done", {
                "text": text,
                "model": model,
                "elapsed": round(time.time() - started, 2),
                "history_id": hid,
            })
        except BrokenPipeError:
            return
        except Exception as exc:  # noqa: BLE001
            try:
                emit("error", {"message": friendly_error(str(exc))})
            except Exception:
                pass
        finally:
            try:
                self.wfile.flush()
            except Exception:
                pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="提示词增强器（本地运行）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8756)
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    return parser.parse_args(argv)


def run_server(host="127.0.0.1", port=8756, open_browser=True):
    """启动服务（开发入口与打包入口共用）"""
    global APP_URL
    APP_URL = "http://%s:%d/" % (host, port)
    db_init()
    load_config()
    SYNC_ACTIONS.extend(appdata.sync_pair(DATA_DIR, MIRROR_DIR))
    print("提示词增强器已启动：%s" % APP_URL)
    print("运行模式：%s" % ("打包 exe" if appdata.is_frozen() else "开发环境"))
    print("数据目录：%s" % DATA_DIR)
    if MIRROR_DIR:
        print("同步目录：%s" % MIRROR_DIR)
    if SYNC_ACTIONS:
        print("数据同步：%s" % "；".join(SYNC_ACTIONS))
    print("按 Ctrl+C 停止服务")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(APP_URL)).start()
    try:
        ThreadedHTTPServer((host, port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


def main(argv=None):
    args = parse_args(argv)
    run_server(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
