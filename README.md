# AI Novel Studio

通用、可扩展的 AI 辅助小说创作平台。系统覆盖灵感探索、项目创建、世界设定、角色与组织、大纲、章节写作、正文实体抽取和审核。

## 功能

- **统一 AI Provider 层**：OpenAI、Gemini、Anthropic/Claude 和 OpenAI 兼容服务通过同一注册表与调用契约接入。
- **多维灵感生成**：按平台、题材、情节关键词和角色特征一次生成 3–5 个可比较方向，支持合并与故事圣经草稿。
- **可恢复项目向导**：可从灵感结果进入创建流程；表单和生成进度可恢复。
- **模板化世界设定**：内置玄幻、科幻、现代和古代模板，支持动态字段、自定义字段和旧数据迁移。
- **正文实体流水线**：章节验收后异步提取角色、组织、职业和关系；高置信同名实体自动合并，其余候选进入审核。
- **创作工作台**：角色卡、组织、职业体系、关系、时间线、大纲、章节、伏笔、写作风格、Lorebook、Data Bank 和提示词工坊。
- **统一主题与响应式布局**：浅色、深色、跟随系统三种模式；统一 `xs/sm/md/lg/xl` 断点。
- **多种认证方式**：LinuxDO OAuth、本地管理员账户和可选邮箱认证。
- **双数据库支持**：PostgreSQL 用于生产部署，SQLite 用于本地开发和测试。

## 快速开始

### Docker Compose

```bash
git clone <repository-url>
cd <repository-directory>
cp backend/.env.example .env
# 编辑 .env：至少设置 SESSION_SECRET_KEY 和一个 AI Provider

docker compose up -d
```

Docker Compose 会把应用连接到同一份 `.env` 中配置的 PostgreSQL 服务；应用默认监听 `http://localhost:8000`。

### 本地开发

后端：

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# 本地迁移明确使用 SQLite；请勿省略 DATABASE_URL。
DATABASE_URL=sqlite+aiosqlite:///./data/ai_story.db .venv/bin/alembic -c alembic-sqlite.ini upgrade head
.venv/bin/python -m uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 开发服务器会把 `/api` 请求代理到后端。生产构建写入 `backend/static/`：

```bash
cd frontend
npm run build
```

## AI Provider 配置

可在用户设置页面配置 Provider、模型、API Key 和 Base URL，也可使用环境变量提供服务端默认值：

```dotenv
DEFAULT_AI_PROVIDER=openai
DEFAULT_MODEL=gpt-4o-mini
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
```

Provider Base URL 会经过公共 HTTP(S) 地址校验，默认拒绝环回、内网和保留地址，避免 SSRF。新增 Provider 的完整步骤见 [AI Provider 开发指南](docs/AI_PROVIDER_GUIDE.md)。

## 关键环境变量

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `APP_NAME` | `AI Novel Studio` | 应用显示名称 |
| `DATABASE_URL` | 本地示例为 SQLite | 必须显式指向要使用的 PostgreSQL 或 SQLite 数据库；迁移命令与应用应使用同一 URL |
| `SESSION_SECRET_KEY` | 无 | 会话签名密钥；部署时必须使用随机长字符串 |
| `DEFAULT_AI_PROVIDER` | `openai` | 服务端默认 Provider |
| `DEFAULT_MODEL` | `gpt-4o-mini` | 服务端默认模型 |
| `EXTRACTION_PIPELINE_ENABLED` | `false` | 章节验收后启用自动正文实体抽取 |
| `ALLOW_AI_ENTITY_GENERATION` | `false` | 是否允许 AI 绕过候选审核直接生成规范实体；建议保持关闭 |
| `LOCAL_AUTH_ENABLED` | `false` | 启用本地管理员登录 |
| `LINUXDO_CLIENT_ID` | 空 | LinuxDO OAuth Client ID |
| `LINUXDO_CLIENT_SECRET` | 空 | LinuxDO OAuth Client Secret |
| `WORKSHOP_MODE` | `server` | 本地完整提示词工坊；只有显式选择 `client` 并提供 URL 才连接远程工坊 |
| `WORKSHOP_CLOUD_URL` | 空 | 远程工坊地址；默认不连接任何远程服务 |

完整变量及安全说明见 `backend/.env.example`。

## 数据库迁移

SQLite（本地开发）：

```bash
cd backend
DATABASE_URL=sqlite+aiosqlite:///./data/ai_story.db .venv/bin/alembic -c alembic-sqlite.ini upgrade head
```

PostgreSQL（连接已存在的数据库；请先替换示例连接串）：

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://novel:password@localhost:5432/novel_studio \
  .venv/bin/alembic -c alembic-postgres.ini upgrade head
```

每次运行迁移都必须显式设置目标 `DATABASE_URL`，并与应用运行时使用的 URL 保持一致；不要依赖配置中的历史回退值，以免把升级应用到错误的数据库。迁移同时维护 PostgreSQL 与 SQLite 版本；新增表或字段时必须提供可逆 `downgrade`。

## 测试与质量检查

```bash
# 后端
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app

# 前端
cd frontend
npm test -- --run
npm run build
npm run lint
npm run test:e2e
```

关键性能预算：批量生成 3 个灵感小于 30 秒，自动提取 10,000 字章节小于 15 秒，页面首次加载小于 2 秒。相关断言位于后端性能测试和 `frontend/e2e/refactor-critical.spec.ts`。

## 文档

- [架构说明](docs/ARCHITECTURE.md)
- [AI Provider 开发指南](docs/AI_PROVIDER_GUIDE.md)
- [世界设定模板开发指南](docs/WORLD_TEMPLATE_GUIDE.md)
- [用户功能指南](docs/USER_GUIDE.md)

## 项目结构

```text
backend/
  app/api/                  FastAPI 路由
  app/models/               SQLAlchemy 模型
  app/services/             AI、抽取、候选合并和领域服务
  app/services/ai_providers Provider 适配器与注册表
  alembic/postgres/         PostgreSQL 迁移
  alembic/sqlite/           SQLite 迁移
  tests/                    单元与集成测试
frontend/
  src/pages/                页面
  src/components/           复用组件
  src/theme/                主题令牌与模式
  src/styles/               公共和运行时类样式
  e2e/                      Playwright 场景
```

## License

GPL-3.0。详见 [LICENSE](LICENSE)。
