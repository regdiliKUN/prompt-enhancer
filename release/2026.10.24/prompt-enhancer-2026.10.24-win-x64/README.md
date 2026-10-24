# 提示词增强器 Prompt Enhancer

把口语化、冗余的原始提示词，交给**本地小模型**重写为结构清晰、约束完整、可直接使用的高质量提示词。
一个零第三方依赖的轻量本地应用：Python 标准库后端 + 原生前端，可打包为带图标的 Windows 桌面应用，
**全程在本机完成，不向任何外部地址发送数据**。

## 主要特性

- **并排输入 / 输出**：左侧粘贴原始提示词，右侧流式生成优化结果；结果可编辑、复制、迭代再优化。
- **本地小模型推理**：支持 Ollama 原生接口与 OpenAI 兼容接口（llama.cpp / LM Studio / vLLM），
  可配置温度、最大生成长度、超时；页面顶部实时显示模型加载与推理状态，未就绪时给出明确原因。
- **优化规则固化为系统提示词模板**：忠实原意与已有约束、删除寒暄与重复、用占位符补全缺失上下文、
  口语改写为结构化专业描述、输出语言与输入一致、不擅自新增需求；模板可编辑、可恢复默认。
- **场景预设**：通用优化、代码编写、文档撰写、数据分析、翻译润色，一键套用。
- **对比查看**：行级 LCS diff 标出优化前后新增 / 删除行。
- **历史记录**：每次优化自动入库，支持关键词检索、复用原文 / 结果、单条删除、清空。
- **桌面应用与一键入口**：可打包为 exe，界面右上角「一键启动 · 创建桌面快捷方式」按钮幂等创建
  桌面快捷方式并通过它启动；单实例保护，重复启动不会起第二份服务。
- **数据不丢**：偏好设置、历史记录、窗口 / 界面状态在两个数据目录间双向同步，重新打包也不会丢失。

## 快速开始

```bash
# 仅需 Python 3.9+，零第三方依赖
python server.py              # 默认 http://127.0.0.1:8756，自动打开浏览器
python launcher.py             # 与 exe 相同的启动入口（含单实例保护）
python server.py --port 9000   # 指定端口
python server.py --no-browser  # 不自动打开浏览器
```

停止服务：`Ctrl+C`。服务仅监听 `127.0.0.1`。

## 接入本地推理服务

打开页面右上角「设置」，填写推理服务地址并点击「测试连接」，会自动识别服务类型并拉取模型列表：

| 服务 | 地址示例 | 说明 |
| --- | --- | --- |
| Ollama | `http://127.0.0.1:11434` | 自动识别为 Ollama 原生接口，需先 `ollama serve` |
| llama.cpp server | `http://127.0.0.1:8080/v1` | OpenAI 兼容接口 |
| LM Studio / vLLM / LocalAI | `http://127.0.0.1:1234/v1` | OpenAI 兼容接口 |

- 接口类型可选「自动识别 / Ollama 原生 / OpenAI 兼容」，模型名称可手动填写。
- 需要鉴权的本地服务可填写 API Key（留空则不发送鉴权头）。
- 服务未启动或模型不存在时，页面顶部状态条会明确提示原因（连接被拒绝 / 超时 / 模型未找到）。

## 打包为桌面应用

```bash
python build_package.py              # 输出到 I:\workbuddyAI\prompt-enhancer\PromptEnhancer\
python build_package.py --out D:\xx  # 自定义输出目录
python build_package.py --console    # 带控制台窗口（排错用）
```

需要 PyInstaller（`pip install pyinstaller`）。产物 `PromptEnhancer\PromptEnhancer.exe`
无控制台、带应用图标，双击即启动并自动打开界面。

**一键入口**：界面右上角最醒目的蓝色按钮「一键启动 · 创建桌面快捷方式」；快捷方式尚未创建时，
工具栏下方还会显示提示横幅。点击后自动在桌面创建带图标的快捷方式并通过它启动程序。

- 幂等：重复点击不会生成重复快捷方式，明确提示「已存在，未重复创建」。
- 防误覆盖：桌面已有本应用快捷方式且目标有效时不互相覆盖；仅当原目标失效（程序被移动）才自动修复。
- 异常兼容：桌面目录不可写、WScript.Shell 被组策略禁用、PowerShell 缺失、目标缺失等情况都会给出
  可读的中文错误说明与建议，不会静默失败。
- 单实例：重复双击 exe 或快捷方式时不会启动第二个服务，只打开已运行实例的界面。
- 图标由 `tools/make_icon.py` 生成（`assets/icon.ico`），exe 与快捷方式共用，视觉一致。

## 桌面快捷方式：包体内的一键创建入口

除了界面上的按钮，包体里还内置了一个**双击即用的一键脚本**，用户解压后无需打开程序、
无需管理员权限，直接就能在桌面生成快捷方式。

### 包体中的文件位置

```
PromptEnhancer/                      ← 解压根目录（可整体移动到任意位置）
├── PromptEnhancer.exe               ← 主程序
├── 创建桌面快捷方式.bat              ← ★ 用户双击这个（中文名，最显眼）
├── CreateShortcut.bat               ← 同上，英文文件名版本
├── tools/
│   ├── create_shortcut.py           ← Windows / macOS / Linux 通用实现（仅标准库）
│   └── create_shortcut.sh           ← macOS / Linux 下的等价 shell 入口
├── assets/icon.ico                  ← 快捷方式图标（打包资源副本在 _internal/assets）
├── data/                            ← 便携数据（与 %LOCALAPPDATA% 双向同步）
└── 启动说明.txt                      ← 用户可见的步骤说明
```

### 行为约定

| 项目 | 说明 |
| --- | --- |
| 目标定位 | 不写死绝对路径：以脚本所在目录（`%~dp0`）为根，优先指向 `PromptEnhancer.exe`，没有 exe 时退回 `pythonw.exe launcher.py` |
| 名称 / 图标 / 工作目录 | 名称 `提示词增强器`，图标 `assets/icon.ico`（缺失时用 exe 自带图标），工作目录为解压根目录（保证数据目录解析正确） |
| 幂等 | 同一路径永远只有一个快捷方式；已存在且指向正确 → 提示「未重复创建」；指向不对（程序被移动 / 换版本）→ 原地覆盖更新 |
| 权限 | 只写当前用户桌面，不写 Program Files、不改注册表，普通用户权限即可 |
| 失败反馈 | 桌面不可写、组策略禁用 WScript.Shell、缺少 PowerShell、目标文件缺失等，均给出可读中文说明与处理建议；exe 模式下弹窗提示，并写入 `%LOCALAPPDATA%\PromptEnhancer\data\shortcut_result.log` |

### 手动调用

```bat
PromptEnhancer.exe --create-shortcut            :: 创建 / 更新，弹窗显示结果
PromptEnhancer.exe --create-shortcut --launch   :: 创建后立即启动程序
PromptEnhancer.exe --shortcut-status            :: 只查看状态
PromptEnhancer.exe --create-shortcut --no-dialog :: 不弹窗（脚本 / CI 用，可用环境变量 PROMPT_ENHANCER_NO_DIALOG=1 代替）
```

```bash
python tools/create_shortcut.py                 # 创建 / 更新
python tools/create_shortcut.py --check         # 只检查状态
python tools/create_shortcut.py --force         # 已正确时也强制重写
python tools/create_shortcut.py --root "D:\xx\PromptEnhancer"   # 指定根目录（排错）
python tools/create_shortcut.py --desktop "D:\tmp\desk"          # 指定桌面目录（自测）
python tools/create_shortcut.py --json          # 输出机器可读结果
```

退出码：`0` 成功或已存在，`1` 失败，`2` 系统不支持。

### macOS / Linux 等价方案

两者都不使用 `.lnk`，而是生成各自桌面环境认识的文件，逻辑与 Windows 一一对应：

```bash
bash tools/create_shortcut.sh            # 自动识别根目录并创建
bash tools/create_shortcut.sh --check    # 只检查
bash tools/create_shortcut.sh --force    # 强制重写
bash tools/create_shortcut.sh --launch   # 创建后立即启动
```

| 系统 | 生成物 | 说明 |
| --- | --- | --- |
| macOS | `~/Desktop/提示词增强器.command` | 可执行 shell 启动器，`chmod +x` 并清除 quarantine 属性，双击即可运行；若包内同时提供 `PromptEnhancer.app`，会额外用 `osascript` 在桌面建一个 Finder 别名 |
| Linux | `~/.local/share/applications/prompt-enhancer.desktop` + 桌面副本 | 标准 `.desktop` 条目（含 `Exec` / `Path` / `Icon`），桌面目录按 `XDG_DESKTOP_DIR` 自动定位，并刷新 desktop database；若只有源码则用 `python3 launcher.py` |

两者的根目录同样按脚本位置自动推算（`$(dirname $0)/..`），不依赖工作目录或绝对路径。

### 作用域：只动自己的快捷方式，绝不碰用户自建的

判定归属（`shortcuts.is_owned` / `tools/create_shortcut.py` 的 `is_owned`）满足任一条件才算「本产品创建」：

1. 快捷方式 **Description** 含归属标记「由提示词增强器创建」（新版写入时一律带上）；
2. 或 Description 以应用名开头（兼容早期版本创建的快捷方式）；
3. 或目标路径就是本程序的可执行文件 / 启动脚本（说明它本来就指向本程序）。

不符合上述条件的同名快捷方式，一律当作**用户自建**：**不创建、不覆盖、不删除**，只返回
`name_taken` 状态与提示（界面横幅 + 弹窗/日志都会说明「它指向 X，本程序不会改动它」）。
需要为本程序创建时，可用 `--name` 换一个文件名：

```bat
PromptEnhancer.exe --create-shortcut --shortcut-name "提示词增强器-2.lnk"
python tools/create_shortcut.py --name "提示词增强器-2"
```

**备份与回滚**：覆盖自己创建过的快捷方式前，会把旧文件备份到
`<数据目录>/shortcut_backup/提示词增强器.lnk`（附 `.json` 元信息）；写入失败或校验不通过时
**自动回滚**并提示「桌面快捷方式保持原样」。手动回滚：

```bat
PromptEnhancer.exe --restore-shortcut
python tools/create_shortcut.py --restore
```

### 各流程对桌面快捷方式的影响（已逐项核对）

| 流程 | 是否触碰桌面快捷方式 | 说明 |
| --- | --- | --- |
| 安装（解压 / 首次拷贝目录） | 否 | 只写目录内文件，不写桌面 |
| 首次启动 | 否 | 不会自动创建；界面顶部横幅提示可一键创建 |
| 用户主动创建（bat / 界面按钮 / exe 参数） | 仅当同名文件不存在或确认是本产品的 | 用户自建同名文件一律跳过并提示 |
| 更新 / 重新打包 | 否 | `build_package.py` 只备份恢复 `data/`，不碰桌面 |
| 下载 GitHub 包 / 换目录 | 否 | 换目录后主动点击创建，才会把**自己的**快捷方式指向更新为新路径 |
| 卸载（删除程序目录） | 否 | 本产品没有卸载器，任何代码路径都不删除桌面 .lnk；桌面图标可手动删除 |

代码层面只有两处会写入快捷方式：`shortcuts.ensure()`（界面按钮）与
`tools/create_shortcut.py`（bat / --create-shortcut），两者共用同一套归属判定 + 备份回滚；
删除操作仅存在于覆盖写入失败时的自身重建（同一路径，且前置了归属判定）。

### failed to fetch 排查

界面状态条出现「推理失败 / Failed to fetch」**不代表推理服务有问题**，而是浏览器连不上
本工具自己的后端（`http://127.0.0.1:8756`）。常见触发场景：

- 程序已退出 / 被关闭，页面还开着（最常见）；
- 程序正在重启或首次启动尚未完成；
- 端口被其他实例占用（换端口启动后页面仍是旧地址）。

现在的处理：`fetch` 网络错误统一翻译为「无法连接本工具的后端服务（程序可能已退出或正在
重启），请重新启动提示词增强器」；状态探测按 2s→4s→8s…（上限 30s）指数退避自动重试，
后端恢复后状态条自动回到「模型就绪」。

### 验证快捷方式确实能启动程序

```powershell
# 1) 看快捷方式指向：目标必须是 PromptEnhancer.exe，工作目录必须是解压根目录
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$env:USERPROFILE\Desktop\提示词增强器.lnk")
$sc.TargetPath; $sc.Arguments; $sc.WorkingDirectory; $sc.IconLocation

# 2) 双击桌面快捷方式后，确认服务真的起来了
curl http://127.0.0.1:8756/api/health

# 3) 把整个 PromptEnhancer 目录挪到别处，再双击 bat，目标应自动更新为新路径
```

脚本自带的校验：`tools/create_shortcut.py` 写完会**回读**快捷方式并比对目标，
比对不上就删除重建，仍失败才报错，因此不会出现「提示成功但其实是旧的」这种情况。

## 数据保留与同步

数据文件：偏好设置 `config.json`、使用记录 `history.db`、界面 / 窗口状态 `ui_state.json`。

- 包体运行时主目录：`%LOCALAPPDATA%\PromptEnhancer\data`
- 开发环境运行时主目录：项目内 `data/`
- 启动时按「修改时间较新者胜出」在两个目录间**双向同步**（SQLite 在线备份，不中断服务），
  每次写入后自动镜像到另一目录；重新打包、移动包体或创建快捷方式都不会丢失数据。
- 重新打包前 `build_package.py` 会把包体目录内已有的 `data/` 备份为 `data_backup_<时间戳>`，
  构建完成后原样恢复（双保险）。
- 测试用环境变量：`PROMPT_ENHANCER_DATA_DIR`、`PROMPT_ENHANCER_DESKTOP_DIR`、
  `PROMPT_ENHANCER_SHORTCUT_TARGET`。

## 数据与隐私

- 服务仅监听 `127.0.0.1`，对外请求只发往你在设置中填写的本地推理服务地址（并强制绕过系统 HTTP 代理）。
- 删除 `data/`（以及包体模式下的 `%LOCALAPPDATA%\PromptEnhancer\data`）即可清空全部本地数据。
- 仓库通过 `.gitignore` 排除 `data/`、构建产物、环境变量与编辑器配置，不会上传任何用户数据。

## 目录结构

```
prompt-enhancer/
├── server.py            # 后端：静态托管 / 配置 / 推理代理 / SSE 流式 / 历史 SQLite
├── launcher.py          # 启动入口（exe、快捷方式、开发环境共用），含单实例保护
├── appdata.py           # 数据目录解析、双向同步、写后镜像
├── shortcuts.py         # 桌面快捷方式：幂等创建 / 检查 / 启动（界面按钮用）
├── build_package.py     # PyInstaller 打包脚本（含 data 备份恢复、入口文件复制）
├── CreateShortcut.bat            # 包体一键入口（英文文件名）
├── 创建桌面快捷方式.bat           # 包体一键入口（中文文件名，最显眼）
├── .gitattributes       # 强制 bat 用 CRLF、sh/py 用 LF
├── assets/icon.ico      # 应用图标（exe 与快捷方式共用）
├── tools/
│   ├── make_icon.py     # 图标生成脚本（依赖 Pillow，仅构建期使用）
│   ├── create_shortcut.py  # 跨平台一键创建脚本（仅标准库，Windows/macOS/Linux）
│   └── create_shortcut.sh  # macOS / Linux 的等价 shell 入口
├── web/                 # 前端：index.html / styles.css / app.js（原生，无构建）
└── data/               # 运行时生成（已 gitignore）：config.json、history.db、ui_state.json
```

## 常见问题

- **模型未就绪**：确认 Ollama 已启动（`ollama serve`）且地址端口与设置一致；本机若设置了 HTTP 代理，
  后端已强制直连本地服务，无需额外处理。
- **端口被占用**：换端口启动（`--port 9000`）；重复双击 exe 会自动复用已运行实例。
- **创建快捷方式失败**：按提示检查桌面目录权限，或改用「以管理员身份运行」启动程序。
