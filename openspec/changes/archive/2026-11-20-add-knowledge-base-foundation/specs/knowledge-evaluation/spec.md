# Spec Delta

## ADDED Requirements

### Requirement: 评测归属知识库
系统 SHALL 将评测集与评测运行归属到具体知识库，评测只针对该库的知识版本执行。

#### Scenario: 创建评测集归属知识库
- **WHEN** 用户在知识库 A 内创建评测集
- **THEN** 系统记录该评测集归属知识库 A

#### Scenario: 评测只作用于所属知识库
- **WHEN** 在知识库 A 内运行评测
- **THEN** 系统只使用知识库 A 的知识版本执行评测并记录该版本

#### Scenario: 跨库评测集不可见
- **WHEN** 用户查看知识库 A 的评测集
- **THEN** 结果不包含知识库 B 的评测集
