# 构建与验收

## 构建 Windows x64 便携版

在 Windows x64 上安装 Python 3.12，运行：

```powershell
python tools/build_portable.py
```

构建脚本下载并校验 Python 3.12.10 官方嵌入式运行时，安装 requirements.txt 中固定版本的 Windows x64 依赖，复制代码和必要素材，然后输出 `RELEASE/Mocknido-v1.0.0-Windows-x64.zip` 及 SHA256 校验文件。首次构建需要联网，成品运行无需联网。

运行时、缓存和发布包不进入 Git。Python 与各依赖的许可证保留在便携包中。若修改发布版本，需要同步更新脚本版本、README 和 CHANGELOG。

## 检查

源码环境：

```powershell
python scripts/check_instant_dimensions.py
python scripts/check_instant_crop_ui.py
```

第二项需要 Edge 或 Chrome；可通过 `MOCKNIDO_BROWSER` 指定浏览器可执行文件。检查包括菜单状态、裁切、上传、旋转及 PNG 下载。

完整解压便携 ZIP 后，在其根目录执行：

```powershell
runtime\python.exe -X utf8 scripts/check_portable.py
```

便携检查会确认解释器路径、三类透明渲染、默认素材、本地网页资源及 PNG 导出。发布前将 ZIP 解压至另一个含中文和空格的目录再检查，并核对 SHA256。便携版已在其他电脑正常使用。
