# Spec Delta

## ADDED Requirements

### Requirement: 本地上传作为导入来源
系统 SHALL 支持以用户上传的本地文件作为导入来源，归一化后写入对应知识库的 raw 层级，且导入由持久化任务驱动。

#### Scenario: 上传文件归一化
- **WHEN** 本地连接器处理上传的 Markdown 或 zip 内容
- **THEN** 系统产出带 type 与 frontmatter 的 OKF 源数据概念并写入该知识库的 raw 层级

#### Scenario: 任务驱动导入
- **WHEN** 用户为知识库创建上传导入任务
- **THEN** 导入执行由该任务驱动，并把结果计数与状态写回任务记录
