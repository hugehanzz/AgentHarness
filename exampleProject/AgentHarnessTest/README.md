# AgentHarnessTest

这是一个用于 AgentHarness 开发阶段验证的轻量级、纯 Java 后端测试工作区。

它用于验证 AgentHarness 是否能够：

- 在任务指定的工作区路径中启动 Codex；
- 针对真实项目执行实现或修复工作；
- 运行 `mvn test` 等安全验证命令；
- 解析 `REVIEW.md`；
- 支持 Codex 与 ReviewerAgent 之间的反馈闭环。

根目录包含一个独立静态页面 `helloworld.html`，可直接用浏览器打开查看，不需要 Web 服务器或前端构建工具。

## 领域

示例领域是员工请假审批流程。

允许的状态流转：

```text
DRAFT -> SUBMITTED
SUBMITTED -> MANAGER_APPROVED
SUBMITTED -> REJECTED
MANAGER_APPROVED -> HR_APPROVED
MANAGER_APPROVED -> REJECTED
HR_APPROVED -> ARCHIVED
REJECTED -> ARCHIVED
```

## 验证

```bash
mvn test
```
