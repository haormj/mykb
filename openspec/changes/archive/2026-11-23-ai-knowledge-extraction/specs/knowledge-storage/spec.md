# Spec Delta

## ADDED Requirements

### Requirement: claim 级来源与提取元数据
系统 SHALL 在业务知识概念中除概念级 sources 外，记录 claim 级来源以及提取元数据（模型、提示词版本、源内容指纹、所属任务），以支持变更定位与产出来源追溯。

#### Scenario: 记录 claim 来源与提取元数据
- **WHEN** AI 产出一条业务知识
- **THEN** 概念记录每条 claim 的来源概念 id，并记录 x-extraction 元数据（模型、提示词版本、源指纹、任务）

### Requirement: 主干已审不变量
系统 SHALL 保证知识库主干中不存在未经人工评审的内容：源数据与业务知识的候选变更先存在于评审 MR 分支，只有在 MR 合并后才进入主干。

#### Scenario: 主干只含已审内容
- **WHEN** 存在尚未合并的文档级 MR
- **THEN** 该 MR 中的源数据与业务知识不出现在主干，也不进入检索索引
