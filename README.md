# LCSC 浏览器扩展 → KiCad

在 Chrome / Edge 里浏览立创商城（szlcsc.com、lcsc.com、lcsc.cn），在商品页或搜索结果页点「导入」，
把符号、封装和 3D 模型写进指定的 KiCad 工程。不需要 KiCad 插件、WebView 或 wxPython。

```
商品页 / 搜索页
   └─ 扩展 content script（注入「导入」按钮）
        └─ 扩展 service worker ── POST http://127.0.0.1:8737/import
             └─ 本地服务（仅监听 127.0.0.1，单文件可执行文件或源码运行）
                  └─ vendor/LCSC_Kicad_import 的转换核心
                       └─ <工程>/LCSC/  + sym-lib-table / fp-lib-table
```

## 基于哪些项目

本项目是**外壳**：浏览器交互、本地服务、打包与发布。转换器没有重写，来自下列项目：

| 组成 | 来源 | 许可证 |
| --- | --- | --- |
| 符号 / 封装 / 3D 转换、工程落盘 | [silencewwh/LCSC_Kicad_import](https://github.com/silencewwh/LCSC_Kicad_import)，以 git submodule 固定在 `vendor/LCSC_Kicad_import` | GPL-3.0 |
| EasyEDA → KiCad 转换器 | [uPesy/easyeda2kicad.py](https://github.com/uPesy/easyeda2kicad.py)（镜像 [Steffen-W/easyeda2kicad.py](https://github.com/Steffen-W/easyeda2kicad.py)），随上述子模块引入 | AGPL-3.0 |
| 导入器原型 | [Steffen-W/Import-LIB-KiCad-Plugin](https://github.com/Steffen-W/Import-LIB-KiCad-Plugin)，由 LCSC_Kicad_import 改造 | GPL-3.0 |
| 浏览器扩展、本地服务、打包与发布 | 本仓库新增 | AGPL-3.0 |

本仓库以 **AGPL-3.0** 发布：发布的二进制内嵌了 AGPL-3.0 的 easyeda2kicad，源码即本仓库与
`vendor/LCSC_Kicad_import` 子模块在对应标签下的内容。署名与许可证细节见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 安装

从 Releases 下载 `LCSC-KiCad-Bridge-<版本>-<平台>.zip`，解压后包含本地服务可执行文件、
`extension/` 和使用说明。

浏览器扩展（三平台相同）：

- 已上架：从 Edge 加载项 / Chrome 应用商店安装，免开发者模式。
- 未上架：`edge://extensions` 或 `chrome://extensions` → 开发者模式 → 加载已解压 → 选 `extension/`。

**Windows**：双击 `LCSC-KiCad-Bridge.exe`，首次运行选择含 `.kicad_pro` 的工程目录（端口默认 8737）。
配置在 `%LOCALAPPDATA%\LCSCKiCadBridge\config.json`。

**macOS**（未签名，需解除隔离）：

```bash
xattr -dr com.apple.quarantine LCSC-KiCad-Bridge
chmod +x LCSC-KiCad-Bridge && ./LCSC-KiCad-Bridge
```

配置在 `~/Library/Application Support/LCSCKiCadBridge/config.json`。

**Linux**：

```bash
sudo apt install python3-tk    # 仅在需要图形选择窗口时；二进制自带 Python
chmod +x LCSC-KiCad-Bridge && ./LCSC-KiCad-Bridge
```

配置在 `${XDG_CONFIG_HOME:-~/.config}/LCSCKiCadBridge/config.json`。无桌面环境时用 `--project` 指定工程目录。

安装扩展后打开扩展选项，点「测试连接」：应显示工程目录且 `token_required: false`（默认免配对）。

## 页面上的按钮从哪来

| 页面 | 料号来源 |
| --- | --- |
| 商品详情页，如 `https://item.szlcsc.com/2040.html` | JSON-LD `Product.sku`，要求 `url` 与当前地址一致 |
| 搜索结果页，如 `https://so.szlcsc.com/global.html?k=…` | 卡片「编号」行，并与卡片 `data-custom-data.productCode` 交叉校验 |
| 任意页面 | 工具栏扩展图标 → 手动输入料号或粘贴商品页链接 |

## 命令行

```text
LCSC-KiCad-Bridge                    启动服务
LCSC-KiCad-Bridge --setup            重新选择工程目录 / 端口
LCSC-KiCad-Bridge --check            只校验配置与转换器
LCSC-KiCad-Bridge --import C1688     不开浏览器，直接导入一个料号
LCSC-KiCad-Bridge --project PATH     临时指定工程目录
LCSC-KiCad-Bridge --config PATH      指定配置文件
```

## 开发

```bash
git clone --recurse-submodules https://github.com/silencewwh/lcsc-browser-bridge.git
cd lcsc-browser-bridge
python server/bridge_server.py --config server/config.json
```

`server/config.example.json` → `server/config.json`：`port`、`project_dir`、`token`（默认空）、
`kicad_import_dir`（留空时自动使用 `vendor/LCSC_Kicad_import`）。

转换核心的回归测试在子模块里：

```bash
python -m pytest vendor/LCSC_Kicad_import/tests -q
```

## 打包

各平台分别构建，不能交叉编译：

```bash
python -m pip install pyinstaller
python tools/build_portable.py
```

产物：`dist/LCSC-KiCad-Bridge[.exe]`、`dist/extension-store.zip`、
`dist/LCSC-KiCad-Bridge-<版本>-<平台>.zip`。

## 发布流程

版本号位于 `server/bridge_server.py` 的 `VERSION` 与 `extension/manifest.json` 的 `version`。

```bash
git tag bridge-v1.2.0
git push origin bridge-v1.2.0
```

`.github/workflows/release.yml` 在 Windows / macOS / Linux 三个 runner 上分别打包，自动创建 Release，
附加三个平台压缩包、`extension-store.zip` 与 `SHA256SUMS.txt`。`workflow_dispatch` 只验证构建，不发布。

## 扩展分发

Chromium 稳定版不允许免开发者模式安装未上架扩展，因此「点一下就能用」需要上架：

- Edge 加载项：免费，个人 Microsoft 账号即可，上传 `extension-store.zip`。
- Chrome 应用商店：一次性 5 美元注册费，同一份包。

## 安全

- 只监听 `127.0.0.1`；`/import` 仅接受 `chrome-extension://`、`edge-extension://` Origin 或无 Origin 的本地调用。
- `config.json` 的 `token` 非空时启用共享密钥；默认留空，无需配对。
- 只写入配置的 `project_dir`（路径约束由转换器执行）；`/health` 会返回工程路径，每条请求记录耗时。

## 故障排查

- 没有按钮：详情页等 JSON-LD 就绪（1–2 秒）；搜索页需要卡片「编号」行；改版后用工具栏手动导入。
- `本机服务要求 token`：清空 `config.json` 的 `token`，或把同一值填进扩展选项。
- 连接被拒绝：确认服务窗口仍在运行，扩展 endpoint 的端口与配置一致。
- 端口占用：`--setup` 换端口，扩展选项同步修改 endpoint。
- macOS 提示「无法验证开发者」：执行 `xattr -dr com.apple.quarantine`。
- 首次运行没弹窗（终端 / CI / 管道）：用 `--project <工程目录>` 或 `--setup`。
