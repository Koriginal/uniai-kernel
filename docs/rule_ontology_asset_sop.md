# 规则与本体资产生产线 SOP

这套能力应该单独作为平台里的一个应用来做，名字可以先叫“规则与本体资产台”。它不负责和用户聊天，也不直接执行合同审核、风控审核。它负责把业务制度、合同模板、审核手册、历史案例和数据库字段整理成可发布、可回放、可审计的结构化资产。

运行时只能使用已发布的结构化资产。原始文件、临时摘录、草稿规则和未审核本体不能直接进入业务智能体应用。

评审类应用还有一层更具体的生产线：`PolicyDocument -> PolicyArticle -> NormClause -> ReviewCheck -> ReviewPack -> ReviewRun`。合同审核、招标文件审核优先走这条线，因为它要求每个结论都能引用原文条款，且运行时必须固定规则包版本。`RuleEntry` 和 `OntologyTerm` 仍然是底层规则/本体资产，不替代评审规则包。

## 1. 目标

要解决的问题很具体：

- 业务规则不能停留在 Word、PDF、Excel、飞书文档或提示词里。
- 合同审核、风控审核这类应用，不能每次靠模型重新理解制度文件。
- 每条规则要能追到来源、版本、审核人和发布时间。
- 本体里的实体、字段、枚举、关系要有定义来源，不能只是一份手写 JSON。
- 应用运行时要记录用了哪个规则包、本体包和映射包版本。

当前系统已经有 `ontology_packages`、审批、发布、rollback、规则评估和运行时解释。缺的是前置生产线：从非结构化材料到结构化条目，再从条目编译成 package。

## 2. 产品边界

规则与本体资产台负责：

- 维护规则来源文档。
- 维护结构化规则条目。
- 维护本体术语、实体、字段、关系和枚举。
- 维护字段映射草稿。
- 发起审核、确认、退回、废弃。
- 从已批准条目编译 `schema`、`mapping`、`rule` package。
- 把 package 交给现有治理流程发布到 `staging` 或 `ga`。

不负责：

- 不负责业务应用的对话执行。
- 不负责替代 `AgentApplication`。
- 不负责让模型在运行时临时解释制度文件。
- 不负责复杂流程画布。
- 不负责绕过审批直接改线上规则。

## 3. 标准流程

### 3.1 总流程

```text
创建本体空间
-> 上传/登记来源文档
-> 解析为候选规则和候选本体
-> 业务人员校对
-> 技术人员补字段、类型、映射和执行条件
-> 提交审核
-> 审核通过
-> 编译 package
-> package 走现有治理发布
-> AgentApplication 绑定已发布版本
-> 运行时记录版本和命中结果
```

### 3.1.1 合同/招标评审流程

```text
上传合同/招标审查规则文档
-> 提取 DOCX/TXT/MD 原文
-> 切分 PolicyArticle，保留章、条、locator、quote
-> 抽取 NormClause 候选
-> 生成 ReviewCheck 候选
-> 业务人员确认 NormClause 和 ReviewCheck
-> 创建 ReviewPack
-> 发布 ReviewPack
-> AgentApplication 绑定 review_pack_id 和 review_pack_version
-> 上传或粘贴待审合同/招标文件
-> ReviewRun 输出问题清单、目标文件证据、规则原文引用和修改建议
```

约束：

- `ReviewPack` 只能包含 `approved` 的 `NormClause` 和 `ReviewCheck`。
- `ReviewRun` 只能使用 `released` 的 `ReviewPack`。
- 运行时不能临时读取草稿规则，也不能把来源文档直接当提示词塞给模型。
- 每条 finding 必须带 `policy_citations[]`，至少包含 `policy_article_id`、`locator`、`quote` 和 `norm_clause_id`。

### 3.2 状态流转

来源文档状态：

```text
uploaded -> parsed -> reviewed -> archived
uploaded -> parse_failed
```

规则条目状态：

```text
draft -> reviewing -> approved -> packaged -> released
draft -> rejected
approved -> deprecated
```

本体条目状态：

```text
draft -> reviewing -> approved -> packaged -> released
draft -> rejected
approved -> deprecated
```

package 状态继续复用现有 `VersionStage`：

```text
draft -> review -> staging -> ga -> deprecated
```

规则条目和本体条目是 authoring 层状态。`ontology_packages.stage` 是 runtime artifact 的治理状态。两者不能混用。

## 4. 数据模型

### 4.1 RuleSourceDocument

记录规则和本体定义从哪里来。

```text
id
space_id
user_id
title
source_type
file_name
content_type
content_hash
raw_text
metadata
status
created_at
updated_at
```

`source_type` v1 支持：

```text
policy_doc
contract_template
review_manual
regulation
historical_case
database_schema
api_schema
custom_note
```

约束：

- 同一个 `space_id + content_hash` 不重复入库。
- `raw_text` 可以为空，但必须有 `metadata.storage_ref` 或外部文件引用。
- 文件解析失败时保留 `parse_failed` 状态和失败原因。

### 4.2 RuleEntry

规则条目是业务规则的最小管理单元。它最终可以被编译进 `RulePackageCreate.rules[]`。

```text
id
space_id
source_document_id
rule_code
name
description
target_entity_type
conditions
severity
action
evidence_refs
test_cases
tags
status
version
created_by
reviewed_by
review_note
created_at
updated_at
```

字段说明：

- `rule_code` 是业务可读编号，例如 `CONTRACT_PAYMENT_TERM_GT_90D`。
- `conditions` 使用现有 `RuleCondition` 结构，不能写自然语言条件。
- `evidence_refs` 记录来源文件位置，例如章节、页码、段落号、表格行号。
- `test_cases` 保存正例和反例，编译前必须至少能跑一组。
- `action` 继续使用 `flag`、`block`、`recommend`。

### 4.3 OntologyTerm

本体条目是实体、字段、关系、枚举进入 schema package 前的 authoring 单元。

```text
id
space_id
source_document_id
term_code
name
kind
description
entity_type
data_type
required
enum_values
relation_target_type
relation_cardinality
aliases
evidence_refs
status
version
created_by
reviewed_by
review_note
created_at
updated_at
```

`kind` v1 支持：

```text
entity
attribute
relation
enum
taxonomy
vocabulary
```

约束：

- `kind=attribute` 时必须有 `entity_type` 和 `data_type`。
- `kind=relation` 时必须有 `entity_type`、`relation_target_type` 和 `relation_cardinality`。
- `kind=enum` 时必须有 `enum_values`。
- 同一空间内 `term_code` 唯一。

### 4.4 MappingEntry

字段映射条目负责把业务输入、表单、API、数据库字段转成本体图字段。

```text
id
space_id
source_document_id
mapping_code
source_name
source_path
target_entity_type
target_attr
required
default_value
transform
status
version
created_by
reviewed_by
created_at
updated_at
```

它最终编译进 `MappingPackageCreate.entity_mappings[]`。

## 5. 接口设计

### 5.1 来源文档

```text
POST /api/v1/ontology/asset-sources
GET  /api/v1/ontology/asset-sources/{space_id}
GET  /api/v1/ontology/asset-sources/detail/{source_id}
POST /api/v1/ontology/asset-sources/{source_id}/parse
PATCH /api/v1/ontology/asset-sources/{source_id}
```

v1 的 `parse` 可以先支持纯文本和 JSON 输入。PDF、Word、Excel 后续接文档解析器，不影响表结构。

### 5.2 规则条目

```text
POST  /api/v1/ontology/rule-entries
GET   /api/v1/ontology/rule-entries/{space_id}
GET   /api/v1/ontology/rule-entries/detail/{rule_entry_id}
PATCH /api/v1/ontology/rule-entries/{rule_entry_id}
POST  /api/v1/ontology/rule-entries/{rule_entry_id}/submit-review
POST  /api/v1/ontology/rule-entries/{rule_entry_id}/review
POST  /api/v1/ontology/rule-entries/{rule_entry_id}/deprecate
POST  /api/v1/ontology/rule-entries/test
```

`rule-entries/test` 入参应该包含 `rule_entry_id` 或临时规则定义，以及一个 `InstanceGraph`。它复用现有规则评估器，但不写入线上 decision。

### 5.3 本体条目

```text
POST  /api/v1/ontology/terms
GET   /api/v1/ontology/terms/{space_id}
GET   /api/v1/ontology/terms/detail/{term_id}
PATCH /api/v1/ontology/terms/{term_id}
POST  /api/v1/ontology/terms/{term_id}/submit-review
POST  /api/v1/ontology/terms/{term_id}/review
POST  /api/v1/ontology/terms/{term_id}/deprecate
```

### 5.4 映射条目

```text
POST  /api/v1/ontology/mapping-entries
GET   /api/v1/ontology/mapping-entries/{space_id}
PATCH /api/v1/ontology/mapping-entries/{mapping_entry_id}
POST  /api/v1/ontology/mapping-entries/{mapping_entry_id}/review
```

### 5.5 编译 package

```text
POST /api/v1/ontology/assets/compile-schema
POST /api/v1/ontology/assets/compile-mapping
POST /api/v1/ontology/assets/compile-rules
POST /api/v1/ontology/assets/compile-all
```

编译接口只读取 `approved` 条目。编译成功后生成现有 `OntologyPackageModel` 记录，初始 `stage=draft`。后续继续走：

```text
POST /api/v1/ontology/governance/approvals/submit
POST /api/v1/ontology/governance/approvals/review
POST /api/v1/ontology/governance/release
```

## 6. 编译规则

### 6.1 RuleEntry -> RulePackageCreate

输入：

```text
space_id
version
rule_entry_ids optional
include_tags optional
```

处理：

- 只读取 `status=approved` 的规则。
- 校验 `rule_code` 不重复。
- 校验 `target_entity_type` 在已批准本体实体中存在。
- 校验 `conditions[].path` 指向已批准字段。
- 校验 `severity`、`action` 在枚举范围内。
- 校验每条规则至少有一条 `evidence_refs`。
- 校验有 `test_cases` 的规则能通过测试。

输出：

```text
RulePackageCreate {
  space_id,
  version,
  description,
  rules
}
```

package `payload.metadata` 里需要保留：

```text
compiled_from_rule_entry_ids
compiled_at
compiled_by
source_document_ids
```

### 6.2 OntologyTerm -> SchemaPackageCreate

处理：

- `entity` 生成 `EntityTypeDef`。
- `attribute` 进入对应 entity 的 `attributes`。
- `relation` 进入对应 entity 的 `relations`。
- `taxonomy` 写入 `taxonomy`。
- `vocabulary` 写入 `vocabulary`。
- `enum` 如果挂在 attribute 上，写入 `enum_values`。

编译前必须校验：

- attribute 不能挂到不存在的 entity。
- relation target 不能指向不存在的 entity。
- required 字段要有明确说明。
- 同一 entity 下 attribute 名称不重复。

### 6.3 MappingEntry -> MappingPackageCreate

处理：

- 按 `target_entity_type` 聚合成 `EntityMappingRule`。
- `source_path`、`target_attr`、`required`、`default_value`、`transform` 写入 `FieldMappingRule`。
- 校验 `target_attr` 在 schema 中存在。
- 校验 transform 和目标字段类型兼容。

## 7. 控制台设计

侧边栏建议新增一级入口：

```text
规则与本体资产
```

不要把它藏在 `OntologyWorkbench` 的 JSON 编辑器里。这个应用要按业务人员和技术人员的工作流组织页面。

页面分区：

1. 来源文档
   - 上传/登记来源
   - 查看解析状态
   - 查看来源文本
   - 查看已抽取条目

2. 规则条目
   - 表格展示 `rule_code`、名称、目标实体、严重度、动作、状态、来源
   - 详情页编辑 conditions
   - 运行测试用例
   - 提交审核

3. 本体条目
   - 实体、字段、关系、枚举分组展示
   - 检查字段类型和 required
   - 查看来源证据
   - 提交审核

4. 映射条目
   - 展示来源字段到本体字段
   - 运行样例映射
   - 标记缺字段

5. 编译与发布
   - 选择条目集合
   - 生成 schema/mapping/rule package
   - 展示编译错误
   - 跳转现有治理审批和发布

6. 运行引用
   - 展示哪些 `AgentApplication` 绑定了当前空间和版本
   - 展示最近运行命中的规则
   - 展示废弃规则是否仍被应用引用

## 8. 运行时接入

`AgentApplication` 不应该只绑定 `ontology_space_id`，后续要能绑定明确版本：

```text
ontology_space_id
schema_version
mapping_version
rule_version
```

如果版本为空，才允许使用当前 GA。生产应用建议固定版本，升级时通过变更单切换。

运行时事件要写入：

```text
ontology_runtime.active_versions.schema
ontology_runtime.active_versions.mapping
ontology_runtime.active_versions.rule
ontology_runtime.decision.hits[].rule_id
ontology_runtime.decision.hits[].rule_entry_id optional
ontology_runtime.decision.hits[].evidence_refs optional
```

这样历史回放才能回答：

- 当时用了哪版规则？
- 命中的是哪条规则？
- 规则来自哪个制度文件？
- 后来规则改了，会不会影响旧结论？

## 9. 人工审核分工

建议保留三个角色，不一定第一版就做完整 RBAC，但数据流要按这个设计。

业务维护人：

- 上传来源文档。
- 修改规则名称、业务说明、严重度、动作。
- 确认来源证据。

规则工程师：

- 补 `conditions`。
- 补本体字段类型。
- 补映射路径和 transform。
- 维护测试用例。

审核人：

- 审核规则条目。
- 审核本体条目。
- 审核 package 发布。
- 不能审核自己提交的条目。

## 10. 质量门禁

规则条目进入 `approved` 前必须满足：

- 有来源文档或明确手工说明。
- 有 `rule_code`。
- 有结构化 `conditions`。
- 有 `severity` 和 `action`。
- 条件引用的实体和字段存在。
- 至少有一条证据引用。
- 高风险规则必须有测试用例。

本体条目进入 `approved` 前必须满足：

- 有唯一 `term_code`。
- 有定义说明。
- 字段类型明确。
- 关系两端实体明确。
- required 字段有业务说明。
- 枚举值完整或有维护说明。

package 发布到 `ga` 前必须满足：

- 编译无错误。
- package diff 已查看。
- staging 环境通过样例回放。
- 审批通过。
- 关键业务应用的引用影响已确认。

## 11. MVP 实施顺序

第一阶段先做规则条目生产线：

1. 新增 `RuleSourceDocumentModel`。
2. 新增 `RuleEntryModel`。
3. 新增规则条目 CRUD 和审核接口。
4. 新增 `compile-rules`，从 approved rule entries 生成现有 rule package。
5. 前端新增“规则与本体资产”入口，先做来源文档和规则条目页面。
6. 测试覆盖创建来源、创建规则、审核、编译、发布回归。

第二阶段做本体条目：

1. 新增 `OntologyTermModel`。
2. 新增本体条目 CRUD 和审核接口。
3. 新增 `compile-schema`。
4. 前端补实体、字段、关系、枚举视图。

当前代码状态：

- 第一阶段已落地来源文档、规则条目、审核和 `compile-rules`。
- 来源文档已支持 multipart 上传：`POST /api/v1/ontology/asset-sources/upload`。
- v1 存储方式是把抽取后的 `raw_text`、文件名、content type、大小、sha256 和抽取告警写入 `rule_source_documents`；原始二进制文件暂不落对象存储。
- 当前文本抽取支持 TXT、MD、JSON、CSV、TSV、DOCX；PDF 先登记文件信息并返回告警，后续接 PDF parser 或对象存储后再支持。
- 来源文档已支持 `POST /api/v1/ontology/asset-sources/{source_id}/parse`，会把 `raw_text` 按条款拆成候选规则条目。
- 自动生成的候选规则会保留 `evidence_refs.source_document_id`、`locator` 和 `quote`，审核时能回看原文依据。
- 第二阶段已落地本体条目、审核和 `compile-schema`。
- 前端“规则与本体资产”入口已接入文档上传、手工登记、原文查看、来源解析、规则条目、本体条目、规则包编译和本体包编译。

第三阶段做映射条目：

1. 新增 `MappingEntryModel`。
2. 新增映射条目 CRUD。
3. 新增 `compile-mapping`。
4. 接现有 data source discovery，把数据库/API 字段转成映射候选。

第四阶段接业务应用：

1. `AgentApplication` 增加 `schema_version`、`mapping_version`、`rule_version`。
2. Runtime contract 展示固定版本或 GA 回退。
3. 历史运行轨迹展示规则来源和版本。
4. 应用升级版本时生成变更记录。

## 12. 和现有模块的关系

现有模块继续保留：

- `backend/app/ontology/domain_models.py` 里的 package schema 仍是运行时格式。
- `backend/app/ontology/persistent_service.py` 仍负责 package 存储、审批、发布和规则评估。
- `OntologyWorkbench` 可以保留 JSON 高级编辑入口。

新增模块建议：

```text
backend/app/models/ontology_assets.py
backend/app/ontology/asset_models.py
backend/app/ontology/asset_service.py
backend/app/api/endpoints/ontology_assets.py
frontend/src/components/RuleOntologyAssetWorkbench.tsx
```

现有 `OntologyWorkbench` 是治理和调试台。新的资产台是生产入口。两者不要混成一个页面。

## 13. 一个合同审核例子

来源文档：

```text
合同审核手册 v2026.01
第 3.2 条：付款周期超过 90 天，需标记为高风险，并要求业务负责人确认。
```

本体条目：

```text
entity: Contract
attribute: payment_term_days integer required
```

规则条目：

```text
rule_code: CONTRACT_PAYMENT_TERM_GT_90D
name: 付款周期超过 90 天
target_entity_type: Contract
severity: high
action: flag
conditions:
  - path: Contract.payment_term_days
    operator: gt
    value: 90
evidence_refs:
  - source_document_id: xxx
    locator: 第 3.2 条
```

映射条目：

```text
source_path: $.contract.paymentDays
target_entity_type: Contract
target_attr: payment_term_days
transform: to_int
```

运行时命中后，历史轨迹里应该能看到：

```text
命中规则：CONTRACT_PAYMENT_TERM_GT_90D
规则版本：rules@2026.01.0
来源：合同审核手册 v2026.01 第 3.2 条
动作：flag
结论：高风险，需要业务负责人确认
```

这才是合同审核智能体稳定运行需要的基础。
