# knowledge-storage Specification

## Purpose

以 git 仓库承载 OKF bundle 作为知识唯一事实源，管理源数据与业务知识的分层结构、血缘、版本与生命周期元数据。

## Requirements

### Requirement: 知识分层存储
系统 SHALL 以每个知识库对应一个独立 OKF bundle（位于该库自己的 git 仓库）的方式组织知识，并区分为源数据（raw）与业务知识（knowledge）两个层级，每个概念以带 YAML frontmatter 的 markdown 文件表示。

#### Scenario: 源数据落盘
- **WHEN** 数据导入流程产出源数据概念
- **THEN** 概念文件写入对应知识库 bundle 的 raw 层级目录，且 frontmatter 包含非空 type 字段

#### Scenario: 业务知识落盘
- **WHEN** 数据提取流程产出业务知识概念
- **THEN** 概念文件写入对应知识库 bundle 的 knowledge 层级目录

### Requirement: 知识库内容隔离
系统 SHALL 保证概念文件只写入所属知识库自己的 git 仓库，不同知识库之间的内容互不可见、互不影响。

#### Scenario: 写入互不串库
- **WHEN** 向某一知识库导入或提取知识
- **THEN** 概念只写入该库的 git 仓库，其他知识库的目录保持不变

#### Scenario: 查询不跨库
- **WHEN** 查询某个知识库的概念
- **THEN** 结果不包含其他知识库的内容

### Requirement: 血缘追溯
系统 SHALL 通过业务知识概念的 sources 字段记录其依赖的源数据概念，使任意业务知识可追溯至其来源。

#### Scenario: 追溯业务知识来源
- **WHEN** 用户查询某条业务知识的来源
- **THEN** 系统返回该概念 sources 字段引用的全部源数据概念

### Requirement: 知识版本化
系统 SHALL 以 git 提交作为知识的版本单位，并在 bundle 根 index.md 中声明 okf_version 与 bundle 版本。

#### Scenario: 变更形成新版本
- **WHEN** 任一概念发生变更并提交
- **THEN** 生成新的 git commit，可据此审计或回滚历史状态

### Requirement: 生命周期与信任元数据
系统 SHALL 使用 generated、verified、status、stale_after、superseded_by 字段表达知识的生产者、验证状态、生命周期与废弃关系。

#### Scenario: 知识被验证
- **WHEN** 人工审核通过某条业务知识
- **THEN** 该概念 frontmatter 记录 verified 事件，status 更新为 stable

### Requirement: OKF 合规性
系统 SHALL 保证 bundle 内所有概念文件符合 OKF 规范：每个非保留文件包含可解析的 YAML frontmatter 且含非空 type 字段，并保留未知扩展字段。

#### Scenario: 校验 bundle
- **WHEN** 对 bundle 执行合规校验
- **THEN** 缺少 type 的概念文件被报告为不合规

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
