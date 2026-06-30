# AGENTS.md — Blank 教育学习闭环

> 本文档面向 AI 编程助手。如果你要修改本项目，请先阅读本文件。项目的主要自然语言是中文，注释、文档和错误提示均以中文为主。

---

## 项目概述

Blank 是一个教育学习闭环 MVP，核心流程为：**输入 -> 拆解 -> 学习 -> 输出（费曼）**。用户上传学习材料后，系统通过 LLM 将其拆分为带依赖关系的知识节点，随后以苏格拉底式引导进行逐节点学习，最后通过费曼验证进行多维度诊断。

项目采用前后端分离架构：
- **前端**：React 19 + TypeScript + Vite，黑白线条风格 UI，单文件巨型组件 `App.tsx`
- **后端**：Python 3.13 + FastAPI + PostgreSQL + Redis + Neo4j/GraphRAG，V2 多智能体为默认主路线

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI 0.136.3, Starlette 1.2.1, Uvicorn 0.34.0 |
| 数据校验 | Pydantic 2.10.4（所有请求/响应模型均继承 `StrictRequestModel`，`extra="forbid"`） |
| 数据库 | PostgreSQL（通过 `SessionStore` 封装） |
| 限流缓存 | Redis（默认限流后端） |
| GraphRAG | Neo4j + 向量索引（默认启用，失败回退材料片段） |
| 加密 | `cryptography`（Fernet 加密存储后台 API Key） |
| PDF 解析 | `pypdf`（限制 80 页，不支持扫描版/OCR） |
| 前端框架 | React 19, TypeScript 5.7.2, Vite 6.0.5 |
| 图标 | `lucide-react` |

---

## 目录结构

```
.
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI 路由、中间件、启动安全校验
│   │   ├── models.py        # Pydantic 模型（请求体、响应体、领域对象）
│   │   ├── services.py      # 业务逻辑：LLM 调用、知识图谱构建、聊天、费曼评分
│   │   ├── store.py         # PostgreSQL 数据访问、 schema 迁移、数据清理、研究端聚合
│   │   ├── auth.py          # 密码哈希（PBKDF2）、token 签发
│   │   ├── security.py      # 速率限制、CORS/Host 校验、SSRF 防护、请求体大小限制
│   │   ├── secrets.py       # API Key 加解密、BLANK_SECRET_KEY 管理
│   │   └── materials.py     # PDF/文本材料提取、文件名净化、二进制伪装检测
│   ├── data/                # 本地安全日志、调试日志和开发密钥（gitignore）
│   ├── test_api.py          # pytest 测试（~4000 行，覆盖端到端流程与安全场景）
│   ├── requirements.txt     # 生产依赖（全部 == 固定版本）
│   └── requirements-dev.txt # 开发依赖（含 pytest、httpx2、pip-audit）
├── pwa/
│   ├── src/
│   │   ├── main.tsx         # React 应用入口
│   │   ├── App.tsx          # 单文件主组件（~80KB，包含全部页面与逻辑）
│   │   ├── api.ts           # 前端 API 客户端（含 CSRF 双提交、流式读取）
│   │   ├── types.ts         # TypeScript 类型定义（与 backend/models.py 对应）
│   │   └── styles.css       # 自定义 CSS（非 Tailwind）
│   ├── index.html           # 开发/生产 HTML 模板（含 CSP 占位符）
│   ├── vite.config.ts       # Vite 配置：开发用 'unsafe-inline'，生产替换为严格 CSP
│   ├── tsconfig.json
│   └── package.json
├── scripts/                 # 开发、测试、部署、安全审计脚本（bash）
├── deploy/                  # 生产部署模板（systemd、nginx、fail2ban、logrotate）
├── docker/                  # 生产应用镜像定义（backend/frontend/all-in-one）与 nginx 配置
├── start.sh                 # 一键启动脚本（自动装依赖、启动前后端）
├── Dockerfile.test          # 后端测试 Docker 镜像
├── compose.yaml             # 基础设施编排（PostgreSQL + Redis + Neo4j）
├── compose.separated.yaml   # 前后端分离应用镜像 + 基础设施编排
├── compose.all-in-one.yaml  # 前后端合并应用镜像 + 基础设施编排
├── compose.test.yaml        # 一体化测试编排
├── environment.yml          # Conda 环境定义（Python 3.13 + Node 22）
├── .dockerignore            # Docker 构建上下文排除规则
└── .env.example             # 环境变量模板
```

---

## 构建与启动命令

### 一键开发启动
```bash
./start.sh
```

Windows 环境可使用同功能的 PowerShell 版本（要求 PowerShell 5.1+，推荐 7+）：
```powershell
.\start.ps1
```

- 自动检测 `blank-learning` Conda 环境或 `backend/.venv`
- 若系统缺少 Python 3.13 / Node.js 22，会自动联网下载 Miniforge 到项目目录 `.tools/miniforge3` 并创建 `blank-learning` 环境（首次约 200-400 MB）
- 自动安装缺失的 Python/npm 依赖
- 若本机未启动默认基础设施，可先运行 `./scripts/infra.sh up`，或使用 `./start.sh --with-infra` / `.\start.ps1 -WithInfra` 通过 Docker Compose 启动 PostgreSQL、Redis、Neo4j
- **Linux 下使用 `--with-infra` / `-WithInfra` 时，若未安装 Docker，会自动联网安装 Docker Engine + Compose plugin**（首次需要 root/sudo；可用 `--no-install-docker` / `-NoInstallDocker` 禁用）
- 提供 `./start.sh --check` / `.\start.ps1 -Check` 检查环境 readiness，数据库不可达不会导致失败
- 提供 `./start.sh --status` / `.\start.ps1 -Status` 检查运行状态，数据库不可达不会导致失败
- 启动后端 `http://127.0.0.1:8000`（含热重载）与前端 `http://127.0.0.1:5173`
- 若服务已在运行，直接打印访问地址
- 脚本默认拒绝监听非本机地址，除非已设置 `BLANK_ALLOWED_HOSTS` 和 `BLANK_CORS_ORIGINS`

### 手动开发启动
```bash
# 方式 A：Conda
conda env create -f environment.yml
conda activate blank-learning
cd pwa && npm install && cd ..
./scripts/dev.sh

# 方式 B：venv
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements-dev.txt
cd pwa && npm install && cd ..
./scripts/dev.sh
```

### 前端生产构建
```bash
cd pwa
npm run build
# 产物输出到 pwa/dist/
```

### Docker 镜像构建与启动

项目提供两类应用镜像：
- 前后端分离：`docker/backend.Dockerfile` 生成 `blank-learning/backend:local`，`docker/frontend.Dockerfile` 生成 `blank-learning/frontend:local`
- 前后端合并：`docker/all-in-one.Dockerfile` 生成 `blank-learning/all-in-one:local`，镜像内包含前端静态资源、FastAPI 后端和 nginx，同源代理 `/api`

构建全部应用镜像并导出到本地 `dist/docker-images/`：

```bash
./scripts/build-docker-images.sh
```

默认导出产物：
- `dist/docker-images/blank-backend-local.tar`
- `dist/docker-images/blank-frontend-local.tar`
- `dist/docker-images/blank-all-in-one-local.tar`

使用合并镜像启动完整开发环境：

```bash
# 启动合并镜像 + PostgreSQL + Redis + Neo4j
./scripts/start-in-docker.sh --all-in-one --build

# 查看应用日志
./scripts/start-in-docker.sh --all-in-one --logs

# 停止并清理所有容器与数据卷
./scripts/start-in-docker.sh --all-in-one --down
```

使用分离镜像启动完整开发环境：

```bash
# 启动前端镜像、后端镜像与基础设施
./scripts/start-in-docker.sh --separated --build

# 停止并清理所有容器与数据卷
./scripts/start-in-docker.sh --separated --down
```

启动后会暴露：
- 合并镜像应用：`http://127.0.0.1:8080`
- 分离镜像前端：`http://127.0.0.1:8080`
- 分离镜像后端 API：`http://127.0.0.1:8000`
- API 文档：合并镜像为 `http://127.0.0.1:8080/docs`，分离镜像为 `http://127.0.0.1:8000/docs`
- Neo4j Browser：`http://127.0.0.1:7474`
- PostgreSQL：`127.0.0.1:5432`
- Redis：`127.0.0.1:6379`

你也可以直接使用 `docker compose`：

```bash
# 启动合并镜像
docker compose -f compose.all-in-one.yaml up --build -d

# 启动分离镜像
docker compose -f compose.separated.yaml up --build -d

# 停止并清理数据卷
docker compose -f compose.all-in-one.yaml down -v
docker compose -f compose.separated.yaml down -v
```

**注意**：`compose.all-in-one.yaml` 与 `compose.separated.yaml` 默认使用开发友好配置。生产部署前必须在 `.env` 中设置强密码并满足生产启动硬门槛。

### 后端测试

#### 本地 venv 方式
```bash
source backend/.venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest backend/test_api.py
```

#### Docker 一体化测试（推荐用于 WSL2 / 干净环境）
项目已提供 `Dockerfile.test` + `compose.test.yaml`，在容器内启动 PostgreSQL、Redis、Neo4j 并自动运行全部后端测试：

```bash
# WSL2 Ubuntu 26.04 中，进入项目目录后执行
./scripts/test-in-docker.sh

# 强制重新构建镜像
./scripts/test-in-docker.sh --build

# 测试完成后清理容器与卷
./scripts/test-in-docker.sh --down
```

该脚本会：
1. 启动 `postgres:16-alpine`、`redis:7-alpine`、`neo4j:5.26-community` 三个容器。
2. 等待服务健康后创建 `blank_test` 测试数据库。
3. 构建/启动 `backend-test` 容器，运行 `backend/test_api.py`、`test_v2_api.py`、`test_v2_agent_graph.py`、`test_v2_feynman_agent.py`。
4. 返回 pytest 的退出码，并在 `--down` 时清理环境。

注意：测试 fixture（`isolated_store`）默认关闭 GraphRAG、使用内存限流，因此核心测试不依赖 Redis/Neo4j；但 compose 环境仍提供完整依赖，便于本地调试与后续扩展。

### 完整安全审计
```bash
./scripts/security-audit.sh
```
串行执行：后端测试、生产启动门禁、开发外网监听保护、部署模板检查、供应链检查、secret 扫描、本地/前端部署 URL 探测、前端 CSP/CSRF 静态检查、前端生产构建、`npm audit`。

---

## 代码组织与模块职责

### 后端 (`backend/app/`)

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI 实例创建、全局中间件（CORS、Host、请求体大小、Fetch Metadata）、路由定义、session/cookie 管理、依赖注入（`require_user`、`require_admin`、`require_recent_admin_reauth`） |
| `models.py` | 所有 Pydantic 模型。注意：`LearningSessionPublic.from_session()` 负责将内部模型转为对外视图，并过滤掉 `user_id`、`material_context` 及管理员专属字段 |
| `services.py` | 核心业务流程：调用 LLM 拆分知识点、苏格拉底式聊天（含流式）、费曼验证出题与评分、记忆生成。内含大量系统提示词（`SPLIT_SYSTEM_PROMPT`、`MENTOR_SYSTEM_PROMPT` 等），修改提示词时需同时检查安全规则约束 |
| `store.py` | PostgreSQL 封装。自动建表、加索引、列迁移（`_ensure_column`）、明文 API Key 自动加密（`_encrypt_plain_api_keys`），并提供教师/研究端聚合。支持用户/session/解析任务/API 配置/审计日志的增删改查及自动清理 |
| `auth.py` | PBKDF2-HMAC-SHA256 密码哈希、用户注册（首个用户可通过引导密钥成为管理员）、token 签发 |
| `security.py` | 环境变量读取、Redis 速率限制、请求体大小限制、模型 URL SSRF 防护（DNS 解析后阻断内网/保留地址）、token 格式校验、密码强度校验、安全响应头 |
| `secrets.py` | 基于 `BLANK_SECRET_KEY` 和 Fernet 的 API Key 加解密。开发环境若未配置密钥，会自动在 `backend/data/.blank_secret_key` 生成本地密钥 |
| `materials.py` | 上传材料解析：PDF 文本提取、纯文本解码（支持 UTF-8/GB18030/GBK）、二进制签名拦截、文件名净化与长度截断 |

### 前端 (`pwa/src/`)

| 文件 | 职责 |
|------|------|
| `App.tsx` | 应用状态编排，包含路由状态机（`Stage`：`canvas`/`map`/`flow`/`feynman`/`mastery`/`evidence`/`research`/`admin`）和各 stage 渲染分支 |
| `api.ts` | 所有 API 调用封装。自动携带 `credentials: "include"` 和 `X-CSRF-Token` 头。流式接口 `streamChatMessage` 使用 `response.body.getReader()` 读取 NDJSON |
| `types.ts` | TypeScript 类型，与后端 `models.py` 保持语义一致 |

---

## 关键运行时行为

### 解析任务（Parse Job）
- 材料上传后创建异步 `ParseJob`，后台线程执行 LLM 拆分
- 用户通过 `GET /api/parse-jobs/{id}` 轮询进度
- 完成后 `session_id` 指向新创建的 `LearningSession`
- 任务完成或失败后，原始材料内容会被清空（`content = ''`）以防长期留存
- 全局并发限制：`BLANK_MAX_CONCURRENT_PARSE_JOBS`（默认 2），通过 `BoundedSemaphore` 控制
- 解析完成后默认尝试写入 GraphRAG 实体、关系和向量片段；Neo4j/Embedding 失败时记录原因并回退材料片段

### 学习流（Chat）
- 默认走 V2 `POST /api/v2/chat/stream` 多智能体流式接口
- V2 返回 SSE，事件类型：`status`、`thought`、`message`、`feynman_result`、`done`、`error`
- V1 `POST /api/sessions/{id}/chat` 和 `POST .../chat/stream` 仅作为过时回退
- 自适应降维：若学习者连续卡顿，`downgraded=true`，导师自动切换为 `plain` 风格

### 费曼验证
- `POST /api/sessions/{id}/feynman/questions` 按节点出题（5 题，对应 5 个 challenge stage）
- 学习者逐题回答，系统可生成动态追问（follow-up）
- 最终提交后返回三维诊断：概念覆盖、逻辑连贯、表达负荷，以及四个维度分
- `passed` 要求四个 dimension_scores 均 ≥70

### 管理员重认证
- 后台用户权限修改、API 配置写操作要求管理员在最近 10 分钟内重新验证密码（`POST /api/auth/reauth`）
- 重认证失败会被记录到审计日志并触发速率限制

---

## 代码风格指南

- **语言**：代码注释、文档字符串、用户可见错误提示一律使用中文。
- **Python**：
  - 使用 `from __future__ import annotations`
  - 所有请求模型继承 `StrictRequestModel`（`extra="forbid"`），防止客户端传入未定义字段
  - 数据库路径、密钥等敏感配置优先从环境变量读取，其次使用安全默认值
  - 错误信息中涉及密钥、token、密码的内容必须经过 `redact_secret_text()` 脱敏后再返回或记录
  - 资源 ID 统一使用 32 位十六进制字符串（`uuid4().hex`），并通过 `resource_id_is_valid()` 校验
- **TypeScript**：
  - `tsconfig.json` 启用 `strict: true`
  - API 基础地址通过 `resolveApiBaseUrl()` 解析，禁止非本地 HTTP
  - Cookie 读取使用 `encodeURIComponent` 匹配，支持 `__Host-` 前缀的生产 Cookie 与无前缀的开发 Cookie

---

## 测试策略

- **后端**：单测集成在 `backend/test_api.py` / `backend/test_v2_api.py`，使用 `TestClient`、测试隔离数据库或显式测试替身。
  - 包含完整的学习闭环端到端测试（注册 -> 建会话 -> 聊天 -> 费曼）
  - 大量使用 `FakeModelServer`（本地 HTTP 服务器）模拟 LLM 响应，避免真实调用外部模型
  - 安全专项测试：SSRF、跨站请求阻断（Fetch Metadata）、文件上传大小/伪装检查、速率限制、生产环境启动校验
  - `isolated_store` fixture 在每个测试前替换全局 `store` 并清理速率限制状态
- **前端**：无单元测试，安全依赖静态检查（`npm run security:check`）与生产构建验证。
- **部署安全**：`scripts/security-audit.sh` 作为上线门禁，必须全部通过。

---

## 安全注意事项

### 生产环境启动硬门槛
设置 `BLANK_ENV=production` 后，启动时会强制检查：
- `BLANK_SECRET_KEY` ≥32 字符，且不是示例占位符
- `BLANK_ADMIN_BOOTSTRAP_KEY` ≥24 字符，且不是示例占位符
- `BLANK_ALLOWED_HOSTS` 已显式配置，不含通配符
- `BLANK_CORS_ORIGINS` 已显式配置为 HTTPS，不含 localhost/内网地址
- Cookie 必须启用 `Secure`，`SameSite` 不能为 `none`
- `BLANK_ALLOW_PRIVATE_MODEL_URLS` 必须为 false

### SSRF 防护
- 模型 Base URL 在保存和请求时均会校验：只允许 `http`/`https`，禁止用户名密码、查询参数、片段
- 请求连接阶段会解析主机名并阻断非全球地址（内网、本机、保留地址）
- 开发环境允许 `127.0.0.1` 回环地址，生产环境一律要求 HTTPS 且禁止私有地址

### 认证与授权
- 使用 HttpOnly Cookie + CSRF 双提交令牌。写请求（POST/PUT/PATCH/DELETE）必须同时携带合法 Origin 和 `X-CSRF-Token`
- 登录 token 使用 HMAC-SHA256 存储（密钥来自 `BLANK_SECRET_KEY` 或 `BLANK_TOKEN_HASH_KEY`）
- 速率限制：登录（IP+用户名）、注册（IP）、会话创建、聊天、费曼、管理员写操作均有独立限流

### Secret 管理
- 后台 API Key 使用 Fernet 加密存储于 PostgreSQL，密钥派生自 `BLANK_SECRET_KEY`
- 日志中自动脱敏 Bearer Token、API Key、密码等内容
- 审计日志不记录密码，登录失败不暴露账号是否存在

### 部署层要求
- 必须启用 HTTPS，使用反向代理（nginx 模板已提供）
- uvicorn 必须加 `--no-server-header`，反代需清除 `Server` / `X-Powered-By`
- 生产环境关闭 `/docs`、`/redoc`、`/openapi.json`
- PostgreSQL、Redis、Neo4j 必须作为受控服务部署，凭据通过环境变量注入

---

## 环境变量速查

| 变量 | 说明 | 开发默认值 |
|------|------|-----------|
| `BLANK_ENV` | 运行环境：`development` 或 `production` | `development` |
| `BLANK_SECRET_KEY` | API Key 加密主密钥（≥32 字符） | 自动生成本地密钥 |
| `BLANK_TOKEN_HASH_KEY` | 登录 token HMAC 专用密钥（可选） | 复用 `BLANK_SECRET_KEY` |
| `BLANK_ADMIN_BOOTSTRAP_KEY` | 首个管理员引导密钥（≥24 字符） | 示例占位符 |
| `BLANK_ALLOWED_HOSTS` | 允许的 Host 头，逗号分隔 | `localhost,127.0.0.1` |
| `BLANK_CORS_ORIGINS` | 允许的前端来源，逗号分隔 | 多个 localhost 端口 |
| `BLANK_DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://blank:blank@127.0.0.1:5432/blank` |
| `BLANK_REDIS_URL` | Redis 限流连接字符串 | `redis://127.0.0.1:6379/0` |
| `BLANK_GRAPHRAG_ENABLED` | 是否启用 GraphRAG | `true` |
| `BLANK_NEO4J_URI` | Neo4j 连接地址 | `bolt://127.0.0.1:7687` |
| `BLANK_NEO4J_USER` | Neo4j 用户名 | `neo4j` |
| `BLANK_NEO4J_PASSWORD` | Neo4j 密码 | 无默认安全值，必须配置 |
| `BLANK_SECURITY_LOG_PATH` | 安全审计日志路径 | `backend/data/security.log` |
| `BLANK_MAX_REQUEST_BYTES` | 非上传 JSON 请求体上限 | `1048576` (1MB) |
| `BLANK_ALLOW_PRIVATE_MODEL_URLS` | 是否允许模型 URL 指向私有地址 | `false` |
| `BLANK_TRUST_PROXY_HEADERS` | 是否信任 `X-Forwarded-*` | `false` |
| `BLANK_TRUSTED_PROXIES` | 可信反代 IP/CIDR 列表 | 空 |
| `BLANK_ALLOW_PUBLIC_REGISTRATION` | 是否开放公开注册 | `false`（生产默认关闭） |
| `VITE_API_BASE_URL` | 前端编译时 API 地址 | `http://localhost:8000` |

---

## 常用脚本

| 脚本 | 用途 |
|------|------|
| `./start.sh` | 一键启动前后端开发服务 |
| `./scripts/infra.sh up` | 启动本地 PostgreSQL、Redis、Neo4j 开发依赖 |
| `./scripts/dev.sh` | 仅启动开发服务（不自动装依赖） |
| `./scripts/build-docker-images.sh` | 构建 backend/frontend/all-in-one 应用镜像并导出 tar |
| `./scripts/start-in-docker.sh` | 一键 Docker 启动合并镜像或分离镜像环境 |
| `./scripts/test-in-docker.sh` | Docker 中运行后端测试 |
| `./scripts/security-audit.sh` | 完整安全审计与构建验证 |
| `./scripts/test-production-security.sh` | 生产启动配置门禁检查 |
| `./scripts/test-secret-scan.sh` | Secret 泄露扫描（含假阳性自检） |
| `./scripts/check-supply-chain.sh` | Python/npm 依赖供应链检查 |
| `./scripts/check-deploy-templates.sh` | 部署模板静态检查 |
| `./scripts/check-deployment-url.sh <url>` | 对真实部署域名做安全响应头检查 |
| `./scripts/backup-postgres.sh` | PostgreSQL 逻辑备份 |
| `./scripts/restore-postgres.sh --yes <file>` | PostgreSQL 恢复（自动先创建当前库备份） |
