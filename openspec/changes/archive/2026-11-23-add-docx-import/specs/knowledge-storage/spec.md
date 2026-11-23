# Spec Delta

## ADDED Requirements

### Requirement: 派生资产存储

系统 SHALL 允许在知识库 bundle 的 raw 层级存放由转换产生的二进制资产（如图片），资产以与概念同名的目录组织、通过标准 Git LFS 管理并随概念一起版本化；资产不作为独立概念参与枚举与检索。

#### Scenario: 资产随概念落盘
- **WHEN** 导入产出一条包含图片的概念
- **THEN** 图片写入 raw 层与概念同名的 `.assets/` 目录，markdown 以相对路径引用这些资产

#### Scenario: 资产由 Git LFS 管理
- **WHEN** 知识库初始化或写入图片资产
- **THEN** 仓库配置图片类型的 `.gitattributes` 与本地 LFS 过滤，图片以 LFS 指针提交并随 push 传输对象

#### Scenario: 资产不参与概念枚举
- **WHEN** 系统枚举或检索概念
- **THEN** 只处理 markdown 概念，资产目录不参与枚举与检索

#### Scenario: 超出资产配额
- **WHEN** 写入资产将使知识库资产总量超过配置配额
- **THEN** 该条目失败且不写入资产，既有内容保持不变

#### Scenario: 备份恢复包含资产
- **WHEN** 备份并恢复知识库
- **THEN** 派生资产随 LFS 对象一并恢复，概念中的资产引用保持可用
