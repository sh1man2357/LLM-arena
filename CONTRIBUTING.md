# 参与开发

目前支持 Windows x64、Python 3.12、Node.js 24.19.0 和 npm 11.17.0。先阅读 [安装与启动](docs/guides/getting-started.md)和 [AGENTS.md](AGENTS.md)。

提交问题时注明游戏、版本 / Git commit、操作步骤、预期与实际结果。可附最小 Bot 源码和去除个人信息的日志；不要上传真实比赛数据、凭据或完整本机数据目录。

改动请同步维护源码、测试和操作文档，按[开发指南](docs/guides/development.md)运行对应检查。浏览器测试只使用专用数据和端口；可运行 `powershell -ExecutionPolicy Bypass -File tools\test-browser.ps1` 自动启动和关闭测试实例。

公开 CI 在 Windows 上从空环境安装锁定依赖，运行 Python、文档、协议和浏览器检查，并构建两个游戏的开发包。数据、缓存、构建结果和开发包不提交到 Git。不要通过删除 `.git` 或重写提交历史整理项目。

提交贡献即表示你有权按项目 [MIT 许可证](LICENSE)提供相关内容。第三方代码须保留其原始授权与必要说明。
