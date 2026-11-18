# LCSC 浏览器扩展 → KiCad

在 Chrome 或 Edge 里打开立创商城（szlcsc.com、lcsc.com、lcsc.cn），在商品页或搜索结果里点「导入」，
符号、封装和可用的 3D 模型会写进指定的 KiCad 工程。不需要装 KiCad 插件，也不需要 KiCad 的 Python 环境。

```
商品页 / 搜索页
   └─ 扩展 content script：在页面上插入「导入」按钮
        └─ 扩展 service worker：POST http://127.0.0.1:8737/import
             └─ 本地服务：只监听 127.0.0.1
                  └─ vendor/LCSC_Kicad_import 里的转换核心
                       └─ <工程>/LCSC/，并在 sym-lib-table、fp-lib-table 登记 LCSC 库
```

## 基于哪些项目

本仓库只做浏览器交互、本地服务和打包；转换部分没有重写，按提交固定引入。

| 组成 | 来源 | 许可证 |
| --- | --- | --- |
| 符号、封装、3D 转换与工程落盘 | [silencewwh/LCSC_Kicad_import](https://github.com/silencewwh/LCSC_Kicad_import)，submodule 固定在 `vendor/LCSC_Kicad_import` | GPL-3.0 |
| EasyEDA → KiCad 转换器 | [uPesy/easyeda2kicad.py](https://github.com/uPesy/easyeda2kicad.py)（镜像 [Steffen-W/easyeda2kicad.py](https://github.com/Steffen-W/easyeda2kicad.py)），随上面的 submodule 引入 | AGPL-3.0 |
| 导入器原型 | [Steffen-W/Import-LIB-KiCad-Plugin](https://github.com/Steffen-W/Import-LIB-KiCad-Plugin)，LCSC_Kicad_import 由它改造而来 | GPL-3.0 |
| 浏览器扩展、本地服务、打包脚本 | 本仓库 | AGPL-3.0 |

本仓库使用 AGPL-3.0：发布的二进制包含 AGPL-3.0 的 easyeda2kicad，对应源码就是本仓库和
`vendor/LCSC_Kicad_import` 子模块在同一个标签下的内容。逐项署名见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 安装

在 Releases 下载 `LCSC-KiCad-Bridge-<版本>-<平台>.zip`，解压后是本地服务程序、`extension/` 和一份
`使用说明.txt`。先启动服务，再装扩展，两者都准备好后页面按钮才有响应。

浏览器扩展在三个平台都相同：

- 已上架：从 Edge 加载项或 Chrome 应用商店安装，不需要开发者模式。
- 未上架：打开 `edge://extensions` 或 `chrome://extensions`，启用开发者模式，选择「加载已解压的扩展程序」，
  指向 `extension/`。

Windows 下双击 `LCSC-KiCad-Bridge.exe`，首次运行会要求选择含 `.kicad_pro` 的工程目录，端口默认 8737，
配置写到 `%LOCALAPPDATA%\LCSCKiCadBridge\config.json`。

macOS 的二进制没有签名和公证，第一次运行前要解除隔离：

```bash
xattr -dr com.apple.quarantine LCSC-KiCad-Bridge
chmod +x LCSC-KiCad-Bridge
./LCSC-KiCad-Bridge
```

配置写到 `~/Library/Application Support/LCSCKiCadBridge/config.json`。

Linux：

```bash
sudo apt install python3-tk    # 只有需要图形选择窗口时才装；程序本身自带 Python
chmod +x LCSC-KiCad-Bridge
./LCSC-KiCad-Bridge
```

配置写到 `${XDG_CONFIG_HOME:-~/.config}/LCSCKiCadBridge/config.json`。没有桌面环境时用 `--project`
直接指定工程目录。

服务窗口出现 `listening on http://127.0.0.1:8737` 后保持开启。接着打开扩展选项点「测试连接」，
应该能看到工程路径和 `token_required: false`。默认不校验 token。

## 页面按钮的料号来源

| 页面 | 料号从哪来 |
| --- | --- |
| 商品详情页，如 `https://item.szlcsc.com/2040.html` | 页面 JSON-LD 里 `Product.sku`，且 `url` 要与当前地址一致 |
| 搜索结果页，如 `https://so.szlcsc.com/global.html?k=…` | 卡片「编号」行，同时与卡片 `data-custom-data.productCode` 比对，不一致就不插按钮 |
| 其他页面 | 点扩展图标，手动输入料号或粘贴商品页链接 |

搜索结果页上，按钮出现在每张卡片「加入购物车」的下面，鼠标悬停会显示要导入的料号：

![搜索结果页里的导入按钮](docs/images/search-page.png)

## 命令行

```text
LCSC-KiCad-Bridge                    启动服务
LCSC-KiCad-Bridge --setup            重新选择工程目录和端口
LCSC-KiCad-Bridge --check            只检查配置与转换器
LCSC-KiCad-Bridge --import C1688     不开浏览器，直接导入一个料号
LCSC-KiCad-Bridge --project PATH     临时指定工程目录
LCSC-KiCad-Bridge --config PATH      指定配置文件
```

## 从源码运行

```bash
git clone --recurse-submodules https://github.com/betwowt/lcsc-browser-bridge.git
cd lcsc-browser-bridge
cp server/config.example.json server/config.json   # 改 project_dir
python server/bridge_server.py --config server/config.json
```

`server/config.json` 的字段：

- `port`：本地服务端口，默认 8737。
- `project_dir`：KiCad 工程目录，要已存在且包含 `.kicad_pro`。
- `token`：留空表示不校验；填了之后扩展选项里要填同一值。
- `kicad_import_dir`：留空时使用 `vendor/LCSC_Kicad_import`。

转换核心的回归测试在子模块里：`python -m pytest vendor/LCSC_Kicad_import/tests -q`。

## 打包

三个平台各自构建，不能交叉编译。需要 PyInstaller：

```bash
python -m pip install pyinstaller
python tools/build_portable.py
```

产物在 `dist/`：`LCSC-KiCad-Bridge[.exe]`、`extension-store.zip`、`LCSC-KiCad-Bridge-<版本>-<平台>.zip`。
只想更新扩展包时加 `--skip-exe`。

## 发布

版本号在 `server/bridge_server.py` 的 `VERSION` 和 `extension/manifest.json` 的 `version`，两处要一致。

```bash
git tag bridge-v1.2.0
git push origin bridge-v1.2.0
```

`.github/workflows/release.yml` 会在 Windows、macOS、Linux 三个 runner 上分别打包，然后创建 Release，
附上三个平台压缩包、`extension-store.zip` 和 `SHA256SUMS.txt`。用 `workflow_dispatch` 手动跑只验证构建，
不会发布。

扩展要免开发者模式安装，只能上架：Edge 加载项免费，个人 Microsoft 账号就能提交；Chrome 应用商店需要
一次性 5 美元注册费，两份用的是同一个 `extension-store.zip`。

## 安全

- 服务只监听 `127.0.0.1`。`/import` 接受 `chrome-extension://`、`edge-extension://` 的 Origin，也接受没有
  Origin 的本地调用；网页里的 JS 改不了 Origin，所以无法直接调用。
- `token` 非空时改用共享密钥校验，扩展选项里要填同一个值。
- 文件只写进配置的 `project_dir`，路径检查在转换器里。`/health` 会返回工程路径，不需要凭据。

## 已知限制与排查

- 页面没有按钮：详情页要等 JSON-LD 加载完（通常 1–2 秒）；搜索页的按钮依赖卡片里的「编号」行。
  站点改版后先用扩展图标手动导入。
- 提示「本机服务要求 token」：`config.json` 的 `token` 非空，要么清空它，要么在扩展选项填一致的值。
- 连接被拒绝：服务窗口关了，或者扩展 endpoint 的端口和配置不一致。
- 端口被占用：`--setup` 换一个端口，扩展选项里的 endpoint 也要改。
- macOS 提示「无法验证开发者」：执行上面的 `xattr -dr com.apple.quarantine`。
- 首次运行没弹窗（在终端、CI 或管道里启动）：用 `--project <工程目录>` 或 `--setup`。
