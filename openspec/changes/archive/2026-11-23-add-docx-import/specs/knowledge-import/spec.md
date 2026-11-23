# Spec Delta

## MODIFIED Requirements

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
