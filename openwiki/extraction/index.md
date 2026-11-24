# 文件

- [AI 知识提取流水线](knowledge-extraction.md) - 导入的源文档如何经 LLM 提取为业务知识：harness 的结构化约束、稳定概念 id、claim 级来源与增量合并、写盘前校验，以及可替换的 LLM 客户端与离线 FakeLLM。
- [文档级评审与合并](review-workflow.md) - 每份源文档一个 change 分支构成文档级 MR、按库单飞的串行评审、审批/拒绝/退回重做、verified 与 stable 标记，以及提取项与导入任务的状态流转。
