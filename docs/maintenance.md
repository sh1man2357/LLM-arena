# 文档维护

根目录 README 提供简介、快速启动和主要入口。`devkit/` 维护参赛任务材料；`docs/guides/` 维护操作步骤，`docs/specs/` 定义规则与接口，`docs/architecture/` 说明模块与服务，`docs/design/` 定义界面标准。

先补充已有主题，再考虑新增文档；在[文档目录](README.md)登记入口。示例注明执行目录，文件引用使用相对 Markdown 链接。移动文件时同步修改引用它们的源码与打包工具。

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe tools\check_docs.py
```

检查覆盖当前 README、AGENTS 开发约定、文档目录和任务材料，核对本地链接和代码围栏，不依赖历史 Git 提交或验收归档。依赖版本、规则与数据格式编号用于精确复现，须与实现同步维护。
