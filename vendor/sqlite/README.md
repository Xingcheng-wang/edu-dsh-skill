# SQLite for Windows x64（离线）

版本：**3.54.1**（2026-10-16）

来源：

- https://www.sqlite.org/2026/sqlite-tools-win-x64-3540100.zip
- https://www.sqlite.org/2026/sqlite-dll-win-x64-3540100.zip
- https://www.sqlite.org/2026/sqlite-amalgamation-3540100.zip

许可证：**Public Domain**（见 `LICENSE.txt`）。

## 文件

| 文件 | 用途 |
|---|---|
| `sqlite3.exe` | 命令行 shell，可直接打开 `knowledge.db` |
| `sqlite3.dll` | Windows x64 动态库 |
| `sqlite3.def` | 生成导入库用（`lib /def:sqlite3.def /machine:x64`） |
| `sqlite3.h` | C/C++ 头文件 |
| `SHA256SUMS.txt` | 文件哈希与原始压缩包哈希 |

## 直接用

```powershell
.\sqlite3.exe C:\Users\root\.edu-dsh\learner\knowledge.db
.tables
.mode column
.headers on
SELECT id, title, type, state FROM items;
```

Python 不需要这份二进制：`import sqlite3` 是标准库，已带 SQLite。

## 校验

```powershell
Get-FileHash .\sqlite3.exe -Algorithm SHA256
```

与 `SHA256SUMS.txt` 对照。

## 来源包哈希

| 包 | SHA3-256 | SHA256 |
|---|---|---|
| tools zip | `e171f3993a992edf076746926dd52b5e2ebfabaee38818e74987e1d8112ab987` | `fb20997ade5583a5fbf1e36db7bc3c82c9416b3f314f16961e1572aa4e49487d` |
| dll zip | `c2d09c8babb9399277055c057c97a53f1ffd7c5f11d0c1f2118ffdfa39f2daa4` | `f436f53ad8f965af43f3817b42c99c0689e6787f6b7ace208fe38dab7ffc4971` |
| amalgamation zip | `92281c86e2957f9b9305890f9ac04204caa7b677cc868dc326d942689df28e30` | `0a9c8e34352dad46006aa82836d5383bff9dc6bc9ce5a60553c05aa30e6ad1f9` |
