# Spec Delta

## ADDED Requirements

### Requirement: 评测数据独立于知识内容
系统 SHALL 使知识库 bundle 仅承载源数据（raw）与业务知识（knowledge）两类知识内容，评测集与评测运行不作为知识内容存储在该库 git 仓库中，也不随知识库版本提交。

#### Scenario: bundle 不含评测数据
- **WHEN** 查看任一知识库的 git 仓库目录
- **THEN** 该仓库不存在评测集或评测运行记录

#### Scenario: 评测不产生知识提交
- **WHEN** 对某知识库运行评测任务
- **THEN** 该知识库的 git 历史不因评测而新增提交
