#!/usr/bin/env bash
# ============================================================================
#  PromptEnhancer - 一键创建桌面快捷方式（macOS / Linux）
#
#  用法：保持本文件位于解压目录的 tools/ 下，双击或执行：
#        bash tools/create_shortcut.sh
#        bash tools/create_shortcut.sh --check     # 只检查状态
#        bash tools/create_shortcut.sh --force     # 强制重写
#        bash tools/create_shortcut.sh --launch    # 创建后立即启动
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

CHECK=0
FORCE=0
LAUNCH=0
ROOT_OVERRIDE=""
DESKTOP_OVERRIDE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --check)   CHECK=1 ;;
        --force)   FORCE=1 ;;
        --launch)  LAUNCH=1 ;;
        --root)    shift; ROOT_OVERRIDE="${1:-}" ;;
        --desktop) shift; DESKTOP_OVERRIDE="${1:-}" ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "未知参数：$1" >&2; exit 1 ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 脚本位于 <根目录>/tools/ → 根目录为上一级
if [ "$(basename "$SCRIPT_DIR")" = "tools" ]; then
    ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    ROOT="$SCRIPT_DIR"
fi
[ -n "$ROOT_OVERRIDE" ] && ROOT="$ROOT_OVERRIDE"

fail() { echo "【${APP_NAME}】无法创建桌面快捷方式" >&2; echo "----------------------------------------" >&2; echo "$1" >&2; exit 1; }

# ---- 定位主程序 ---------------------------------------------------------- #
detect_target() {
    local exe=""
    if [ -f "$ROOT/PromptEnhancer" ] && [ -x "$ROOT/PromptEnhancer" ]; then
        exe="$ROOT/PromptEnhancer"
    elif [ -d "$ROOT/PromptEnhancer.app" ]; then
        exe="$ROOT/PromptEnhancer.app"
    else
        for c in "$ROOT"/*.exe "$ROOT"/bin/*; do
            [ -f "$c" ] && exe="$c" && break
        done
    fi
    if [ -n "$exe" ]; then
        TARGET="$exe"; ARGS=""; PYMODE=0; return
    fi
    if [ -f "$ROOT/launcher.py" ]; then
        PY="$(command -v python3 || command -v python)"
        [ -n "$PY" ] || fail "根目录中没有可执行文件，且系统未安装 python3：\n  $ROOT"
        TARGET="$PY"; ARGS="$ROOT/launcher.py"; PYMODE=1; return
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

# ---- 生成 --------------------------------------------------------------- #
write_file() {  # write_file <路径> <内容>
    printf '%s' "$2" > "$1" || fail "没有写入权限：$1"
    chmod +x "$1" 2>/dev/null || true
}

if [ "$(uname -s)" = "Darwin" ]; then
    OUT="$DESKTOP/$COMMAND_NAME"
    BODY="#!/bin/bash
cd \"$ROOT\" || exit 1
exec \"$TARGET\" $ARGS \"\$@\"
"
    if [ -f "$OUT" ] && [ "$FORCE" = "0" ]; then
        if grep -q "$TARGET" "$OUT" 2>/dev/null; then
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
Exec=\"${TARGET}\" ${ARGS}
Path=${ROOT}
Icon=${ICON}
Terminal=false
Categories=Utility;Development;
StartupNotify=true
"
    OUT="$DESKTOP/$DESKTOP_ENTRY"
    write_file "$OUT" "$BODY"
    MENU="$HOME/.local/share/applications/$DESKTOP_ENTRY"
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
    if [ "$(uname -s)" = "Darwin" ]; then open "$RESULT"; else xdg-open "$RESULT" >/dev/null 2>&1 & fi
    echo "已尝试启动程序。"
fi
exit 0
