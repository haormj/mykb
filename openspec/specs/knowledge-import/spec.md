# knowledge-import Specification

## Purpose

通过可扩展连接器框架（同步 + 归一化两阶段）从外部数据源摄入数据并产出 OKF 源数据概念。

## Requirements

### Requirement: 连接器两阶段接口
系统 SHALL 将每个数据源连接器定义为「同步数据」与「归一化为 markdown」两个阶段，分别负责从源拉取数据与将原始数据转为 OKF 概念。

#### Scenario: 连接器执行同步
- **WHEN** 一个连接器对数据源执行同步阶段
- **THEN** 系统从源平台拉取原始数据并完成鉴权、分页、限流与增量拉取

#### Scenario: 连接器执行归一化
- **WHEN** 一个连接器对已同步的原始数据执行归一化阶段
- **THEN** 系统产出带 type 与 frontmatter 的 OKF 源数据概念

### Requirement: 连接器注册与发现
系统 SHALL 支持注册多种数据源连接器，使平台可从语雀、Confluence、飞书、Git、数据库、代码仓等来源摄入数据。

#### Scenario: 注册新连接器
- **WHEN** 开发者实现并注册一个数据源连接器
- **THEN** 平台能够发现该连接器并对其配置的数据源执行同步与归一化

### Requirement: 源数据概念产出
系统 SHALL 使归一化阶段产出的源数据概念以 resource 字段指向外部源，并以 generated.by 标记为 process 类型连接器产出。

#### Scenario: 源数据标记来源
- **WHEN** 连接器产出一条源数据概念
- **THEN** 其 frontmatter 的 resource 字段指向外部源 URI，generated.by 记录 process 与连接器标识

### Requirement: 代码源只读引用
系统 SHALL 将代码仓库视为只读数据源，不修改代码，提取业务知识时以 resource 字段引用代码文件而非复制代码本体。

#### Scenario: 从代码提取业务知识
- **WHEN** 从代码仓库提取业务知识
- **THEN** 产出概念的 resource 字段指向代码文件位置，代码仓库内容不被修改或复制到 bundle

### Requirement: 本地上传作为导入来源
系统 SHALL 支持以用户上传的本地文件作为导入来源：Markdown 直通，Word `.docx` 经内部转换服务归一化为 markdown，图片资产随概念写入对应知识库的 raw 层级，且导入由持久化任务驱动。

#### Scenario: 上传文件归一化
- **WHEN** 本地连接器处理上传的 `.md` 或 `.markdown` 内容
- **THEN** 系统产出带 type 与 frontmatter 的 OKF 源数据概念并写入该知识库的 raw 层级

#### Scenario: 上传 docx 归一化
- **WHEN** 本地连接器处理上传的 `.docx` 内容
- **THEN** 系统先将其转换为 markdown，再产出带 type 与 frontmatter 的源数据概念，并把图片资产随概念一并写入

#### Scenario: zip 条目归一化
- **WHEN** 本地连接器处理 zip，其中包含 Markdown 或 `.docx` 条目
- **THEN** 系统按条目分别归一化，单个条目的格式或转换失败不影响其他条目

#### Scenario: 任务驱动导入
- **WHEN** 用户为知识库创建上传导入任务
- **THEN** 导入执行由该任务驱动，并把结果计数与状态写回任务记录

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
