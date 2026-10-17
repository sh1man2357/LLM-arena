# 第三方组件与授权

本项目自身源码采用 [MIT License](LICENSE)。依赖组件仍按各自许可证授权；该声明不会重新授权第三方代码。

| 组件 | 用途 | 上游与授权 |
| --- | --- | --- |
| React / React DOM、React Router | 本地前端 | [React（MIT）](https://github.com/facebook/react/blob/main/LICENSE)、[React Router（MIT）](https://github.com/remix-run/react-router/blob/main/LICENSE.md) |
| Lucide | 前端图标 | [Lucide（ISC）](https://github.com/lucide-icons/lucide/blob/main/LICENSE) |
| FastAPI、Starlette、Uvicorn、Pydantic、HTTPX 等 | 本机服务与测试 | 精确版本和安装包哈希见 `requirements-service.lock`，授权以各上游项目及安装包内 LICENSE 为准 |
| Wasmtime | WASM 执行 | [Wasmtime](https://github.com/bytecodealliance/wasmtime/blob/main/LICENSE)，Apache-2.0 WITH LLVM-exception |
| WASI SDK / LLVM / wasi-libc | C++20 编译、标准库与运行库 | [WASI SDK 33](https://github.com/WebAssembly/wasi-sdk/tree/wasi-sdk-33)，Apache、LLVM 例外、MIT 及上游列出的组件授权 |

仓库不包含 Python / npm 安装包或 SDK 二进制。安装脚本从公开来源获取锁定依赖，并核验安装包哈希。前端构建产物和本机依赖目录不提交到 Git。

公开开发包包含本项目基准 Bot 的 WASM 编译产物，因此随包保留以下上游许可文本：

- [WASI SDK 33 / LLVM 许可](licenses/WASI-SDK.txt)
- [wasi-libc 多许可说明](licenses/WASI-libc.txt)
- [wasi-libc Apache + LLVM 例外](licenses/WASI-libc-APACHE-LLVM.txt)
- [wasi-libc Apache 2.0](licenses/WASI-libc-APACHE.txt)
- [wasi-libc MIT](licenses/WASI-libc-MIT.txt)
- [musl 版权与许可](licenses/musl-COPYRIGHT.txt)

这些文本来自 SDK 33 所固定的 [wasi-libc 提交](https://github.com/WebAssembly/wasi-libc/tree/161b3195fc2558d2b1ba3eb9ffae3b2b47407623)，保留原文。其他运行库组件的来源与授权说明见其上游源码；SDK 本身不随开发包分发。
