# 项目开发约定

- 默认直接在 `main` 分支开发。除非用户明确要求，不创建或切换到其他开发分支。
- 保留 Git 提交历史；项目初始化和整理不通过删除 `.git` 或重写历史完成。
- 仓库维护当前源码、配置、测试和操作文档。比赛数据、验收输出、日志、任务 ZIP、构建结果与缓存放在 Git 忽略目录。
- 参考赛和测试样例从当前源码生成，不依赖历史验收归档。模型任务材料维护在 `devkit/`，对外 ZIP 保持根目录执行入口。
- 清理产物使用 `tools/cleanup-test-data.ps1`，先预览目标。保留 `.venv/`、`.tools/`、`web/node_modules/` 和现有主办方数据；删除收卷、比赛或备份需要用户明确要求。
- 修改后按影响范围检查：Python 核心及服务运行 `.\.venv\Scripts\python.exe -m unittest discover -v`；文档运行 `.\.venv\Scripts\python.exe tools\check_docs.py`；前端在 `web/` 运行 `npm.cmd run build` 和 `npm.cmd run test:protocol`。浏览器测试只使用专用测试实例。
