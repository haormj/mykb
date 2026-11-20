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
系统 SHALL 支持以用户上传的本地文件作为导入来源，归一化后写入对应知识库的 raw 层级，且导入由持久化任务驱动。

#### Scenario: 上传文件归一化
- **WHEN** 本地连接器处理上传的 Markdown 或 zip 内容
- **THEN** 系统产出带 type 与 frontmatter 的 OKF 源数据概念并写入该知识库的 raw 层级

#### Scenario: 任务驱动导入
- **WHEN** 用户为知识库创建上传导入任务
- **THEN** 导入执行由该任务驱动，并把结果计数与状态写回任务记录
