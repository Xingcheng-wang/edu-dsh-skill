# VS Code SQLite Viewer（不随仓库分发）

扩展：**SQLite Viewer** 26.9.1，publisher `qwtel`。

- Marketplace：https://marketplace.visualstudio.com/items?itemName=qwtel.sqlite-viewer
- 发布者条款：**禁止再分发**（No Redistribution）。  
  因此本仓库**不提交** `.vsix` 文件；只提供下载/安装脚本。

## 在线安装

```powershell
code --install-extension qwtel.sqlite-viewer@26.9.1
```

## 离线安装（推荐流程）

在一台能联网的机器上：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\fetch-vscode-sqlite-viewer.ps1 -Version 26.9.1
```

它会把 VSIX 下载到：

```
vendor\vscode\sqlite-viewer-26.9.1.vsix
```

把整个仓库目录复制到离线机器，然后：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-vendor.ps1 -InstallVsix
```

或者直接：

```powershell
code --install-extension vendor\vscode\sqlite-viewer-26.9.1.vsix
```

## 版本与校验

- 版本：`26.9.1`
- 下载后脚本会打印 SHA256；可用 `Get-FileHash` 复核。
- 本仓库抓取到的 26.9.1 VSIX SHA256：
  `00434403271d83eeae0ae164fd3cf55f256fbca12267a50425fc3b454f9c4a52`
- VSIX 被 `.gitignore` 忽略（`vendor/vscode/*.vsix`），避免误提交。

## 为什么不在仓库里

扩展发布者条款明确写着：

> No Redistribution: You may not redistribute the Extension in any form.

把 `.vsix` 放进公开仓库属于再分发，和条款冲突。脚本下载是“你自己安装”，不是仓库分发。

如果你想要一个**允许再分发**的替代扩展，可以换用 MIT 许可的 SQLite 查看器；告诉我，我再评估。
