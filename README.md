# Scout 项目筛选台

把早期创业项目的访谈记录，变成可复盘的两层筛选。

我在奇绩创坛 Campus Scout 期间做需求验证和项目初筛，接触了一批高校和早期创业者。那时判断靠感觉、记录散在聊天和备忘录里，事后想复盘"为什么没推荐这个团队"时，找不到当时的依据。这个工具把那套筛选方法固定下来：**每个判断都要有访谈原话做证据，系统只给建议，推不推荐由人拍板。**

## 筛选框架

| 层 | 标准 | 规则 |
|---|---|---|
| 第一层 · 硬门槛 | 场景真实性、需求与付费强度 | 任一项"不成立"直接淘汰；"待核实"要求补访谈 |
| 第二层 · 打分（1–5） | AI 必要性 35%、数据/工作流壁垒 30%、团队验证能力 35% | 加权 ≥ 3.8 **且** 每项 ≥ 3 才建议推荐 |

为什么这样设计，每一分代表什么，见 [docs/framework.md](docs/framework.md)。标准、权重、推荐线都集中在 [`scout/criteria.py`](scout/criteria.py)，改一处全局生效。

## 功能

- **项目池**：访谈记录 → 两层判断 → 系统建议 → 人工决定（推荐 / 暂缓 / 不推荐），状态自动流转
- **证据链**：每条判断都带访谈原话，没写证据的会标"缺证据"
- **AI 抽取证据**：粘贴访谈转写，模型按标准逐条给出判断和引用
  - 引用必须能在原文里**逐字找到**，找不到的直接丢弃，防止模型编造证据
  - AI 只给建议，点"采纳"才写进记录
  - 没配模型 API 时退回关键词匹配，只摘候选句，不下判断
- **复盘**：筛选漏斗 + 未通过原因分布 + 可复制的初筛清单
- **访谈模板**：由筛选标准自动生成，问题和标准一一对应
- **命令行**：批量导入导出、出复盘报告

## 快速开始

只用 Python 标准库，不需要装任何依赖（Python ≥ 3.9）。

```bash
python -m scout.server            # 打开 http://127.0.0.1:8000，首次启动自动载入示例数据
python -m scout.cli report        # 命令行看漏斗和未通过原因
python -m unittest discover -s tests -t .
```

启用 AI 抽取（任何 OpenAI 兼容接口都可以，我用的是火山方舟）：

```bash
export ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
export ARK_API_KEY=...
export SCOUT_MODEL=<模型 ID>
```

> 示例数据里的 6 个项目是虚构的，只用来演示各种筛选结果。

## 结构

```
scout/
  criteria.py   筛选标准、权重、推荐线（唯一配置来源）
  engine.py     两层判定、缺证据检查、复盘统计（纯函数）
  store.py      SQLite 存储 + 输入校验
  extract.py    访谈转写 → 证据建议（LLM + 引用校验 + 关键词兜底）
  server.py     JSON API + 静态前端
  cli.py        命令行
web/            前端（原生 JS 模块，无构建步骤）
tests/          引擎、存储、抽取、API 的测试
docs/           筛选框架说明
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/criteria` | 筛选标准 |
| GET / POST | `/api/projects` | 列表（附系统建议）/ 新建 |
| PUT / DELETE | `/api/projects/{id}` | 更新 / 删除 |
| POST | `/api/projects/{id}/extract` | 从转写抽取证据建议 |
| GET | `/api/report` | 漏斗、未通过原因、初筛清单 |
| GET / POST | `/api/export`、`/api/import` | 全量导出 / 覆盖导入 |
