@echo off
rem ============================================================================
rem  PromptEnhancer - 中文名一键入口（与 CreateShortcut.bat 等价）
rem  保留中文文件名是为了解压后最显眼；实际逻辑集中在 CreateShortcut.bat，
rem  避免两份脚本各自维护导致修改遗漏。
rem ============================================================================
call "%~dp0CreateShortcut.bat" %*
exit /b %ERRORLEVEL%
