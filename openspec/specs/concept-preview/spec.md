# concept-preview Specification

## Purpose

让对知识库有查看权限的成员在平台内阅读 raw 源数据与业务知识两类概念的 markdown 正文，并能看到转换产生的派生图片资产。

## Requirements

### Requirement: 概念正文读取

系统 SHALL 允许对目标知识库具备 viewer 及以上角色的成员读取其 raw 源数据概念与业务知识概念的 markdown 正文，且只返回该知识库内的概念。

#### Scenario: 读取 raw 正文
- **WHEN** 有查看权限的成员请求某条 raw 概念的正文
- **THEN** 系统返回该概念的 markdown 正文

#### Scenario: 读取知识正文
- **WHEN** 有查看权限的成员请求某条业务知识概念的正文
- **THEN** 系统返回该业务知识概念的 markdown 正文

#### Scenario: 非成员被拒绝
- **WHEN** 非该知识库成员的已登录用户请求概念正文
- **THEN** 系统返回禁止访问错误且不返回正文

#### Scenario: 概念不存在
- **WHEN** 请求的概念标识在目标知识库中不存在
- **THEN** 系统返回未找到错误

#### Scenario: 不跨库读取
- **WHEN** 请求知识库 A 的概念正文
- **THEN** 系统不返回知识库 B 的任何内容

### Requirement: 派生资产读取

系统 SHALL 允许具备 viewer 及以上角色的成员读取某概念同名 `<concept>.assets/` 目录中的派生图片资产，并按资产类型返回对应的内容类型。

#### Scenario: 读取图片资产
- **WHEN** 有查看权限的成员请求某概念 `.assets/` 目录内存在的图片
- **THEN** 系统返回图片字节与匹配图片类型的内容类型

#### Scenario: 资产不存在
- **WHEN** 请求的资产文件或概念资产目录不存在
- **THEN** 系统返回未找到错误

### Requirement: 资产访问范围约束

系统 SHALL 将资产读取限制在目标概念自己的 `.assets/` 目录内，任何解析后越出该目录的请求 SHALL 被拒绝。

#### Scenario: 拒绝路径穿越
- **WHEN** 请求的资产路径包含 `..` 或绝对路径并试图越出概念资产目录
- **THEN** 系统拒绝该请求且不返回该目录外的文件

#### Scenario: 拒绝跨概念读取
- **WHEN** 请求使用某概念的资产路径去读取另一个概念的资产目录
- **THEN** 系统拒绝该请求

### Requirement: 概念 Markdown 渲染

系统 SHALL 在预览中以 markdown 渲染概念正文，支持标题、列表、表格、代码块与图片链接，并支持数学公式与 mermaid 图的渲染。

#### Scenario: 渲染常见结构
- **WHEN** 概念正文包含标题、列表、表格与代码块
- **THEN** 预览按 markdown 结构渲染这些内容

#### Scenario: 渲染公式与图
- **WHEN** 概念正文包含数学公式或 mermaid 代码块
- **THEN** 预览将其渲染为公式或图形

#### Scenario: 不显示 frontmatter
- **WHEN** 概念文件包含 YAML frontmatter
- **THEN** 预览只渲染正文，不把 frontmatter 当作正文内容显示

### Requirement: 图片鉴权获取

系统 SHALL 以携带用户凭据的方式获取预览中的图片，未通过鉴权的资产请求 SHALL 被拒绝。

#### Scenario: 带凭据加载图片
- **WHEN** 有查看权限的成员在预览中打开含图片的概念
- **THEN** 图片在携带其登录凭据的情况下获取并显示

#### Scenario: 无凭据拒绝
- **WHEN** 资产请求未携带有效凭据
- **THEN** 系统返回未授权错误且不返回图片

### Requirement: 渲染安全

系统 SHALL 对概念正文中的原始 HTML 与危险链接目标进行清洗，预览不得执行脚本或加载非预期外部资源。

#### Scenario: 清洗脚本
- **WHEN** 概念正文包含脚本或可执行 HTML
- **THEN** 预览不执行该脚本且剔除危险内容

#### Scenario: 拦截危险链接
- **WHEN** 概念正文包含危险协议的链接或资源地址
- **THEN** 预览拦截该目标而不加载

### Requirement: 预览入口与权限

系统 SHALL 在「文档」与「知识」页面为有查看权限的成员提供预览入口，并复用同一套 markdown 渲染能力。

#### Scenario: 文档页预览
- **WHEN** 有查看权限的成员在「文档」页选择某条 raw 文档进行预览
- **THEN** 页面展示该文档渲染后的正文

#### Scenario: 知识页预览
- **WHEN** 有查看权限的成员在「知识」页选择某条业务知识进行预览
- **THEN** 页面展示该知识渲染后的正文

#### Scenario: 无权限不可访问
- **WHEN** 非该知识库成员尝试进入预览
- **THEN** 系统不展示概念内容并给出禁止访问提示
