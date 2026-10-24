# 发行包 · 提示词增强器

本目录存放 **提示词增强器** 的 Windows x64 可运行包体（由桌面快捷方式实际指向的安装/发布目录整理而来）。

| 项目 | 内容 |
| --- | --- |
| 版本 | `2026.10.24` |
| 平台 | Windows x64 |
| 包体路径 | `release/2026.10.24/prompt-enhancer-2026.10.24-win-x64/` |
| 文件数 | 72 |
| 体积 | 约 24.0 MB |

## 运行方式

双击 `PromptEnhancer.exe`

## 校验完整性

```bash
cd release
sha256sum -c SHA256SUMS.txt
```

Windows PowerShell：

```powershell
Get-Content release\SHA256SUMS.txt | ForEach-Object {
  $h, $p = $_ -split '  ', 2
  if ((Get-FileHash $p -Algorithm SHA256).Hash -ne $h.ToUpper()) { "MISMATCH $p" }
}
```

## 关于 提示词增强器

本地提示词优化工具。

## 未纳入的内容

本地用户配置 `data/` 未纳入。

以上目录属于开发环境、运行期缓存或大体积模型权重，不影响程序本体运行。
