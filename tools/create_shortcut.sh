#!/usr/bin/env bash
# ============================================================================
#  PromptEnhancer - 一键创建桌面快捷方式（macOS / Linux）
#
#  用法：保持本文件位于解压目录的 tools/ 下，双击或执行：
#        bash tools/create_shortcut.sh
#        bash tools/create_shortcut.sh --check            # 只检查状态
#        bash tools/create_shortcut.sh --force            # 强制重写
#        bash tools/create_shortcut.sh --launch           # 创建后立即启动
#        bash tools/create_shortcut.sh --name "自定义名"    # 换名（避开用户自建同名文件）
#        bash tools/create_shortcut.sh --root "/path/to/PromptEnhancer"   # 指定程序根目录（排错）
#        bash tools/create_shortcut.sh --desktop "/path/to/desktop"       # 指定桌面目录（自测）
#
#  行为：自动以本脚本所在目录的上一级作为「解压根目录」，不写死绝对路径；
#        优先指向 PromptEnhancer 可执行文件，没有则退回 python3 launcher.py；
#        重复执行只更新同一个文件，不会产生重复快捷方式；无需管理员权限。
#  退出码：0 成功/已存在，1 失败，2 系统不支持
# ============================================================================
set -u

APP_NAME="提示词增强器"
COMMAND_NAME="提示词增强器.command"
DESKTOP_ENTRY="prompt-enhancer.desktop"
# 与 create_shortcut.py 的 UNIX_MARK 保持一致，两个实现才能互相识别各自创建的启动器
UNIX_MARK="# made-by-prompt-enhancer"

# 提前定义 fail：后面的参数校验会用到，bash 逐行执行，定义必须在使用之前
fail() {
    echo "【${APP_NAME}】无法创建桌面快捷方式" >&2
    echo "----------------------------------------" >&2
    printf '%b\n' "$1" >&2   # %b 让 \n 真正换行，echo 在多数 shell 不解释转义
    exit 1
}

CHECK=0
FORCE=0
LAUNCH=0
ROOT_OVERRIDE=""
DESKTOP_OVERRIDE=""
NAME_OVERRIDE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --check)   CHECK=1 ;;
        --force)   FORCE=1 ;;
        --launch)  LAUNCH=1 ;;
        --root)    shift; ROOT_OVERRIDE="${1:-}" ;;
        --desktop) shift; DESKTOP_OVERRIDE="${1:-}" ;;
        --name)    shift; NAME_OVERRIDE="${1:-}" ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "未知参数：$1" >&2; exit 1 ;;
    esac
    shift
done

# 名称只允许文件名，拒绝路径分隔符，防止写出到桌面之外
if [ -n "$NAME_OVERRIDE" ]; then
    # 去掉首尾空白，避免生成带空格的怪异文件名
    NAME_OVERRIDE="$(printf '%s' "$NAME_OVERRIDE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    case "$NAME_OVERRIDE" in
        ""|*/*|*\\*|.|..) fail "快捷方式名称不合法（只能是文件名，不能包含路径或全空白）" ;;
    esac
fi

# 与 Python 版一致：自定义名也按平台补全后缀，否则桌面环境不识别
effective_name() {
    local default_name="$1"
    local n="${NAME_OVERRIDE:-$default_name}"
    case "$(uname -s)" in
        Darwin) case "$n" in *.command) ;; *) n="$n.command" ;; esac ;;
        Linux)  case "$n" in *.desktop) ;; *) n="$n.desktop" ;; esac ;;
    esac
    printf '%s' "$n"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 脚本位于 <根目录>/tools/ → 根目录为上一级
if [ "$(basename "$SCRIPT_DIR")" = "tools" ]; then
    ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    ROOT="$SCRIPT_DIR"
fi
if [ -n "$ROOT_OVERRIDE" ]; then
    [ -d "$ROOT_OVERRIDE" ] || { echo "指定的程序根目录不存在：$ROOT_OVERRIDE" >&2; exit 1; }
    ROOT="$(cd "$ROOT_OVERRIDE" && pwd)"
fi

# ---- 定位主程序 ---------------------------------------------------------- #
detect_target() {
    local exe=""
    if [ -f "$ROOT/PromptEnhancer" ] && [ -x "$ROOT/PromptEnhancer" ]; then
        exe="$ROOT/PromptEnhancer"
    elif [ -d "$ROOT/PromptEnhancer.app" ]; then
        exe="$ROOT/PromptEnhancer.app"
    else
        # 与 Python 版一致：跳过卸载/安装程序，避免把 unins000.exe 当成主程序
        for c in "$ROOT"/*.exe "$ROOT"/bin/*; do
            [ -f "$c" ] || continue
            local base
            base="$(basename "$c")"
            case "$base" in unins*|*uninstall*|*setup*|*installer*) continue ;; esac
            exe="$c" && break
        done
    fi
    if [ -n "$exe" ]; then
        TARGET="$exe"; ARGS=""; PYMODE=0; return
    fi
    if [ -f "$ROOT/launcher.py" ]; then
        PY="$(command -v python3 || command -v python)"
        [ -n "$PY" ] || fail "根目录中没有可执行文件，且系统未安装 python3：\n  $ROOT"
        # 给 launcher 路径加引号，含空格目录（如 "My App"）下才不会被拆词；与 Python 版一致
        TARGET="$PY"; ARGS="\"$ROOT/launcher.py\""; PYMODE=1; return
    fi
    fail "在根目录中没有找到可启动的主程序：\n  $ROOT\n期望存在 PromptEnhancer（可执行）、PromptEnhancer.app 或 launcher.py。"
}

PYMODE=0
TARGET=""; ARGS=""
detect_target

ICON=""
for p in "$ROOT/assets/icon.png" "$ROOT/assets/icon.icns" "$ROOT/_internal/assets/icon.png"; do
    [ -f "$p" ] && ICON="$p" && break
done

# ---- 定位桌面目录 -------------------------------------------------------- #
if [ -n "$DESKTOP_OVERRIDE" ]; then
    DESKTOP="$DESKTOP_OVERRIDE"
elif [ "$(uname -s)" = "Darwin" ]; then
    DESKTOP="$HOME/Desktop"
else
    DESKTOP="$HOME/Desktop"
    if [ -f "$HOME/.config/user-dirs.dirs" ]; then
        # shellcheck disable=SC1090
        . "$HOME/.config/user-dirs.dirs" 2>/dev/null || true
        [ -n "${XDG_DESKTOP_DIR:-}" ] && DESKTOP="${XDG_DESKTOP_DIR/\$HOME/$HOME}"
    fi
    [ -d "$DESKTOP" ] || DESKTOP="$HOME"
fi
[ -d "$DESKTOP" ] || fail "桌面目录不存在或不可访问：$DESKTOP"

# ---- --check：只报告状态，不写入任何文件 -------------------------------- #
check_path() {
    local p="$1"
    if [ ! -f "$p" ]; then
        echo "【${APP_NAME}】桌面快捷方式尚未创建：$p"
        return 0
    fi
    if grep -qF "$UNIX_MARK" "$p" 2>/dev/null; then
        # 用带引号的完整目标匹配，避免 /path/App 前缀误匹配 /path/App-old
        if grep -qF "\"$TARGET\"" "$p" 2>/dev/null; then
            echo "【${APP_NAME}】桌面快捷方式已存在且指向正确：$p"
        else
            echo "【${APP_NAME}】桌面快捷方式已存在但指向不正确：$p"
        fi
    else
        echo "【${APP_NAME}】桌面已有同名文件，但不是本产品创建的，未改动：$p"
    fi
}

if [ "$CHECK" = "1" ]; then
    if [ "$(uname -s)" = "Darwin" ]; then
        check_path "$DESKTOP/$(effective_name "$COMMAND_NAME")"
    else
        check_path "$DESKTOP/$(effective_name "$DESKTOP_ENTRY")"
    fi
    exit 0
fi

# ---- 生成 --------------------------------------------------------------- #
write_file() {  # write_file <路径> <内容>
    # 覆盖已有文件时先备份到 data/shortcut_backup/，与 Python 版行为一致
    if [ -f "$1" ]; then
        local bdir="$ROOT/data/shortcut_backup"
        local base
        mkdir -p "$bdir" 2>/dev/null || true
        base="$(basename "$1")"
        # 桌面副本与应用菜单副本同名，按 basename 备份会互相覆盖；加目录前缀区分
        case "$1" in */applications/*) base="menu-$base" ;; *) base="desktop-$base" ;; esac
        cp -p "$1" "$bdir/$base" 2>/dev/null || true
    fi
    printf '%s' "$2" > "$1" || fail "没有写入权限：$1"
    chmod +x "$1" 2>/dev/null || true
}

if [ "$(uname -s)" = "Darwin" ]; then
    OUT="$DESKTOP/$(effective_name "$COMMAND_NAME")"
    BODY="#!/bin/bash
# $UNIX_MARK
cd \"$ROOT\" || exit 1
exec \"$TARGET\" $ARGS \"\$@\"
"
    if [ -f "$OUT" ]; then
        # 先判归属：没有本产品标记的同名文件一律当作用户自建，绝不覆盖
        if ! grep -qF "$UNIX_MARK" "$OUT" 2>/dev/null; then
            fail "桌面已有同名启动器，但它不是本产品创建的，为避免误删未做改动；可用 --name 换名创建。\n  $OUT"
        fi
        if [ "$FORCE" = "0" ] && grep -qF "\"$TARGET\"" "$OUT" 2>/dev/null; then
            echo "【${APP_NAME}】桌面启动器已存在且指向正确，未重复创建：$OUT"
            exit 0
        fi
    fi
    write_file "$OUT" "$BODY"
    # 若同时提供 .app，再尝试创建一个 Finder 别名（失败不影响主流程）
    if [ -d "$ROOT/PromptEnhancer.app" ]; then
        osascript -e "tell application \"Finder\" to make alias file to POSIX file \"$ROOT/PromptEnhancer.app\" at POSIX file \"$DESKTOP\"" \
            >/dev/null 2>&1 && echo "（已在桌面创建 Finder 别名）"
    fi
    # 去掉 quarantine 属性，避免首次双击被 Gatekeeper 拦截
    xattr -d com.apple.quarantine "$OUT" 2>/dev/null || true
    echo "【${APP_NAME}】已创建桌面启动器：$OUT"
    RESULT="$OUT"
else
    BODY="[Desktop Entry]
Type=Application
Version=1.0
Name=${APP_NAME}
Comment=本地提示词优化工具（数据不出本机）
$UNIX_MARK
Exec=\"${TARGET}\" ${ARGS}
Path=${ROOT}
Icon=${ICON}
Terminal=false
Categories=Utility;Development;
StartupNotify=true
"
    OUT="$DESKTOP/$(effective_name "$DESKTOP_ENTRY")"
    if [ -f "$OUT" ] && ! grep -qF "$UNIX_MARK" "$OUT" 2>/dev/null; then
        fail "桌面已有同名快捷方式，但它不是本产品创建的，为避免误删未做改动；可用 --name 换名创建。\n  $OUT"
    fi
    # 与 macOS 分支一致：已存在且指向正确、且未指定 --force 时不重复写入
    if [ "$FORCE" = "0" ] && [ -f "$OUT" ] \
       && grep -qF "$UNIX_MARK" "$OUT" 2>/dev/null \
       && grep -qF "\"$TARGET\"" "$OUT" 2>/dev/null; then
        echo "【${APP_NAME}】桌面快捷方式已存在且指向正确，未重复创建：$OUT"
        exit 0
    fi
    write_file "$OUT" "$BODY"
    MENU="$HOME/.local/share/applications/$(effective_name "$DESKTOP_ENTRY")"
    mkdir -p "$(dirname "$MENU")" 2>/dev/null && write_file "$MENU" "$BODY" && echo "（已同时登记到应用菜单）"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1
    echo "【${APP_NAME}】已创建桌面快捷方式：$OUT"
    RESULT="$OUT"
fi

echo "----------------------------------------"
echo "程序根目录：$ROOT"
echo "桌面目录　：$DESKTOP"
echo "启动目标　：$TARGET $ARGS"
echo "图标　　　：${ICON:-（使用系统默认图标）}"

if [ "$LAUNCH" = "1" ]; then
    if [ "$(uname -s)" = "Darwin" ]; then
        open "$RESULT" 2>/dev/null && echo "已尝试启动程序。" || echo "自动启动失败，请手动双击桌面快捷方式。"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$RESULT" >/dev/null 2>&1 & echo "已尝试启动程序。"
    else
        echo "系统缺少 xdg-open，无法自动启动，请手动双击桌面快捷方式。"
    fi
fi
exit 0
