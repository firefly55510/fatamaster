# FateMaster 模拟版（无登录/订阅）

这是一个基于 `fatemaster.ai` 功能形态制作的可运行模拟项目，覆盖了核心功能入口与调用流程，并去掉了登录验证与订阅限制。

## 已实现模块

- 八字分析命盘解析
- 每日运势
- 合婚分析
- 事业合作分析
- 婆媳关系分析
- 知己分析
- 八字关系图谱
- 梅花易数每日决策
- 六爻占卜
- 塔罗占卜
- 紫微斗数排盘
- 紫微合婚
- 黄历查询

## 技术栈

- 后端：FastAPI
- 前端：原生 HTML/CSS/JS（单页）
- 运行方式：本地服务，开放全部模块接口

## 快速启动

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# 首次可先复制 env 文件并填写 API Key
copy .env.example .env
uvicorn app:app --reload --port 8000
```

浏览器访问：`http://127.0.0.1:8000`

## 说明

- 该项目用于产品流程模拟与功能演示。
- 分析结果为算法生成的“可复现文本”，仅供参考，不构成现实决策建议。
- 按需求已移除登录、订阅、权限控制相关逻辑。
- 已支持外接大模型（OpenAI 协议兼容）。
- 核心三模块已重构为传统规则链路：八字（节气/真太阳时/四柱十神）、六爻（铜钱法/动爻/世应六亲）、紫微（安宫安星/四化）。

## 大模型配置（先 .env，后续可改系统环境变量）

- 当前读取来源：项目根目录 `.env`（通过 `python-dotenv` 自动加载）。
- 支持协议切换：OpenAI / Anthropic（兼容接口协议）。
- 关键配置项：
  - `LLM_BASE_URL`（示例：`https://coding.dashscope.aliyuncs.com/v1`）
  - `LLM_MODEL`（示例：`qwen3.5-plus`）
  - `LLM_API_KEY`（你的密钥）
- 协议切换：
  - `LLM_PROTOCOL=openai` 或 `LLM_PROTOCOL=anthropic`
  - OpenAI 协议专用：`LLM_BASE_URL_OPENAI`、`LLM_MODEL_OPENAI`、`LLM_API_KEY_OPENAI`
  - Anthropic 协议专用：`LLM_BASE_URL_ANTHROPIC`、`LLM_MODEL_ANTHROPIC`、`LLM_API_KEY_ANTHROPIC`
- 深度思考开关：
  - `LLM_DEEP_THINKING=true/false`
  - `LLM_REASONING_EFFORT=low/medium/high`
  - `LLM_THINKING_BUDGET_TOKENS`、`LLM_MAX_TOKENS`
- 当 `LLM_API_KEY` 为空时，系统自动回退到本地 AI 文案，不影响功能使用。

## 核心三模块新增字段

- 八字接口 `POST /api/bazi/analyze`：
  - `profile.timezone_offset`：时区偏移（默认 `8`）
  - `profile.longitude`：经度（默认 `120.0`）
- 六爻接口 `POST /api/liuyao/divine`：
  - 返回本卦/之卦、动爻、世应与六亲装配。
- 紫微接口 `POST /api/ziwei/chart`：
  - 返回十二宫星曜列表、四化结果与 `chart_svg` 命盘图。

## 全量典籍数据层

- 六爻典籍库：`data/classics/iching_64.json`
  - 含 64 卦完整条目（卦号、卦名、卦符）。
  - 文本结构升级为三栏：`texts.原文` / `texts.白话` / `texts.注解`，其中每卦含卦辞与爻辞。
- 紫微星曜库：`data/classics/ziwei_stars.json`
  - 含主星/辅星扩展属性（五行、亮度、吉凶、象义）。
- 引擎加载策略：启动后按需缓存加载，缺失时回退内置常量，避免服务中断。

## OpenAPI 与 Schema

- 在线文档：`http://127.0.0.1:8000/docs`
- 导出命令：

```bash
python scripts/export_openapi.py
```

- 导出文件：`openapi.schema.json`

## 覆盖率报告（pytest-cov）

- 运行命令：

```bash
pytest --cov=app --cov=engine --cov-report=term-missing --cov-report=xml --cov-report=html
```

- 终端会输出覆盖率摘要；
- HTML 报告目录：`htmlcov/index.html`；
- XML 报告文件：`coverage.xml`。

## 安全加固

- 环境变量管理：
  - `.gitignore` 已使用 `.env*` 规则屏蔽本地环境文件，并通过 `!.env.example` 保留模板。
  - `.env.example` 仅保留键名和 `<PLACEHOLDER>` 占位，不包含真实密钥。
- PDF 导出安全：
  - `MINIMAX_PDF_SKILL_DIR` 可显式指定 PDF 技能目录；未设置时回退到系统临时目录下的 `minimax-pdf`。
  - 导出流程使用独立临时工作目录和 `NamedTemporaryFile(delete=False)`，并在 `finally` 中执行清理，失败即回收临时文件。
  - 子进程异常会记录结构化错误日志并抛出 `PdfExportError`，不再吞异常。
- 调试接口限制：
  - 仅在开发环境注册 `POST /debug/pdf/export`（优先 `APP_ENV=development`，兼容 `FLASK_ENV=development`）。
  - 生产环境默认不暴露该接口。
- 统一错误响应：
  - 服务端对未处理异常返回固定 `Internal Server Error` + `trace_id`，前端不再看到 traceback、绝对路径、环境变量值。
- 预提交密钥扫描：
  - 已提供 `.pre-commit-config.yaml` 与 `.secrets.baseline`。
  - 初始化命令：

```bash
pip install pre-commit detect-secrets
pre-commit install
pre-commit run --all-files
```

- 安全扫描命令（建议在 CI 中执行）：

```bash
python -m bandit -r app.py engine.py -lll
python -m safety check -r requirements.txt
```
