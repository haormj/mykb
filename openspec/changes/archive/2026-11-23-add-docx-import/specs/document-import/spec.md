# Spec Delta

## MODIFIED Requirements

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
