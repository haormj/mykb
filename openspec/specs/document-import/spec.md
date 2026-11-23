# document-import Specification

## Purpose

让用户在知识库内上传本地文档并生成可追踪的导入任务，把文件归一化为该知识库的 raw 源数据概念。

## Requirements

### Requirement: 上传创建导入任务
系统 SHALL 允许具备导入权限的用户为指定知识库上传本地文档（Markdown、Word `.docx` 或 zip），并在数据库创建一条导入任务记录。

#### Scenario: 上传成功创建任务
- **WHEN** 有导入权限的用户上传符合类型与大小限制的文件
- **THEN** 系统创建状态为 queued 的导入任务并返回任务标识

#### Scenario: 上传 docx 创建任务
- **WHEN** 有导入权限的用户上传 `.docx` 文件
- **THEN** 系统创建一条导入任务，并在执行时对该文件进行格式转换

#### Scenario: 无权限拒绝
- **WHEN** 无导入权限的用户尝试上传
- **THEN** 系统返回禁止访问错误且不创建任务

### Requirement: 导入任务状态机
系统 SHALL 以数据库为唯一依据记录导入任务状态，取值为 queued、running、succeeded、partial、failed、cancelled，并记录计数、错误与起止时间。

#### Scenario: 全部成功
- **WHEN** 导入任务处理完所有条目且无失败
- **THEN** 任务状态置为 succeeded 并记录新增/更新/跳过数量

#### Scenario: 部分失败
- **WHEN** 导入任务完成但部分条目处理失败
- **THEN** 任务状态置为 partial 并记录失败数量与错误摘要

#### Scenario: 整体失败
- **WHEN** 导入过程发生不可恢复错误
- **THEN** 任务状态置为 failed 并记录错误信息

#### Scenario: 取消任务
- **WHEN** 有权限的用户取消排队中或运行中的任务
- **THEN** 任务状态置为 cancelled，且不再写入概念

### Requirement: 按知识库串行执行
系统 SHALL 保证同一知识库同一时刻只有一个导入任务写入工作副本，其余任务按顺序排队等待。

#### Scenario: 同库并发排队
- **WHEN** 同一知识库已有任务运行中又提交新任务
- **THEN** 新任务保持 queued 直到前一个任务结束

#### Scenario: 不同库互不阻塞
- **WHEN** 两个知识库各自提交导入任务
- **THEN** 两个任务可以互不阻塞地推进

### Requirement: 重启恢复
系统 SHALL 在服务重启后将残留的运行中任务标记为 failed，避免任务永久停留在 running。

#### Scenario: 重启后清理残留
- **WHEN** 服务启动时发现状态为 running 的任务
- **THEN** 系统将其置为 failed 并记录中断原因

### Requirement: 文档列表
系统 SHALL 提供按知识库列出已导入文档（raw 概念）的接口，并展示每条文档的来源与所属导入任务。

#### Scenario: 列出文档
- **WHEN** 有查看权限的用户请求该知识库的文档列表
- **THEN** 系统返回文档标题、来源与所属任务

#### Scenario: 不跨库返回
- **WHEN** 请求知识库 A 的文档列表
- **THEN** 结果不包含知识库 B 的文档

### Requirement: 上传临时文件清理
系统 SHALL 在导入任务进入终态后删除上传临时文件与原始文档，仅保留转换后的概念、派生资产与任务记录；原始文档不被持久化。

#### Scenario: 完成后清理
- **WHEN** 导入任务进入终态
- **THEN** 对应的上传临时文件与原始文档被删除

#### Scenario: 失败后清理
- **WHEN** 导入任务以 failed、partial 或 cancelled 进入终态
- **THEN** 上传临时文件与原始文档同样被删除

#### Scenario: 仓库不含原件
- **WHEN** 导入结束并提交 git
- **THEN** 知识库仓库中只包含转换后的概念与派生资产，不包含原始上传文档

### Requirement: 上传限制
系统 SHALL 限制上传文件类型与大小，超出限制的请求被拒绝。

#### Scenario: 不支持的类型
- **WHEN** 用户上传不在 Markdown、`.docx` 或 zip 范围内的文件
- **THEN** 系统拒绝该请求并提示允许的类型

#### Scenario: 超出大小限制
- **WHEN** 上传内容超过配置大小上限
- **THEN** 系统拒绝该请求
