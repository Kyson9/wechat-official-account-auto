# Skill: 微信公众号自动写作与发布

版本：3.1 | 角色：`DEFAULT(main)` 编排器

---

## 一、Agent 分工

| 角色 | 职责 |
|---|---|
| `DEFAULT(main)` | 编排器，直接执行所有脚本，负责与用户澄清需求、串联状态机、控制发布边界 |
| `research_agent` | 研究、证据收集、可选切入角度分析 |
| `writer_agent` | 写作方案、初稿、精修、排版基线产出 |
| `review_agent` | 底线审校：事实、合规、严重可读性与结构问题 |
| `image_agent` | 配图与封面素材生成 |
| `data_agent` | 按需提供发布时间建议、表现预测、发布后数据回收 |
| `cron_agent` | 定时触发发布、轮询发布状态 |

**main agent 直接 exec 所有脚本，无需借道其他 agent。**

---

## 二、脚本索引

所有脚本：`echo '<JSON>' | python scripts/<name>.py`
统一返回：`{"success": true/false, "data": {...}}` 或 `{"success": false, "error": {...}}`

| 脚本 | 用途 |
|---|---|
| `setup_db.py` | 一次性初始化数据库（首次使用） |
| `task_create.py` | 创建任务，返回 task_id |
| `task_normalize.py` | 标准化任务字段，推导 task_brief |
| `task_query.py` | 查询任务完整状态 |
| `state_transition.py` | 验证并执行状态跳转 |
| `step_start.py` | 记录步骤开始，返回 step_id |
| `step_finish.py` | 记录步骤完成 |
| `content_version_create.py` | 创建内容版本，返回 content_version_id |
| `review_record_write.py` | 写入审核记录 |
| `idempotency_check.py` | 幂等键检查（草稿/发布） |
| `resume_find.py` | 找最后稳定节点，重建上下文 |
| `validate_envelope.py` | 校验 agent 输出格式 |
| `metrics_write.py` | 写入发布后指标 |
| `prepare_article_images.py` | 整理文章配图与封面输入，生成上传前素材清单 |
| `markdown_to_wechat_html.py` | 将 markdown 主链转换为微信兼容 HTML |
| `preview_fallback.py` | 预览失败时生成降级预览方案 |
| `svg_to_jpeg.py` | 将 SVG 素材转为 JPEG 以适配微信链路 |
| `wechat_token.py` | 获取/刷新 access_token |
| `wechat_upload_img.py` | 下载外链图片并上传微信，替换 HTML |
| `wechat_upload_cover.py` | 上传封面为永久素材，返回 thumb_media_id |
| `wechat_draft_add.py` | 新增微信草稿 |
| `wechat_draft_update.py` | 更新微信草稿（返工后使用） |
| `wechat_preview.py` | 触发微信预览 |
| `wechat_publish.py` | 提交发布，返回 publish_id |
| `wechat_poll.py` | 轮询发布状态 |

---

## 三、首次启动

```bash
echo '{}' | python scripts/setup_db.py
echo '{"wechat_account_id":"wxoa_main"}' | python scripts/wechat_token.py
```

两条都 `success: true` 才能继续。

---

## 四、每步标准执行模式

每一步必须按此顺序执行，不可跳过：

```
1. step_start.py                          → 获得 step_id
2. 调度 subagent 或执行脚本
3. validate_envelope.py                   → 仅 agent 输出需要；脚本调用无需校验
4. 根据结果决定：继续 / 重试 / 回退 / 人工介入
5. 必要时写入内容版本、审校记录或幂等记录
6. step_finish.py                         → 记录结果
7. state_transition.py                    → 推进状态
8. 若中断恢复，优先 task_query.py + resume_find.py
```

---

## 四点五、任务隔离与归档总则

以下归档要求为**强约束**，不可省略、不可降级为建议：

- 每篇文章必须独立归档到 `<project_root>/drafts/by-task/<task_id或稳定稿件标识>/`，不得与其他任务共用目录。
- 正式归档目录至少固定包含：`versions/`、`artifacts/markdown/`、`artifacts/html/`、`artifacts/images/`、`records/`。
- `planning`、`drafting`、`refining`、`images_generating`、`typesetting`、`draft_saved` 各阶段的关键产物，最终都必须同步或归档到上述对应目录，不得只停留在临时路径。
- 临时处理路径仅用于中间产物或脚本执行过程；进入稳定节点后，必须回填到对应任务归档目录。临时路径与正式归档路径必须明确区分。
- 新稿不得覆盖旧稿目录；返工、续写、重排版、补图必须沿用同一 `task_id` 对应的任务链目录持续沉淀。
- 若 `task_id` 已存在，则在原目录下追加新版本与新记录；不得新建并覆盖旧链路的正式归档位置。

## 五、主工作流
必须严格按照步骤进行，一个步骤不能少，也不能跳过；每一步的产物必须满足要求，才能进入下一步。每一步的输入产物必须来自前一步的输出，或来自 task_query.py + resume_find.py 的上下文重建。

### 步骤 0：任务接收

```bash
echo '{
  "topic": "...",
  "goal": "...",
  "audience": "...",
  "brand_voice": "...",
  "must_include": [],
  "must_avoid": [],
  "reference_materials": [],
  "publish_preference": {"mode": "auto_best_time", "scheduled_at": null},
  "kpi_target": {"read_target": 10000},
  "wechat_account_id": "wxoa_main"
}' | python scripts/task_create.py
→ task_id
```

---

### 步骤 1：任务标准化（received → normalized）

```bash
echo '{"task_id":"{task_id}","step_name":"normalize","input_snapshot":{"topic":"..."}}' \
  | python scripts/step_start.py
→ step_id
```

**由 `DEFAULT(main)` 直接与用户澄清 / 归纳：**

- 此步骤需要和用户Brainstorming，反复澄清需求细节，直到信息足够支撑后续研究与写作；但不要求过度细化到写作方案层面。
- 此步骤不执行 `validate_envelope.py`
- `task_brief` 采用开放式 brief，不强制 `content_type`、`intent` 等死枚举
- 至少沉淀以下字段：
  - `wechat_account`：再次向用户确认的本次投稿账号
  - `topic_understanding`：当前对主题的理解
  - `target_audience`：目标读者画像
  - `content_goal`：内容目标
  - `known_constraints`：已知限制与必须满足项
  - `current_assumptions`：当前合理假设
  - `questions_for_research`：待 research 验证的问题

可在需要时调用 `task_normalize.py` 生成归一化存档，但判断以主 agent 与用户澄清结果为准。

**成功后：**
```bash
echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"task_brief":{...}}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"normalized"}' \
  | python scripts/state_transition.py
```

若信息仍明显不足，可留在当前步骤继续澄清；不要带着关键歧义进入研究。

---

### 步骤 2：研究（normalized → research_done）

以 `research_agent` 为主，`data_agent` 按需触发，不再默认必跑。

```bash
echo '{"task_id":"{task_id}","step_name":"researching","input_snapshot":{"task_brief":{...}}}' \
  | python scripts/step_start.py
→ step_id
```

**调度 `research_agent`：**

```
task_id: {task_id}
step_name: researching
task_brief: {task_brief}
reference_materials: {原始任务中的 reference_materials}
目标阅读量：{target_read_count}

请先做充分研究，再输出 Agent Envelope JSON：
{
  "task_id": "{task_id}",
  "step_name": "researching",
  "status": "success",
  "artifacts": {
    "research_report": {
      "summary": "...",
      "freeform_findings": "自由研究报告，可分节展开",
      "optional_angles": [{"id":"...","title":"...","reason":"..."}],
      "risk_notes": []
    },
    "evidence_pack": {
      "sources": [{"source_id","type","title","url","credibility","used_for"}]
    },
    "research_self_assessment": {
      "is_sufficient_for_writing": true,
      "confidence": 0.0-1.0,
      "missing_questions": []
    }
  },
  "warnings": [],
  "errors": []
}
```

要求：
- 研究必须足够支撑写作，不做表面搜集
- `optional_angles` 数量不限，只要有价值即可
- 由 `research_agent` 自评 `is_sufficient_for_writing`
- 若研究不足，不得进入 planning

**按需调度 `data_agent`：**
- 仅当确实需要发布时间建议、表现预测或额外数据判断时才触发
- 失败允许降级，不阻断研究主线

示例 Envelope：

```
task_id: {task_id}
step_name: data_analyzing
task_brief: {task_brief}
目标阅读量：{target_read_count}

请输出 Agent Envelope JSON：
{
  "task_id": "{task_id}",
  "step_name": "data_analyzing",
  "status": "success",
  "artifacts": {
    "performance_prediction": {
      "estimated_range": [min, max],
      "confidence": 0.0-1.0,
      "drivers": ["..."]
    },
    "publish_time_suggestion": {
      "recommended_at": "ISO8601+08:00",
      "reason": "..."
    }
  },
  "warnings": [],
  "errors": []
}
```

**校验：**
```bash
echo '{"envelope":{...},"expected_task_id":"{task_id}","expected_step_name":"researching"}' \
  | python scripts/validate_envelope.py
```

如调用了 `data_agent`，再分别校验其输出。

**容错：**
- `research_agent` 失败 → 重试最多 3 次 → 仍失败则停止
- `research_agent` 返回 `is_sufficient_for_writing=false` → 留在研究阶段补充研究，不推进状态
- `data_agent` 失败 → 重试最多 3 次 → 仍失败允许降级，记录 warning

```bash
echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"research_report":{...},"evidence_pack":{...},"research_self_assessment":{...},"performance_prediction":{...},"publish_time_suggestion":{...}}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"research_done"}' \
  | python scripts/state_transition.py
```

---

### 步骤 3：写作计划（research_done → planning）

```bash
echo '{"task_id":"{task_id}","step_name":"planning","input_snapshot":{}}' \
  | python scripts/step_start.py
→ step_id
```

**调度 `writer_agent`：**

```
task_id: {task_id}
step_name: planning
task_brief: {task_brief}
research_report: {research_report}
evidence_pack: {evidence_pack}
performance_prediction: {performance_prediction}
目标阅读量：{target_read_count}

请输出 Agent Envelope JSON。
artifacts 必须形成可执行写作方案，并给出主推荐方案，至少包含：
- title_candidates: 标题候选（数量按需要）
- outline: 可执行提纲
- notes: 写作注意事项 / 证据使用说明 / 风格建议
- recommended_plan: 主推荐方案（说明为什么这样写）
- 可选包含 hook_options / cta_options，但不要求固定数量
```

**校验后，创建内容版本：**

并将 planning 关键产物归档到当前任务目录，至少包括：
- `records/`：本轮规划输入、校验结果、步骤记录
- `versions/`：规划对应的内容版本快照

```bash
echo '{"envelope":{...},"expected_task_id":"{task_id}","expected_step_name":"planning"}' \
  | python scripts/validate_envelope.py

echo '{"task_id":"{task_id}","outline_json":{...},"created_by_agent":"writer_agent"}' \
  | python scripts/content_version_create.py
→ content_version_id

echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"recommended_plan":{...},"outline":{...}}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"planning"}' \
  | python scripts/state_transition.py
```

---

### 步骤 4：初稿生成（planning → drafting）

```bash
echo '{"task_id":"{task_id}","step_name":"drafting","input_snapshot":{"content_version_id":"{cv_id}"}}' \
  | python scripts/step_start.py
→ step_id
```

**调度 `writer_agent`：**

```
task_id: {task_id}
step_name: drafting
task_brief: {task_brief}
outline: {outline}
title_candidates: {title_candidates}
evidence_pack: {evidence_pack}
brand_voice: {brand_voice}

artifacts 必须包含：
- draft_markdown: 完整正文，作为正文基线
- selected_title: 从 title_candidates 中选一个
- summary: 摘要
- char_count: 字符数（记录字段，不作为硬门槛）

初稿要求：完整、可读、主线成立、足以进入 refining；
不要求此时就接近最终公众号成稿排版。
```

初稿阶段完成后，必须把 `draft_markdown` 等关键产物归档到当前任务目录：
- `versions/`：对应内容版本
- `artifacts/markdown/`：初稿 markdown 基线
- `records/`：本轮步骤记录与校验结果

**校验：** `validate_envelope.py`

```bash
echo '{"envelope":{...},"expected_task_id":"{task_id}","expected_step_name":"drafting"}' \
  | python scripts/validate_envelope.py

echo '{"task_id":"{task_id}","title":"{selected_title}","summary":"...","markdown_body":"...","created_by_agent":"writer_agent"}' \
  | python scripts/content_version_create.py
→ 新 content_version_id

echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"selected_title":"...","char_count":1234}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"drafting"}' \
  | python scripts/state_transition.py
```

---

### 步骤 5：精修稿（drafting → draft_generated）

```bash
echo '{"task_id":"{task_id}","step_name":"refining","input_snapshot":{"content_version_id":"{cv_id}"}}' \
  | python scripts/step_start.py
→ step_id
```

**调度 `writer_agent`：**

```
task_id: {task_id}
step_name: refining
draft_markdown: {draft_markdown}
title_candidates: {title_candidates}
performance_prediction: {performance_prediction}
brand_voice: {brand_voice}

精修目标：
- 更清晰
- 更顺畅
- 更有阅读动力
- 更适合传播

artifacts 必须包含：
- draft_markdown: 精修后正文
- selected_title: 最终推荐标题
- summary: 摘要
- 可选：title_candidates、cover_plan、image_plan

不要把本阶段写成重型图片规范系统；以内容质量提升为主。
```

精修阶段完成后，必须把最新正文与相关说明归档到当前任务目录：
- `versions/`：精修后的内容版本
- `artifacts/markdown/`：精修后的 markdown 正文
- `records/`：摘要、标题决策、校验结果及返工说明

**校验：** `validate_envelope.py`

```bash
echo '{"envelope":{...},"expected_task_id":"{task_id}","expected_step_name":"refining"}' \
  | python scripts/validate_envelope.py

echo '{
  "task_id":"{task_id}",
  "title":"{selected_title}",
  "summary":"...",
  "markdown_body":"...",
  "cover_plan_json":{...},
  "evidence_pack_json":{...},
  "created_by_agent":"writer_agent"
}' | python scripts/content_version_create.py
→ 新 content_version_id

echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"selected_title":"...","summary":"..."}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"draft_generated"}' \
  | python scripts/state_transition.py
```

---

### 步骤 5.5：配图生成（draft_generated → draft_generated）

该阶段独立存在，默认走 `image_agent` 生成通道；失败可重试，也可降级为无图或仅封面方案。

```bash
echo '{"task_id":"{task_id}","step_name":"images_generating","input_snapshot":{"content_version_id":"{cv_id}"}}' \
  | python scripts/step_start.py
→ step_id
```

共享目录约定保持固定，输出需按任务与版本隔离，回填标准化路径。临时生成目录可用于中间处理，但最终图片与封面素材必须归档到当前任务目录下的 `artifacts/images/`，并在 `records/` 留下来源、版本与转换记录。

**调度 `image_agent`：**

```
task_id: {task_id}
step_name: images_generating
draft_markdown: {draft_markdown}
selected_title: {selected_title}
summary: {summary}
image_plan: {image_plan}
cover_plan: {cover_plan}
output_dir: {shared_versioned_output_dir}

要求：
- prompt 必须详细到足以让 image_agent 稳定理解任务
- prompt 组织形式可以灵活：结构化字段或高质量自然语言 brief 均可
- 输出需明确区分正文配图与封面素材
- 失败可重试；必要时允许降级
```

如生成 SVG 素材但上传链路要求 JPEG，可补充执行：

```bash
echo '{"input_path":"...svg","output_path":"...jpg"}' | python scripts/svg_to_jpeg.py
```

必要时使用：

```bash
echo '{"task_id":"{task_id}","content_version_id":"{cv_id}","image_outputs":[...]}' \
  | python scripts/prepare_article_images.py
```

本阶段可记录图片产物路径，但不引入新的状态名；完成后仍停留在当前内容阶段，供后续排版与上传使用。

```bash
echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"image_outputs":[...],"cover_asset":"..."}}' \
  | python scripts/step_finish.py
```

---

### 步骤 5.6：排版与 HTML 生成（draft_generated → draft_generated）

保留独立 typesetting 阶段，`typeset_markdown` 作为正式排版基线，`markdown_to_wechat_html.py` 为主链。

```bash
echo '{"task_id":"{task_id}","step_name":"typesetting","input_snapshot":{"content_version_id":"{cv_id}"}}' \
  | python scripts/step_start.py
→ step_id
```

可由 `writer_agent` 输出排版后的 `typeset_markdown`，也可由 main agent 基于精修稿整理后入链；若走 agent，则先校验 envelope。

建议同时让 `writer_agent` 明确排版选择，保持轻量即可：
- `typesetting_spec.mode`：`md2wechat_ai` / `browser_remote`
- `typesetting_spec.theme`：当前默认 `default`
- `typesetting_spec.code_theme`：`atom-one-dark` / `github`
- `typesetting_spec.notes`：如“手机端优先、轻高亮、少分隔线”这类目标导向说明

**结果要求：**
- `typeset_markdown`：正式排版基线
- `wechat_html`：可进入后续上传链路
- `typesetting_spec`：至少能表达本轮排版方式选择
- 适合公众号阅读
- 手机端可读
- 图文关系自然
- HTML 结构稳定，可继续执行图片替换与草稿上传

**禁止使用硬门槛：**
- 不强制标题字数
- 不强制导语字数
- 不强制段落频率或停顿点频率

**建议 checklist（结果检查项）：**
- 是否便于手机端连续阅读
- 是否能快速看懂层次
- 是否图文关系自然
- 是否不存在明显排版断裂
- 是否已检查 Markdown 原始编号/分点与转换后 HTML 渲染编号没有重复叠加（如 `2.1 1.` 这类情况），并顺手修正
- 是否 HTML 可进入微信上传链路

主链转换：

```bash
echo '{
  "task_id":"{task_id}",
  "typeset_markdown":"...",
  "conversion_mode":"md2wechat_ai",
  "typesetting_mode":"default",
  "code_theme":"github",
  "typesetting_spec":{
    "mode":"md2wechat_ai",
    "theme":"default",
    "code_theme":"github",
    "notes":"手机端优先、轻高亮、少分隔线"
  }
}' \
  | python scripts/markdown_to_wechat_html.py
→ wechat_html
```

默认建议先走 `md2wechat_ai` 本地链路；如本地链路不可用或效果不满足，再改为 `browser_remote` 走旧的网页编辑器兼容路径。

排版阶段完成后，必须将正式产物归档到当前任务目录：
- `artifacts/markdown/`：`typeset_markdown`
- `artifacts/html/`：`wechat_html`
- `records/`：`typesetting_spec`、转换方式、fallback 与异常记录

若主链失败，可执行 fallback，但目标仍是拿到可上传 HTML，而不是为了满足教条化规则。

```bash
echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"typeset_markdown":"...","wechat_html":"..."}}' \
  | python scripts/step_finish.py
```

---

### 步骤 6：自动审校（draft_generated → reviewing）

**先检查返工次数：**

```bash
echo '{"task_id":"{task_id}"}' | python scripts/task_query.py
→ rework_count
```

若 `rework_count >= 3`，跳过自动返工，直接进人工：
```bash
echo '{"task_id":"{task_id}","to_status":"human_review_pending"}' \
  | python scripts/state_transition.py
→ 跳到步骤 8
```

```bash
echo '{"task_id":"{task_id}","step_name":"reviewing","input_snapshot":{"content_version_id":"{cv_id}"}}' \
  | python scripts/step_start.py
→ step_id
```

**调度 `review_agent`：**

```
task_id: {task_id}
step_name: reviewing
task_brief: {task_brief}
draft_markdown: {draft_markdown}
typeset_markdown: {typeset_markdown}
evidence_pack: {evidence_pack}
brand_voice: {brand_voice}
rework_count: {rework_count}

review_agent 是守底线 reviewer，不是第二作者。

artifacts 必须包含：
- fact_check_report: {status(pass|fail), issues[{section,code,comment}]}
- editorial_review_report: {status(pass|revise), issues[...]}
- compliance_report: {status(pass|fail), issues[...]}
- review_decision: "approved" | "revise" | "human_escalation"
- blocking_issues: []
- non_blocking_suggestions: []

硬阻塞：
- 事实错误
- 合规风险
- 严重可读性问题
- 结构明显失效

软建议：
- 标题、节奏、表达、风格优化
- 一些小错误应该顺手修改，而不是反馈给 writer_agent 返工
不自动上升为返工。
```

**先校验：**
```bash
echo '{"envelope":{...},"expected_task_id":"{task_id}","expected_step_name":"reviewing"}' \
  | python scripts/validate_envelope.py
```

**所有审校结论必须留痕：** 任何 `approved / revise / human_escalation` 都必须调用 `review_record_write.py`。

**根据 `review_decision` 决策：**

**A. `approved`：**
```bash
echo '{"task_id":"{task_id}","content_version_id":"{cv_id}","review_type":"auto","reviewer_type":"review_agent","decision":"approved","comments":{}}' \
  | python scripts/review_record_write.py
echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"review_decision":"approved"}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"review_passed"}' \
  | python scripts/state_transition.py
→ 继续步骤 7
```

**B. `revise`：**
```bash
echo '{"task_id":"{task_id}","content_version_id":"{cv_id}","review_type":"auto","reviewer_type":"review_agent","decision":"revise","comments":{...}}' \
  | python scripts/review_record_write.py
echo '{"step_id":"{step_id}","status":"retryable_error","output_snapshot":{"review_decision":"revise","issues":[...]}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"review_failed"}' \
  | python scripts/state_transition.py
→ 执行返工路由（见第六节）
```

**C. `human_escalation`：**
```bash
echo '{"task_id":"{task_id}","content_version_id":"{cv_id}","review_type":"auto","reviewer_type":"review_agent","decision":"human_escalation","comments":{...}}' \
  | python scripts/review_record_write.py
echo '{"step_id":"{step_id}","status":"failed","output_snapshot":{"review_decision":"human_escalation"}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"human_review_pending"}' \
  | python scripts/state_transition.py
→ 步骤 8
```

---

### 步骤 7：微信素材准备 + 草稿保存（review_passed → draft_saved）

**main agent 直接执行，无需调度任何 agent。**

```bash
echo '{"task_id":"{task_id}","step_name":"assets_preparing","input_snapshot":{"content_version_id":"{cv_id}"}}' \
  | python scripts/step_start.py
→ step_id_assets
```

**7-A 整理文章素材：**

```bash
echo '{"task_id":"{task_id}","content_version_id":"{cv_id}","typeset_markdown":"...","image_outputs":[...],"cover_asset":"..."}' \
  | python scripts/prepare_article_images.py
→ prepared_assets
```

**7-B 上传正文图片（main agent exec）：**

```bash
echo '{"wechat_account_id":"{wechat_account_id}","wechat_html":"{wechat_html}"}' \
  | python scripts/wechat_upload_img.py
→ wechat_html_replaced, image_map
```

失败 → 重试最多 3 次（间隔 5 秒）→ 仍失败则停止并通知。

**7-C 上传封面素材（main agent exec）：**

```bash
echo '{"wechat_account_id":"{wechat_account_id}","cover_image_source":"{cover_plan.cover_image_source}"}' \
  | python scripts/wechat_upload_cover.py
→ thumb_media_id（为空则停止）
```

失败 → 重试最多 3 次（间隔 5 秒）。

**7-D 幂等检查（main agent exec）：**

```bash
echo '{
  "type": "draft",
  "task_id": "{task_id}",
  "content_version_id": "{cv_id}",
  "wechat_account_id": "{wechat_account_id}",
  "wechat_html_hash": "{sha256(wechat_html_replaced)}",
  "thumb_media_id": "{thumb_media_id}"
}' | python scripts/idempotency_check.py
```

- `exists: true` → 直接用 `cached_result.media_id`，跳过 7-E
- `exists: false` → 继续

**7-E 保存草稿（main agent exec）：**

```bash
echo '{"task_id":"{task_id}","step_name":"draft_saving","input_snapshot":{}}' \
  | python scripts/step_start.py
→ step_id_draft

echo '{
  "task_id":"{task_id}",
  "content_version_id":"{cv_id}",
  "wechat_account_id":"{wechat_account_id}",
  "payload_hash":"{idempotency_key}",
  "title":"{selected_title}",
  "author":"{config.author_name}",
  "digest":"{summary}",
  "content":"{wechat_html_replaced}",
  "content_source_url":"{config.content_source_url}",
  "thumb_media_id":"{thumb_media_id}"
}' | python scripts/wechat_draft_add.py
→ media_id
```

失败 → 重试最多 2 次（间隔 10 秒）→ 仍失败停止。

进入草稿保存前，`prepared_assets`、`wechat_html_replaced`、`thumb_media_id`、`media_id` 等关键产物不得只停留在运行时上下文；必须回填归档到当前任务目录，其中至少包括：
- `artifacts/images/`：最终上传所用图片、封面映射或其清单
- `artifacts/html/`：上传前后 HTML 基线与替换结果
- `records/`：幂等检查结果、草稿保存结果、media_id、上传映射

**完成：**

```bash
echo '{"step_id":"{step_id_assets}","status":"success","output_snapshot":{"prepared_assets":{...},"image_map":[...],"thumb_media_id":"..."}}' \
  | python scripts/step_finish.py
echo '{"step_id":"{step_id_draft}","status":"success","output_snapshot":{"media_id":"..."}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"draft_saved"}' \
  | python scripts/state_transition.py
```

---

### 步骤 8：人工审核（draft_saved → human_review_pending）

```bash
echo '{"task_id":"{task_id}","to_status":"human_review_pending"}' \
  | python scripts/state_transition.py

echo '{"task_id":"{task_id}"}' | python scripts/task_query.py
```

**向审核员呈现：**

```
=== 待审稿件 ===
task_id: {task_id}
主题：{topic}
版本：v{version_no}（返工次数：{rework_count}）

【标题候选】
{title_candidates 中最值得看的若干个}

当前选定：{selected_title}
摘要：{summary}

【审校结论】
事实：{fact_check_report.status} | 风格：{editorial_review_report.status} | 合规：{compliance_report.status}
硬阻塞问题：{blocking_issues}
优化建议：{non_blocking_suggestions}

【数据参考】
预期阅读：{estimated_range[0]}～{estimated_range[1]}
推荐发布：{recommended_at}（{reason}）

草稿 media_id：{media_id}（可在微信后台草稿箱预览）
```

**等待审核员操作，收到后执行：**

| 操作 | 执行 |
|---|---|
| approve | review_record_write(approved) → state_transition(human_review_approved) → 步骤 9 |
| reject | review_record_write(revise) → state_transition(human_review_rejected) → 返工路由 |
| reschedule | 更新 scheduled_publish_at → 保持 pending 重新等待 |
| cancel | state_transition(cancelled) → 结束 |

---

### 步骤 9：发布调度（human_review_approved → publishing）

```bash
echo '{"task_id":"{task_id}"}' | python scripts/task_query.py
→ publish_mode, scheduled_publish_at
```

- `manual`：state_transition(scheduled)，等人工触发 resume
- `scheduled`：state_transition(scheduled)，交由 `cron_agent` 在指定时间触发
- `auto_best_time`：只作为建议调度，不得越权自动发布；仍需人工显式确认最终发布时间

**发布前必须满足：**
- 人工已显式确认可以发布
- 未处于未知断点恢复状态
- 已完成 publish 幂等检查

**可选预览，不作为绝对阻断条件：**

```bash
echo '{"wechat_account_id":"{wechat_account_id}","media_id":"{media_id}","preview_target":"..."}' \
  | python scripts/wechat_preview.py
```

若预览失败，可降级：

```bash
echo '{"task_id":"{task_id}","media_id":"{media_id}","reason":"preview_failed"}' \
  | python scripts/preview_fallback.py
```

预览失败可降级，不必阻断整个流程，但要记录 warning。

**发布触发时（main agent exec）：**

```bash
# 幂等检查
echo '{"type":"publish","task_id":"{task_id}","content_version_id":"{cv_id}","media_id":"{media_id}","scheduled_at":"{scheduled_at}"}' \
  | python scripts/idempotency_check.py
```

- `exists: true` 且 `publish_status != failed` → 直接进轮询
- `exists: false` → 继续

```bash
echo '{"task_id":"{task_id}","step_name":"publishing","input_snapshot":{"media_id":"{media_id}"}}' \
  | python scripts/step_start.py
→ step_id

echo '{
  "task_id":"{task_id}",
  "content_version_id":"{cv_id}",
  "wechat_account_id":"{wechat_account_id}",
  "media_id":"{media_id}",
  "idempotency_key":"{idempotency_key}",
  "scheduled_at":"{scheduled_at}"
}' | python scripts/wechat_publish.py
→ publish_id
```

失败 → 重试最多 2 次（间隔 30 秒）→ 仍失败停止，**不再自动重试，等人工确认**。

```bash
echo '{"step_id":"{step_id}","status":"success","output_snapshot":{"publish_id":"..."}}' \
  | python scripts/step_finish.py
echo '{"task_id":"{task_id}","to_status":"publish_polling"}' \
  | python scripts/state_transition.py
```

---

### 步骤 10：发布轮询（publish_polling → published/publish_failed）

由 `cron_agent` 按策略间隔调度，main agent 执行：

```bash
echo '{"wechat_account_id":"{wechat_account_id}","publish_id":"{publish_id}","task_id":"{task_id}"}' \
  | python scripts/wechat_poll.py
→ publish_status: polling | published | failed
```

**轮询策略（由 cron_agent 控制间隔）：**
- 前 5 分钟：每 30 秒一次
- 5 分钟后：每 2 分钟一次
- 超过 30 分钟未终态：state_transition(publish_failed)，通知人工

| publish_status | 处理 |
|---|---|
| `polling` | 等待，按策略再次轮询 |
| `published` | state_transition(published)，通知用户发布链接 |
| `failed` | state_transition(publish_failed)，通知用户 |

---

### 步骤 11：发布后数据回收（published → archived，异步）

由 `cron_agent` 在发布后 24h / 48h / 7天触发，调度 `data_agent`：

```
task_id: {task_id}
step_name: post_publish_collection
article_id: {published_article_id}
article_link: {published_link}
wechat_account_id: {wechat_account_id}
capture_round: 1|2|3

artifacts 必须包含：
- post_publish_metrics: {view_count, share_count, favorite_count, like_count, comment_count}
- feedback_features: {content_type, title_type, publish_hour, performance_level(high|medium|low)}
```

**main agent exec（写入指标）：**

```bash
echo '{"task_id":"{task_id}","content_version_id":"{cv_id}","article_id":"...","view_count":...}' \
  | python scripts/metrics_write.py
```

第 3 次完成后：
```bash
echo '{"task_id":"{task_id}","to_status":"archived"}' \
  | python scripts/state_transition.py
```

---

## 六、返工路由

收到 `revise` 时，原则是：**问题在哪一层产生，就回到哪一层解决。**

下表为推荐映射 / 默认映射，不是僵硬唯一映射：

| reason_codes | 回退步骤 | 重新执行 |
|---|---|---|
| `fact_error` / `evidence_missing` | researching | research_agent → 步骤 3 起 |
| `angle_wrong` / `topic_mismatch` | planning | writer_agent(planning) → 步骤 4 起 |
| `title_weak` / `structure_problem` / `hook_fail` | drafting | writer_agent(drafting) → 步骤 5 起 |
| `tone_mismatch` / `style_issue` / `compliance_issue` | refining | writer_agent(refining) → 步骤 6 起 |
| `image_issue` | assets_preparing | 步骤 7-A 起 |

**执行步骤：**

1. state_transition 到 `review_failed` 或 `human_review_rejected`
2. 创建新内容版本：`content_version_create.py`（version_no 自动递增）
3. 将 `comments.items` 作为 `review_feedback` 注入下一次对应 agent 调用
4. 回退到对应步骤重新执行
5. 若已有 `media_id`，返工后草稿可用 `wechat_draft_update.py`，但**只能用于同一篇文章、同一任务链、同一草稿延续**；返工必须继续写入原 `drafts/by-task/<task_id或稳定稿件标识>/` 目录，不得新建目录覆盖旧稿：

```bash
echo '{"wechat_account_id":"{wechat_account_id}","media_id":"{media_id}","title":"...","content":"...","thumb_media_id":"..."}' \
  | python scripts/wechat_draft_update.py
```

---

## 七、断点续跑

任何中断恢复，默认先：

```bash
echo '{"task_id":"{task_id}"}' | python scripts/task_query.py
echo '{"task_id":"{task_id}"}' | python scripts/resume_find.py
→ stable_node, resume_from_step, context
```

**禁止在未知断点状态下直接重跑发布侧动作。**

| resume_from_step | 继续从哪步 |
|---|---|
| normalize | 步骤 1 |
| researching | 步骤 2 |
| planning | 步骤 3 |
| drafting | 步骤 4 |
| refining | 步骤 5 |
| reviewing | 步骤 6（先检查 rework_count） |
| assets_preparing | 步骤 7-A |
| draft_saving | 先幂等检查，有 media_id 跳过 draft_add |
| human_review_pending | 步骤 8，重新呈现审核摘要 |
| publishing | 先幂等检查，有 publish_id 直接进轮询 |
| publish_polling | 步骤 10，继续轮询 |

---

## 八、错误通知格式

```
[中断] task_id={task_id} 步骤={step_name} 错误={error_code}: {message}
稳定节点：{stable_node}
操作建议：
  查看状态  → echo '{"task_id":"{task_id}"}' | python scripts/task_query.py
  继续执行  → echo '{"task_id":"{task_id}"}' | python scripts/resume_find.py
  取消任务  → echo '{"task_id":"{task_id}","to_status":"cancelled"}' | python scripts/state_transition.py
```

---

## 九、安全约束

1. `human_review_pending` 状态下禁止直接触发发布
2. 任何微信 API 调用前必须先 `step_start.py`
3. `wechat_draft_add.py`、`wechat_draft_update.py` 延续链路判断、`wechat_publish.py` 调用前必须先做对应幂等检查
4. 微信凭证不写入任何 agent prompt 或 step 快照
5. `wechat_publish.py` 重试上限 2 次，超出等人工确认
6. `rework_count >= 3` 时禁止继续自动返工，强制进入 `human_review_pending`
7. `auto_best_time` 只能给出建议，不得代替人工发布确认
8. 未经人工显式确认，任何 publish 动作不得执行
9. 未确认断点上下文前，不得直接重跑草稿更新、发布、轮询等发布侧动作
