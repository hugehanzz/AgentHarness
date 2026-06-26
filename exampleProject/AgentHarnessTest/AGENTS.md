# AGENTS.md

## 项目

AgentHarnessTest 是一个小型、纯 Java 后端测试工作区，用于在 AgentHarness 开发阶段验证多 Agent 调度流程。

## 规则

- 不要添加前端代码。
- 除非需求明确要求，不要添加数据库、Web 服务器或 Spring 依赖。
- 保持领域模型简单，便于评审。
- 优先使用普通 Java service 类和单元测试。
- 修改代码后运行 `mvn test`。
- 不要修改 `REVIEW.md`；该文件由 ReviewerAgent 维护。
- 如果需求需要新增依赖，请先说明并等待 Human Supervisor 批准。
- 面向 Human Supervisor 的回复请使用简体中文；代码标识符、文件路径、命令和错误信息可以保持原文。

## 当前领域

当前测试领域是员工请假审批流程。
