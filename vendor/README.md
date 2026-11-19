# vendor：离线依赖

这里放“离线也能用”的依赖，避免每次上网找。

## SQLite（已内置，可直接离线用）

- 路径：`vendor/sqlite/`
- 版本：3.54.1（Windows x64）
- 内容：`sqlite3.exe`、`sqlite3.dll`、`sqlite3.def`、`sqlite3.h`
- 许可：Public Domain
- 用途：不装任何东西，直接打开 `knowledge.db`

```powershell
vendor\sqlite\sqlite3.exe C:\Users\root\.edu-dsh\learner\knowledge.db
```

Python 标准库已带 SQLite，不需要这份二进制；它是给命令行和 C/C++ 用的。

## VS Code SQLite Viewer（不提交 VSIX）

- 扩展：`qwtel.sqlite-viewer` 26.9.1
- 许可：发布者条款 **禁止再分发**，所以仓库里不放 `.vsix`
- 做法：用 `scripts/fetch-vscode-sqlite-viewer.ps1` 在一台联网机器下载，再复制到离线机器安装

```powershell
powershell -ExecutionPolicy Bypass -File scripts\fetch-vscode-sqlite-viewer.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-vendor.ps1 -InstallVsix
```

详见 `vendor/vscode/README.md`。

## 许可摘要

| 组件 | 许可 | 是否随仓库分发 |
|---|---|---|
| SQLite 3.54.1 | Public Domain | 是 |
| SQLite Viewer 26.9.1 | 发布者条款（禁止再分发） | 否，只提供下载脚本 |
