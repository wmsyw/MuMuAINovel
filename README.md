# MuMuAINovel 📚✨

<div align="center">

![Version](https://img.shields.io/badge/version-1.4.6-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-green.svg)
![React](https://img.shields.io/badge/react-18.3.1-blue.svg)
![License](https://img.shields.io/badge/license-GPL%20v3-blue.svg)

**基于 AI 的智能小说创作助手**

[特性](#-特性) • [快速开始](#-快速开始) • [配置说明](#%EF%B8%8F-配置说明) • [项目结构](#-项目结构)

</div>

---

<div align="center">

## 💬 加入交流群

欢迎扫码加入 QQ 交流群，一起交流 AI 小说创作心得、反馈问题、获取最新动态！

<img src="frontend/public/qq.jpg" alt="QQ交流群二维码" width="300" />

</div>

---

<div align="center">

## 💖 支持项目

如果这个项目对你有帮助，欢迎通过以下方式支持开发：

**[☕ 请我喝杯咖啡](https://mumuverse.space:1588/)**

**[🌐 MuMuのAPI站点](https://api.mumuverse.space/register?aff=4NN8)**

> 在 MuMu の API 站点充值满 50 元及以上，也可以获得下方赞助专属权益。

### 🎁 赞助专属权益

| 权益 | 说明 |
|------|------|
| 📋 **优先需求响应** | 您的功能需求和问题反馈将获得优先处理 |
| 🚀 **Windows一键启动** | 获取免安装 EXE 程序，双击即可使用 |
| 💬 **专属技术支持** | 加入赞助者内部群，获得远程协助和配置指导 |

### ☕ 赞助 / API 站点充值档位

| 金额 | 描述 |
|------|------|
| ¥5 | 🌶️ 一包辣条 |
| ¥10 | 🍱 一顿拼好饭 |
| ¥20 | 🧋 一杯咖啡 |
| ¥50 | 🍖 一次烧烤  |
| ¥99 | 🍲 一顿海底捞 |

您的支持是我持续开发的动力！🙏

</div>

---

## ✨ 特性

- 🤖 **多 AI 模型** - 支持 OpenAI、Gemini、Claude 等主流模型
- 📝 **智能向导** - AI 自动生成大纲、角色和世界观
- 👥 **角色管理** - 人物关系、组织架构可视化管理
- 📖 **章节编辑** - 支持创建、编辑、重新生成和润色
- 🌐 **世界观设定** - 构建完整的故事背景
- 🔐 **多种登录** - LinuxDO OAuth 或本地账户登录
- 💾 **PostgreSQL** - 生产级数据库，多用户数据隔离
- 🐳 **Docker 部署** - 一键启动，开箱即用

## 📸 项目预览

<details>

<summary>多图预警</summary>

<div align="center">

### 登录界面
![登录界面](images/1.png)

![登录界面](images/1-1.png)

### 主界面
![主界面](images/2.png)

![主界面（暗色）](images/2-1.png)

### 项目管理
![项目管理](images/3.png)

![项目管理](images/3-1.png)

### 赞助我 💖
![赞助我](images/4.png)

![赞助我](images/4-1.png)

</div>

</details>

## 📋 TODO List

### ✅ 已完成功能

- [x] **灵感模式** - 创作灵感和点子生成
- [x] **自定义写作风格** - 支持自定义 AI 写作风格
- [x] **数据导入导出** - 项目数据的导入导出
- [x] **Prompt 调整界面** - 可视化编辑 Prompt 模板
- [x] **章节字数限制** - 用户可设置生成字数
- [x] **思维链与章节关系图谱** - 可视化章节逻辑关系
- [x] **根据分析一键重写** - 根据分析建议重新生成
- [x] **Linux DO 自动创建账号** - OAuth 登录自动生成账号
- [x] **职业等级体系** - 自定义职业和等级系统，支持修仙境界、魔法等级等多种体系
- [x] **角色/组织卡片导入导出** - 单独导出角色和组织卡片，支持跨项目数据共享
- [x] **伏笔管理** - 智能追踪剧情伏笔，提醒未回收线索，可视化伏笔时间线
- [x] **提示词工坊** - 社区驱动的 Prompt 模板分享平台，一键导入优质提示词
- [x] **拆书功能** - 目前呼声比较高的功能，一键拆书，给当年的ta一个圆满的结局
- [x] **正文抽取工作流** - 从正文自动提取角色、组织、职业和关系，支持候选评审、合并与回滚

### 📝 规划中功能

......

> 💡 欢迎提交 Issue 或 Pull Request！

## 💻 硬件配置要求

### 最低配置（个人使用/开发环境）

| 组件 | 要求 |
|------|------|
| **CPU** | 2 核 |
| **内存** | 2 GB RAM |
| **存储** | 10 GB 可用空间 |
| **网络** | 稳定互联网连接（用于调用 AI API） |

### 推荐配置（小型团队/生产环境）

| 组件 | 要求 |
|------|------|
| **CPU** | 4 核 |
| **内存** | 8 GB RAM |
| **存储** | 20 GB SSD |
| **网络** | 稳定互联网连接 |

### 高并发配置（80-150 用户）

| 组件 | 要求 |
|------|------|
| **CPU** | 8 核 |
| **内存** | 16 GB RAM |
| **存储** | 50 GB+ SSD |
| **网络** | 高带宽连接 |

> **📌 说明**
> - **Embedding 模型**：约 400 MB 磁盘空间，运行时加载到内存
> - **PostgreSQL**：默认配置使用 256 MB shared_buffers，1 GB effective_cache_size
> - **Docker 部署**：建议预留额外 1-2 GB 内存给容器运行时
> - 本项目主要依赖外部 AI API（OpenAI/Claude/Gemini），不需要本地 GPU

## 🚀 快速开始

### 前置要求

- Docker 和 Docker Compose
- 至少一个 AI 服务的 API Key（OpenAI/Gemini/Claude）

### Docker Compose 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/xiamuceer-j/MuMuAINovel.git
cd MuMuAINovel

# 2. 配置环境变量（必需）
cp backend/.env.example .env
# 编辑 .env 文件，填入必要配置（API Key、数据库密码等）

# 3. 确保文件准备完整
# ⚠️ 重要：确保以下文件存在
# - .env（配置文件，必需挂载到容器）
# - backend/scripts/init_postgres.sql（数据库初始化脚本）

# 4. 启动服务
docker-compose up -d

# 5. 访问应用
# 打开浏览器访问 http://localhost:8000
```

> **📌 注意事项**
>
> 1. **`.env` 文件挂载**: `docker-compose.yml` 会自动将 `.env` 挂载到容器，确保文件存在
> 2. **数据库初始化**: `init_postgres.sql` 会在首次启动时自动执行，安装必要的PostgreSQL扩展
> 3. **自行构建**: 如需从源码构建，请先下载 embedding 模型文件（[加群获取](frontend/public/qq.jpg)）

### 使用 Docker Hub 镜像（推荐新手）

```bash
# 1. 拉取最新镜像（已包含模型文件）
docker pull mumujie/mumuainovel:latest

# 2. 创建 docker-compose.yml（点击下方展开查看完整配置）
```

<details>
<summary>📄 点击展开 docker-compose.yml 完整配置</summary>

```yaml
services:
  postgres:
    image: postgres:18-alpine
    container_name: mumuainovel-postgres
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-mumuai_novel}
      POSTGRES_USER: ${POSTGRES_USER:-mumuai}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-123456}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"
      TZ: ${TZ:-Asia/Shanghai}
    volumes:
      - postgres_data:/var/lib/postgresql
      - ./backend/scripts/init_postgres.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-mumuai} -d ${POSTGRES_DB:-mumuai_novel}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - ai-story-network
    command:
      - postgres
      - -c
      - max_connections=${POSTGRES_MAX_CONNECTIONS:-200}
      - -c
      - shared_buffers=${POSTGRES_SHARED_BUFFERS:-256MB}
      - -c
      - effective_cache_size=${POSTGRES_EFFECTIVE_CACHE_SIZE:-1GB}
      - -c
      - maintenance_work_mem=${POSTGRES_MAINTENANCE_WORK_MEM:-64MB}
      - -c
      - checkpoint_completion_target=${POSTGRES_CHECKPOINT_COMPLETION_TARGET:-0.9}
      - -c
      - wal_buffers=${POSTGRES_WAL_BUFFERS:-16MB}
      - -c
      - default_statistics_target=${POSTGRES_DEFAULT_STATISTICS_TARGET:-100}
      - -c
      - random_page_cost=${POSTGRES_RANDOM_PAGE_COST:-1.1}
      - -c
      - effective_io_concurrency=${POSTGRES_EFFECTIVE_IO_CONCURRENCY:-200}
      - -c
      - work_mem=${POSTGRES_WORK_MEM:-4MB}
      - -c
      - min_wal_size=${POSTGRES_MIN_WAL_SIZE:-1GB}
      - -c
      - max_wal_size=${POSTGRES_MAX_WAL_SIZE:-4GB}

  mumuainovel:
    image: mumujie/mumuainovel:latest
    container_name: mumuainovel
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "${APP_PORT:-8000}:8000"
    volumes:
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
      - ./storage/generated_covers:/app/backend/storage/generated_covers
    environment:
      # 应用配置
      - APP_NAME=${APP_NAME:-MuMuAINovel}
      - APP_VERSION=${APP_VERSION:-1.0.0}
      - APP_HOST=${APP_HOST:-0.0.0.0}
      - APP_PORT=8000
      - DEBUG=${DEBUG:-false}
      # 数据库配置
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-mumuai}:${POSTGRES_PASSWORD:-123456}@postgres:5432/${POSTGRES_DB:-mumuai_novel}
      - DB_HOST=postgres
      - DB_PORT=5432
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-123456}
      # PostgreSQL 连接池配置
      - DATABASE_POOL_SIZE=${DATABASE_POOL_SIZE:-30}
      - DATABASE_MAX_OVERFLOW=${DATABASE_MAX_OVERFLOW:-20}
      - DATABASE_POOL_TIMEOUT=${DATABASE_POOL_TIMEOUT:-60}
      - DATABASE_POOL_RECYCLE=${DATABASE_POOL_RECYCLE:-1800}
      - DATABASE_POOL_PRE_PING=${DATABASE_POOL_PRE_PING:-True}
      - DATABASE_POOL_USE_LIFO=${DATABASE_POOL_USE_LIFO:-True}
      # 代理配置（可选）
      - HTTP_PROXY=${HTTP_PROXY:-}
      - HTTPS_PROXY=${HTTPS_PROXY:-}
      - NO_PROXY=${NO_PROXY:-localhost,127.0.0.1}
      # AI 服务配置
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.openai.com/v1}
      - GEMINI_API_KEY=${GEMINI_API_KEY:-}
      - GEMINI_BASE_URL=${GEMINI_BASE_URL:-}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-}
      - DEFAULT_AI_PROVIDER=${DEFAULT_AI_PROVIDER:-openai}
      - DEFAULT_MODEL=${DEFAULT_MODEL:-gpt-4o-mini}
      - DEFAULT_TEMPERATURE=${DEFAULT_TEMPERATURE:-0.7}
      - DEFAULT_MAX_TOKENS=${DEFAULT_MAX_TOKENS:-32000}
      # LinuxDO OAuth 配置
      - LINUXDO_CLIENT_ID=${LINUXDO_CLIENT_ID:-11111}
      - LINUXDO_CLIENT_SECRET=${LINUXDO_CLIENT_SECRET:-11111}
      - LINUXDO_REDIRECT_URI=${LINUXDO_REDIRECT_URI:-http://localhost:8000/api/auth/linuxdo/callback}
      - FRONTEND_URL=${FRONTEND_URL:-http://localhost:8000}
      # 本地账户登录配置
      - LOCAL_AUTH_ENABLED=${LOCAL_AUTH_ENABLED:-true}
      - LOCAL_AUTH_USERNAME=${LOCAL_AUTH_USERNAME:-admin}
      - LOCAL_AUTH_PASSWORD=${LOCAL_AUTH_PASSWORD:-admin123}
      - LOCAL_AUTH_DISPLAY_NAME=${LOCAL_AUTH_DISPLAY_NAME:-本地管理员}
      # 会话配置
      - SESSION_EXPIRE_MINUTES=${SESSION_EXPIRE_MINUTES:-120}
      - SESSION_REFRESH_THRESHOLD_MINUTES=${SESSION_REFRESH_THRESHOLD_MINUTES:-30}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    networks:
      - ai-story-network

volumes:
  postgres_data:
    driver: local

networks:
  ai-story-network:
    driver: bridge
```

</details>

```bash
# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f

# 5. 更新到最新版本
docker-compose pull
docker-compose up -d
```

> **💡 提示**: Docker Hub 镜像已包含所有依赖和模型文件，无需额外下载

### 本地开发 / 从源码构建

#### 前置准备

```bash
# ⚠️ 重要：如果从源码构建，需要先下载 embedding 模型文件
# 模型文件较大（约 400MB），需放置到以下目录：
# backend/embedding/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/
#
# 📥 获取方式：
# - 加入项目 QQ 群或 Linux DO 讨论区获取下载链接
# - 群号：见项目主页
# - Linux DO：https://linux.do/t/topic/1100112
```

#### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 配置 .env 文件
cp .env.example .env
# 编辑 .env 填入必要配置

# 启动 PostgreSQL（可使用 Docker）
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=mumuai_novel \
  -p 5432:5432 \
  postgres:18-alpine

# 启动后端
python -m uvicorn app.main:app --host localhost --port 8000 --reload
```

#### 前端

```bash
cd frontend
npm install
npm run dev  # 开发模式
npm run build  # 生产构建
```

## ⚙️ 配置说明

### 必需配置

创建 `.env` 文件：

```bash
# PostgreSQL 数据库（必需）
DATABASE_URL=postgresql+asyncpg://mumuai:your_password@postgres:5432/mumuai_novel
POSTGRES_PASSWORD=your_secure_password

# AI 服务
OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_AI_PROVIDER=openai
DEFAULT_MODEL=gpt-4o-mini

# 本地账户登录
LOCAL_AUTH_ENABLED=true
LOCAL_AUTH_USERNAME=admin
LOCAL_AUTH_PASSWORD=your_password
```

### 可选配置

```bash
# LinuxDO OAuth
LINUXDO_CLIENT_ID=your_client_id
LINUXDO_CLIENT_SECRET=your_client_secret
LINUXDO_REDIRECT_URI=http://localhost:8000/api/auth/callback

# PostgreSQL 连接池（高并发优化）
DATABASE_POOL_SIZE=30
DATABASE_MAX_OVERFLOW=20
```

### 中转 API 配置

支持所有 OpenAI 兼容格式的中转服务：

```bash
# New API 示例
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.new-api.com/v1

# 其他中转服务
OPENAI_BASE_URL=https://your-proxy-service.com/v1
```

## 🐳 Docker 部署详情

### 服务架构

- **postgres**: PostgreSQL 18 数据库
  - 端口: 5432
  - 数据持久化: `postgres_data` volume
  - 初始化脚本: `backend/scripts/init_postgres.sql`（自动挂载）
  - 优化配置: 支持 80-150 并发用户

- **mumuainovel**: 主应用服务
  - 端口: 8000
  - 日志目录: `./logs`
  - 配置挂载: `.env` 文件
  - 自动等待数据库就绪
  - 健康检查: 每 30 秒检测一次

### 重要文件说明

| 文件 | 说明 | 是否必需 |
|------|------|---------|
| `.env` | 环境配置（API Key、数据库密码等） | ✅ 必需 |
| `docker-compose.yml` | 服务编排配置 | ✅ 必需 |
| `backend/scripts/init_postgres.sql` | PostgreSQL 扩展安装脚本 | ✅ 自动挂载 |
| `backend/embedding/models--*/` | Embedding 模型文件 | ⚠️ 自建需要 |

> **注意**: 使用 Docker Hub 镜像时，模型文件已包含在镜像中，无需额外下载

### 常用命令

```bash
# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看资源使用
docker stats
```

### 数据持久化

- `./postgres_data` - PostgreSQL 数据库文件
- `./logs` - 应用日志文件

### 端口配置

修改 `docker-compose.yml` 中的端口映射：

```yaml
ports:
  - "8800:8000"  # 宿主机:容器
```

## 📁 项目结构

```
MuMuAINovel/
├── backend/                 # 后端服务
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── models/         # 数据模型
│   │   ├── services/       # 业务逻辑
│   │   ├── middleware/     # 中间件
│   │   ├── database.py     # 数据库连接
│   │   └── main.py         # 应用入口
│   ├── scripts/            # 工具脚本
│   └── requirements.txt    # Python 依赖
├── frontend/               # 前端应用
│   ├── src/
│   │   ├── pages/         # 页面组件
│   │   ├── components/    # 通用组件
│   │   ├── services/      # API 服务
│   │   └── store/         # 状态管理
│   └── package.json
├── docker-compose.yml      # Docker Compose 配置
├── Dockerfile             # Docker 镜像构建
└── README.md
```

## 🛠️ 技术栈

**后端**: FastAPI • PostgreSQL • SQLAlchemy • OpenAI/Claude/Gemini SDK

**前端**: React 18 • TypeScript • Ant Design • Zustand • Vite

## 📖 使用指南

1. **登录系统** - 使用本地账户或 LinuxDO 账户
2. **创建项目** - 选择"使用向导创建"
3. **AI 生成** - 输入基本信息，AI 自动生成大纲和角色
4. **编辑完善** - 管理角色关系，生成和编辑章节

### API 文档

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 🛠️ 核心工作流：正文抽取 (Extraction-First Workflow)

MuMuAINovel 采用“正文即真理”的设计理念。角色、组织、职业及其关系应当主要从正文中自动提取，而不是手动创建或由 AI 直接生成规范记录。

### 1. 自动与手动触发
- **自动触发**：在保存正文、生成章节或导入 TXT 完成后，系统会自动运行抽取任务。
- **手动触发**：用户可以在项目或章节管理界面手动触发重新抽取。

### 2. 候选评审机制
抽取结果首先进入“候选 (Candidate)”状态。用户可以在“实体评审”界面查看：
- **来源证据**：AI 提取该实体的正文片段。
- **置信度**：AI 对提取结果的确定程度。
- **操作**：接受 (Accept)、拒绝 (Reject) 或合并 (Merge) 到现有实体。

### 3. 策略网关 (Policy Gate)
默认情况下，普通用户无法直接通过 AI 生成规范的角色/组织/职业记录。
- **候选优先**：AI 生成的结果默认作为候选进入评审流。
- **高级覆盖**：管理员或开启“允许 AI 生成实体”高级设置的用户可以绕过此限制，直接创建规范记录（操作将被审计）。

### 4. 世界设定版本化
世界观生成结果不再直接覆盖当前设定，而是作为历史版本保存。用户评审并“接受”后，才会更新到当前活跃快照，并支持一键回滚。

### 5. 数据迁移与回填 (Migration & Backfill)
系统保留所有现有数据。在迁移过程中，旧有的角色、组织、职业和关系记录将通过回填服务自动标记为“已接受的规范记录”，并生成初始溯源 (Provenance) 信息，确保与新系统的兼容性。

### 6. 模型思考强度 (Provider Reasoning)
支持 OpenAI, Claude, Gemini 的思考强度配置。
- **模型限制**：思考强度受具体模型能力限制，并非所有模型都支持所有等级。
- **语义保证**：如果所选模型不支持指定的强度等级，系统将回退到该模型的默认行为，不保证强制生效。

### 7. 特性开关 (Feature Flags)
- `EXTRACTION_PIPELINE_ENABLED=True`：启用抽取管线，分析结果进入候选评审流。
- `EXTRACTION_PIPELINE_ENABLED=False`：保持兼容模式，分析结果直接修改规范数据（仅用于平滑过渡）。

### 8. 验证与开发命令

#### 后端验证
```bash
# 运行静态审计测试 (核心验证)
cd backend
python -m pytest tests/test_generation_bypass_audit.py -q

# 运行所有后端测试
cd backend
python -m pytest
```
*注意：如果本地环境缺少依赖，请使用 uv 运行：*
`uv run --python python3.11 --with pytest --with sqlalchemy --with alembic --with pydantic --with pydantic-settings --with fastapi python -m pytest tests/test_generation_bypass_audit.py -q`

#### 前端验证
```bash
# 完整构建、校验与测试链
cd frontend
npm run build && npm run lint && npm run test -- --run
```

#### 部署验证
```bash
# Docker 构建烟雾测试
docker-compose build
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

### 贡献者

感谢所有为本项目做出贡献的开发者！

<a href="https://github.com/xiamuceer-j/MuMuAINovel/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=xiamuceer-j/MuMuAINovel" />
</a>

## 📝 许可证

本项目采用 [GNU General Public License v3.0](LICENSE)

**GPL v3 意味着：**
- ✅ 可自由使用、修改和分发
- ✅ 可用于商业目的
- 📝 必须开源修改版本
- 📝 必须保留原作者版权
- 📝 衍生作品必须使用 GPL v3 协议

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - Python Web 框架
- [React](https://react.dev/) - 前端框架
- [Ant Design](https://ant.design/) - UI 组件库
- [PostgreSQL](https://www.postgresql.org/) - 数据库

## 📧 联系方式

- 提交 [Issue](https://github.com/xiamuceer-j/MuMuAINovel/issues)
- Linux DO [讨论](https://linux.do/t/topic/1106333)
- 加入QQ群 [QQ群](frontend/public/qq.jpg)
- 加入WX群 [WX群](frontend/public/WX.png)

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐️ Star！**

Made with ❤️

</div>

## Star History

<a href="https://www.star-history.com/#xiamuceer-j/MuMuAINovel&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=xiamuceer-j/MuMuAINovel&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=xiamuceer-j/MuMuAINovel&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=xiamuceer-j/MuMuAINovel&type=date&legend=top-left" />
 </picture>
</a>

## History

![Alt](https://repobeats.axiom.co/api/embed/ee7141a5f269c64759302e067abe23b46796bafe.svg "Repobeats analytics image")
