# Spec Delta

## ADDED Requirements

### Requirement: 导入产出进入待审队列
系统 SHALL 使导入产出的源数据概念不直接写入主干，而是作为候选变更进入按知识库串行的待审队列，最终随其提取结果组成文档级评审 MR，经人工合并后进入主干。

#### Scenario: 导入不直接落主干
- **WHEN** 一个导入任务完成格式转换并产出源数据概念
- **THEN** 这些源数据概念不直接提交到主干，而是进入该知识库的待审队列

#### Scenario: 导入产出随 MR 合并
- **WHEN** 某文档的文档级 MR 被人工合并
- **THEN** 该文档的源数据与提取出的业务知识一并进入主干

### Requirement: 导入任务生命周期覆盖评审
系统 SHALL 将导入任务的状态从转换延伸到评审与合并，至少覆盖 converting、queued-for-review、reviewing、merged、rejected，并保持失败与取消的既有语义。

#### Scenario: 任务进入待审
- **WHEN** 导入完成转换且等待人工评审
- **THEN** 任务状态为 queued-for-review 或 reviewing

#### Scenario: 任务合并或拒绝
- **WHEN** 该文档的 MR 被合并或被拒绝
- **THEN** 任务状态相应更新为 merged 或 rejected
