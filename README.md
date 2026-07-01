# Blank

Blank 是一个教育学习闭环 MVP，核心流程为：**输入 -> 拆解 -> 学习 -> 输出（费曼）**。用户上传学习材料后，系统通过 LLM 拆分知识节点，再以苏格拉底式引导逐节点学习，最后用费曼验证做多维诊断。

## 目录

- [功能概览](#功能概览)
- [账号与组织权限](#账号与组织权限)
- [架构状态](#架构状态)
- [快速启动](#快速启动)
- [Docker 启动](#docker-启动)
- [Docker 镜像打包](#docker-镜像打包)
- [本地开发启动](#本地开发启动)
- [测试与安全审计](#测试与安全审计)
- [主要接口](#主要接口)
- [环境变量](#环境变量)
- [安全与部署](#安全与部署)

## 功能概览

- 材料输入：上传 PDF、TXT、Markdown、CSV、JSON 和图片材料；图片可通过 Unlimited-OCR HTTP 服务提取文字，扫描版 PDF 仍会提示先 OCR。
- 解析任务：材料提交后进入持久化解析任务，刷新页面可继续查看解析进度。
- 知识拓扑：生成知识节点、复杂度、依赖关系和解锁状态。
- 苏格拉底学习：支持 Persona 调节、流式对话、困惑状态记录、自适应降维和动态多 Agent 增派。
- 思考摘要：导师消息上方显示可展开的推理要点摘要。
- 语音闭环：后台可配置 SenseVoice 兼容 ASR 与 Supertonic 兼容 TTS；费曼讲解可录音转写，导师消息和费曼题目可朗读。
- 费曼验证：提交解释后返回概念覆盖、逻辑连贯、表达负荷等诊断。
- 记忆系统：PostgreSQL 按用户持久化会话、消息与认知记录。
- 账号系统：注册、登录、HttpOnly Cookie 会话、双提交 CSRF、系统管理员/组织管理者/组织成员/个人学习者四类角色。
- 后台管理：配置 OpenAI / vLLM / Ollama / Custom 的 Base URL、API Key 和模型，创建账号并分配组织权限。
- 组织闭环：组织管理者可管理成员、查看组织研究面板、批量下发学习任务、维护组织专属知识库，并导出本组织成员的对话、费曼验证和节点轨迹用于溯源分析。
- 教师/研究端：聚合薄弱点、费曼评分分布、材料节点质量、常见误区、长期记忆类别和 token 成本指标。

## 账号与组织权限

空库第一次启动时，后端会自动创建默认系统管理员：

```text
账号：xiemonb666
密码：xiemonb666
```

默认管理员只会在用户表为空时创建，不会覆盖已有账号或重置已修改的密码。该账号首次登录后会弹出“修改账号与密码”提醒；提醒不是强制流程，点击“下次登录修改”会关闭本次弹窗，下次登录仍会提醒，直到修改密码。

角色边界：

| 角色 | 说明 |
|------|------|
| 系统管理员 `admin` | 全局后台、API/语音配置、账号创建、组织账号分配、全局研究面板 |
| 组织管理者 `org_manager` | 本组织成员、任务、知识库、组织研究统计和成员详细学习报告 |
| 组织成员 `org_member` | 自己的学习会话、本组织任务、组织知识库增强检索 |
| 个人学习者 `learner` | 原有个人学习闭环，不加入组织 |

注册页支持选择三种公开注册身份：组织管理者、组织成员、个人学习者。组织管理者注册时填写组织名称并自动创建组织 ID；组织成员填写组织 ID 后直接加入组织；个人学习者维持原有逻辑。生产环境仍受 `BLANK_ALLOW_PUBLIC_REGISTRATION` 控制，关闭公开注册时应由系统管理员在后台创建或分配账号。

组织管理者进入“组织”入口后，可在四个标签页完成日常管理：

- 成员：查看每个成员的材料数、掌握节点、平均费曼得分和详细能力维度。
- 任务：向全部组织成员或指定成员批量下发学习任务，成员启动后生成独立学习会话。
- 知识库：上传组织内部资料，聊天检索会追加同组织知识库内容；删除时同步清理组织知识库记录和 SAG 索引。
- 组织研究：查看本组织范围内的研究指标、费曼分布、材料质量和成员明细。
- 导出溯源：下载本组织成员的会话、对话消息、费曼问题/答案/追问/评分、节点状态和节点画像 JSON。

## 架构状态

- 前端：React 19 + TypeScript + Vite，黑白线条风 UI。
- 后端：Python 3.13 + FastAPI + PostgreSQL/SAG + Redis + 可选 Neo4j/GraphRAG。
- V2 主路线：前端默认使用 `/api/v2/chat/stream` 多智能体流式对话。
- V1 回退：旧 `/api/sessions/{id}/chat` 单链路导师仍保留用于故障回退。
- 多 Agent：固定角色为 Router、RAG、Socrates、Feynman、Critic、Graph；Router 会按消息复杂度和学习状态动态增派 Planner、Analyst、Coach、Memory。
- RAG：默认 `BLANK_RAG_BACKEND=sag`，使用 PostgreSQL 保存语义分段、实体、事件和多级召回结果；`legacy_neo4j` 可切回旧 Neo4j GraphRAG。
- 主存储：PostgreSQL 是默认主存储和 SAG 数据底座，Redis 是默认限流后端，Neo4j 仅在旧 GraphRAG 模式下使用。
- 语音服务：ASR/TTS 支持后台数据库配置，未配置时回退 `BLANK_ASR_*` / `BLANK_TTS_*` 环境变量。

## 快速启动

推荐先用 Docker 启动完整环境。Docker 会同时启动应用、PostgreSQL、Redis 和 Neo4j。

Linux / macOS / WSL：

```bash
# 自动检测镜像：已有则跳过构建，缺失则构建
./scripts/start-in-docker.sh --all-in-one
```

Windows PowerShell：

```powershell
# 首次启动或依赖变更后
docker compose -f compose.all-in-one.yaml up --build -d

# 已有镜像时只启动
docker compose -f compose.all-in-one.yaml up -d --no-build
```

访问：

```text
应用入口：http://127.0.0.1:8080
API 文档：http://127.0.0.1:8080/docs
Neo4j Web：http://127.0.0.1:7474
```

默认管理员登录信息见 [账号与组织权限](#账号与组织权限)。首次登录后建议立即在弹窗中修改账号或密码。

停止并清理数据卷：

```bash
./scripts/start-in-docker.sh --all-in-one --down
```

```powershell
docker compose -f compose.all-in-one.yaml down -v
```

Linux / macOS / WSL 启动脚本会默认处理 `5432`、`6379`、`7474`、`7687`、`8000`、`8080` 端口冲突。Windows 直接使用 `docker compose` 或脚本加 `--no-kill` 时，需要先手动停止占用这些端口的程序，或修改 compose 中的端口映射。

## Docker 启动

项目提供两种应用镜像形态。

前置条件：

- Linux / WSL：已安装 Docker Engine 和 Docker Compose plugin。
- Windows：已安装 Docker Desktop，并使用 Linux containers 模式。

Linux / macOS / WSL 的 `scripts/start-in-docker.sh` 会自动检测应用镜像：镜像存在时跳过构建，镜像缺失时自动构建。启动前脚本还会检测 Blank 所需端口，优先停止占用端口的 Docker 容器；如果端口仍被宿主机进程占用，会关闭该进程以保证 Blank 优先启动。需要保留占用端口的程序时，可加 `--no-kill`。

| 模式 | 应用镜像 | 适用场景 |
|------|----------|----------|
| 前后端合并 | `blank-learning/all-in-one:local` | 本地演示、单入口部署、同源访问 `/api` |
| 前后端分离 | `blank-learning/backend:local` + `blank-learning/frontend:local` | 前端和后端独立部署、后端 API 单独暴露 |

两种 compose 都会同时编排 PostgreSQL(pgvector 镜像)、Redis 和 Neo4j。这里的“合并镜像”指前端和后端合并为一个应用镜像，数据库和中间件仍作为基础设施容器运行。默认 RAG 后端为 PostgreSQL/SAG；Neo4j 保留给 `BLANK_RAG_BACKEND=legacy_neo4j`。

### 合并模式

Linux / macOS / WSL：

```bash
# 自动检测镜像：已有则跳过构建，缺失则构建
./scripts/start-in-docker.sh --all-in-one

# 只启动已有镜像，不构建；镜像缺失会失败
./scripts/start-in-docker.sh --all-in-one --no-build

# 强制重新构建并启动
./scripts/start-in-docker.sh --all-in-one --build

# 启动但不自动关闭端口冲突程序
./scripts/start-in-docker.sh --all-in-one --no-kill

# 查看日志
./scripts/start-in-docker.sh --all-in-one --logs

# 停止并清理容器与数据卷
./scripts/start-in-docker.sh --all-in-one --down
```

Windows PowerShell：

```powershell
# 只启动已有镜像，不构建
docker compose -f compose.all-in-one.yaml up -d --no-build

# 重新构建并启动
docker compose -f compose.all-in-one.yaml up --build -d

# 查看日志
docker compose -f compose.all-in-one.yaml logs -f app

# 停止并清理容器与数据卷
docker compose -f compose.all-in-one.yaml down -v
```

访问地址：

```text
应用入口：http://127.0.0.1:8080
API 文档：http://127.0.0.1:8080/docs
```

### 分离模式

Linux / macOS / WSL：

```bash
# 自动检测镜像：已有则跳过构建，缺失则构建
./scripts/start-in-docker.sh --separated

# 只启动已有镜像，不构建；镜像缺失会失败
./scripts/start-in-docker.sh --separated --no-build

# 强制重新构建并启动
./scripts/start-in-docker.sh --separated --build

# 启动但不自动关闭端口冲突程序
./scripts/start-in-docker.sh --separated --no-kill

# 查看日志
./scripts/start-in-docker.sh --separated --logs

# 停止并清理容器与数据卷
./scripts/start-in-docker.sh --separated --down
```

Windows PowerShell：

```powershell
# 只启动已有镜像，不构建
docker compose -f compose.separated.yaml up -d --no-build

# 重新构建并启动
docker compose -f compose.separated.yaml up --build -d

# 查看日志
docker compose -f compose.separated.yaml logs -f backend frontend

# 停止并清理容器与数据卷
docker compose -f compose.separated.yaml down -v
```

访问地址：

```text
前端入口：http://127.0.0.1:8080
后端 API：http://127.0.0.1:8000
API 文档：http://127.0.0.1:8000/docs
```

### Docker 配置文件

| 文件 | 说明 |
|------|------|
| `docker/backend.Dockerfile` | 后端生产镜像，只包含 FastAPI 应用和 Python 生产依赖 |
| `docker/frontend.Dockerfile` | 前端生产镜像，Vite 构建后由 nginx 托管静态资源 |
| `docker/all-in-one.Dockerfile` | 合并应用镜像，包含前端 dist、FastAPI 后端和 nginx |
| `docker/nginx/all-in-one.conf` | 合并镜像 nginx 配置，同源代理 `/api` 到内部后端 |
| `docker/nginx/frontend.conf` | 分离前端 nginx 配置 |
| `compose.all-in-one.yaml` | 合并应用镜像 + PostgreSQL + Redis + Neo4j |
| `compose.separated.yaml` | 前端镜像 + 后端镜像 + PostgreSQL + Redis + Neo4j |
| `compose.yaml` | 仅基础设施，供本地非 Docker 应用开发使用 |
| `compose.test.yaml` | Docker 后端测试环境 |

## Docker 镜像打包

### Linux / macOS / WSL

构建三份应用镜像并导出本地 tar 包：

```bash
./scripts/build-docker-images.sh
```

指定分离前端的 API 地址：

```bash
./scripts/build-docker-images.sh --frontend-api-base "https://api.example.com"
```

### Windows PowerShell

如果使用 Docker Desktop，可直接在 PowerShell 中执行：

```powershell
docker build -f docker/backend.Dockerfile -t blank-learning/backend:local .
docker build -f docker/frontend.Dockerfile --build-arg VITE_API_BASE_URL= -t blank-learning/frontend:local .
docker build -f docker/all-in-one.Dockerfile -t blank-learning/all-in-one:local .

New-Item -ItemType Directory -Force dist/docker-images | Out-Null
docker save -o dist/docker-images/blank-backend-local.tar blank-learning/backend:local
docker save -o dist/docker-images/blank-frontend-local.tar blank-learning/frontend:local
docker save -o dist/docker-images/blank-all-in-one-local.tar blank-learning/all-in-one:local
```

也可以在 WSL 或 Git Bash 中直接运行：

```bash
./scripts/build-docker-images.sh
```

默认导出产物：

```text
dist/docker-images/blank-backend-local.tar
dist/docker-images/blank-frontend-local.tar
dist/docker-images/blank-all-in-one-local.tar
```

重新导入镜像：

```bash
docker load -i dist/docker-images/blank-backend-local.tar
docker load -i dist/docker-images/blank-frontend-local.tar
docker load -i dist/docker-images/blank-all-in-one-local.tar
```

PowerShell 同样可使用 `docker load -i ...`。

## 本地开发启动

如果不想把应用放进 Docker，可以只用 Docker 启动 PostgreSQL、Redis 和 Neo4j，然后本机运行前后端开发服务。

Linux / macOS / WSL：

```bash
./scripts/infra.sh up
./start.sh
```

Windows PowerShell：

```powershell
docker compose -f compose.yaml up -d
.\start.ps1
```

访问：

```text
前端：http://localhost:5173
后端：http://localhost:8000/docs
```

Conda 手动启动：

```bash
conda env create -f environment.yml
conda activate blank-learning
cd pwa && npm install && cd ..
./scripts/dev.sh
```

venv 手动启动：

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements-dev.txt
cd pwa && npm install && cd ..
./scripts/dev.sh
```

Windows PowerShell 手动启动：

```powershell
py -3 -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt
cd pwa
npm install
cd ..
.\start.ps1
```

开发脚本默认只监听本机 `127.0.0.1`。确需远程访问时，需要显式设置 `BLANK_BACKEND_HOST` / `BLANK_FRONTEND_HOST`，并同步配置 `BLANK_ALLOWED_HOSTS` 与 `BLANK_CORS_ORIGINS`。

前端生产构建：

```bash
cd pwa
npm run build
```

## 测试与安全审计

本地后端测试：

```bash
source backend/.venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest backend/test_api.py backend/test_v2_api.py backend/test_sag_rag.py backend/test_ocr_materials.py backend/test_concurrency.py
```

Windows PowerShell：

```powershell
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt
python -m pytest backend\test_api.py backend\test_v2_api.py backend\test_sag_rag.py backend\test_ocr_materials.py backend\test_concurrency.py
```

Docker 后端测试：

```bash
./scripts/test-in-docker.sh
```

Windows PowerShell：

```powershell
docker compose -f compose.test.yaml up -d postgres redis neo4j
$testDbExists = docker compose -f compose.test.yaml exec -T postgres psql -U blank -d postgres -tc "select 1 from pg_database where datname = 'blank_test'" | Select-String "1" -Quiet
if (-not $testDbExists) { docker compose -f compose.test.yaml exec -T postgres createdb -U blank blank_test }
docker compose -f compose.test.yaml up --build --abort-on-container-exit backend-test
docker compose -f compose.test.yaml down -v
```

完整安全审计：

```bash
./scripts/security-audit.sh
```

这个脚本会串行执行后端测试、生产启动门禁模拟、开发环境外网监听保护、部署模板静态检查、供应链依赖检查、secret 泄露扫描、本地生产 API URL 探测、前端部署 URL 探测、前端 CSP/CSRF/管理员重认证静态检查、前端生产构建和 `npm audit`。

常用专项检查：

```bash
./scripts/test-production-security.sh
./scripts/check-deploy-templates.sh
./scripts/test-secret-scan.sh
./scripts/check-supply-chain.sh
```

## 主要接口

- `GET /api/health`：健康检查。
- `POST /api/parse-jobs` / `POST /api/parse-jobs/upload`：创建持久化解析任务。
- `GET /api/parse-jobs/{id}`：查询解析进度，完成后返回学习会话。
- `GET /api/sessions`：读取当前用户历史学习记录，管理员可查看全部。
- `GET /api/sessions/{id}`：读取会话。
- `POST /api/sessions/{id}/select-node`：切换当前节点。
- `POST /api/sessions/{id}/chat`：V1 学习流回退接口。
- `POST /api/sessions/{id}/chat/stream`：V1 流式学习流回退接口。
- `POST /api/v2/chat/stream`：V2 多智能体主路线流式接口。
- `GET /api/speech/capabilities`：查询当前用户可用的 ASR/TTS 能力。
- `POST /api/speech/asr/transcribe`：上传录音并转写为文本。
- `POST /api/speech/tts`：将导师或题目文本合成为音频。
- `POST /api/sessions/{id}/feynman/questions`：生成费曼验证题。
- `POST /api/sessions/{id}/feynman/follow-up`：生成费曼追问。
- `POST /api/sessions/{id}/feynman/answer`：保存单题回答。
- `POST /api/sessions/{id}/feynman`：提交费曼解释并获得诊断。
- `POST /api/auth/register` / `POST /api/auth/login` / `POST /api/auth/logout`：认证接口。
- `PATCH /api/me/account`：当前账号修改用户名或密码，需提供当前密码。
- `GET/POST/PATCH /api/admin/users`：后台用户创建、组织绑定和权限管理。
- `GET /api/admin/organizations`：后台组织列表。
- `GET/POST/PATCH/DELETE /api/admin/api-configs`：后台 API 配置管理。
- `GET/POST/PATCH/DELETE /api/admin/speech-configs`：后台语音配置管理。
- `GET /api/admin/research-dashboard`：教师/研究端聚合指标。
- `POST /api/admin/research-experiments`：导入匿名实验记录。
- `GET /api/admin/research-experiments/export`：导出匿名实验记录。
- `GET /api/admin/research-blind-review/export`：导出匿名费曼答卷。
- `GET /api/organizations/current`：当前组织信息和当前成员身份。
- `GET /api/organizations/current/members`：组织成员列表和概要统计。
- `GET /api/organizations/current/members/{user_id}/report`：组织成员学习报告和费曼维度数据。
- `GET /api/organizations/current/dashboard`：组织范围研究面板。
- `GET /api/organizations/current/export`：组织成员完整学习溯源导出，包含对话、费曼问题/答案/追问/评分和节点轨迹。
- `POST /api/organizations/current/tasks`：组织管理者创建学习任务，可下发给全部成员或指定成员。
- `GET /api/me/tasks` / `POST /api/me/tasks/{task_id}/start`：组织成员查看并启动任务。
- `GET /api/organizations/current/knowledge`：组织知识库列表。
- `POST /api/organizations/current/knowledge/upload`：上传组织知识库资料。
- `DELETE /api/organizations/current/knowledge/{id}`：删除组织知识库资料。

当前知识点拆分、学习状态判断、导师对话、费曼诊断和记忆推荐都通过已启用的模型配置真实请求 LLM。如果未启用 API 配置、模型接口连接失败、认证失败或返回格式错误，前端会显示清晰错误，不会静默失败或使用本地伪结果。

## 环境变量

| 变量 | 说明 | 开发默认值 |
|------|------|------------|
| `BLANK_ENV` | 运行环境：`development` 或 `production` | `development` |
| `BLANK_SECRET_KEY` | API Key 加密主密钥，生产环境必须为强随机值 | 自动生成本地密钥 |
| `BLANK_TOKEN_HASH_KEY` | 登录 token HMAC 专用密钥，可选 | 复用 `BLANK_SECRET_KEY` |
| `BLANK_ADMIN_BOOTSTRAP_KEY` | 首个管理员引导密钥 | 示例占位符 |
| `BLANK_ALLOWED_HOSTS` | 允许的 Host 头，逗号分隔 | `localhost,127.0.0.1` |
| `BLANK_CORS_ORIGINS` | 允许的前端来源，逗号分隔 | 多个 localhost 端口 |
| `BLANK_DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://blank:blank@127.0.0.1:5432/blank` |
| `BLANK_DB_POOL_MIN_CONN` | PostgreSQL 连接池最小连接数 | `1` |
| `BLANK_DB_POOL_MAX_CONN` | PostgreSQL 连接池最大连接数 | `20` |
| `BLANK_REDIS_URL` | Redis 限流连接字符串 | `redis://127.0.0.1:6379/0` |
| `BLANK_RAG_BACKEND` | RAG 后端：`sag` 或 `legacy_neo4j` | `sag` |
| `BLANK_OCR_ENABLED` | 是否启用图片 OCR 解析 | `false` |
| `BLANK_UNLIMITED_OCR_BASE_URL` | Unlimited-OCR HTTP 服务 Base URL | 空 |
| `BLANK_UNLIMITED_OCR_PATH` | Unlimited-OCR 接口路径 | `/ocr` |
| `BLANK_UNLIMITED_OCR_REQUEST_MODE` | OCR 请求模式：`multipart` 或 `json` | `multipart` |
| `BLANK_OCR_TIMEOUT_SECONDS` | OCR 请求超时秒数 | `60` |
| `BLANK_ASR_BASE_URL` | ASR 环境变量回退 Base URL；后台语音配置优先 | 空 |
| `BLANK_ASR_PROVIDER` | ASR Provider 标识 | `sensevoice-openai` |
| `BLANK_ASR_TRANSCRIBE_PATH` | ASR 转写接口路径 | `/v1/audio/transcriptions` |
| `BLANK_ASR_MODEL` | ASR 模型名 | `SenseVoiceSmall` |
| `BLANK_ASR_API_KEY` | ASR API Key；后台配置会加密存储 | `blank-local-asr` |
| `BLANK_TTS_BASE_URL` | TTS 环境变量回退 Base URL；后台语音配置优先 | 空 |
| `BLANK_TTS_PROVIDER` | TTS Provider 标识 | `supertonic-http` |
| `BLANK_TTS_PATH` | TTS 合成接口路径 | `/v1/audio/speech` |
| `BLANK_TTS_MODEL` | TTS 模型名 | `supertonic` |
| `BLANK_TTS_API_KEY` | TTS API Key；后台配置会加密存储 | `blank-local-tts` |
| `BLANK_TTS_VOICE` | 默认 TTS 音色 | `F1` |
| `BLANK_TTS_LANGUAGE` | 默认 TTS 语言 | `zh` |
| `BLANK_TTS_RESPONSE_FORMAT` | 默认 TTS 返回格式 | `wav` |
| `BLANK_SPEECH_READ_TIMEOUT` | ASR/TTS 请求读取超时秒数 | `90` |
| `BLANK_GRAPHRAG_ENABLED` | 旧 Neo4j GraphRAG 是否启用，仅 `legacy_neo4j` 模式使用 | `true` |
| `BLANK_NEO4J_URI` | Neo4j 连接地址，仅 `legacy_neo4j` 模式使用 | `bolt://127.0.0.1:7687` |
| `BLANK_NEO4J_USER` | Neo4j 用户名，仅 `legacy_neo4j` 模式使用 | `neo4j` |
| `BLANK_NEO4J_PASSWORD` | Neo4j 密码，仅 `legacy_neo4j` 模式使用 | 无默认安全值 |
| `BLANK_MAX_REQUEST_BYTES` | 非上传 JSON 请求体上限 | `1048576` |
| `BLANK_ALLOW_PRIVATE_MODEL_URLS` | 是否允许模型 URL 指向私有地址 | `false` |
| `BLANK_TRUST_PROXY_HEADERS` | 是否信任 `X-Forwarded-*` | `false` |
| `BLANK_TRUSTED_PROXIES` | 可信反代 IP/CIDR 列表 | 空 |
| `BLANK_ALLOW_PUBLIC_REGISTRATION` | 是否开放公开注册 | `false` |
| `VITE_API_BASE_URL` | 前端编译时 API 地址 | `http://localhost:8000` |

生产环境必须显式设置强密钥、实际域名 Host/CORS、HTTPS 反向代理和数据库凭据。语音服务推荐在后台管理中配置；若改用环境变量回退，生产环境的 ASR/TTS Base URL 也必须满足模型接口相同的 HTTPS 与 SSRF 防护要求。

## 安全与部署

后端默认启用以下保护：

- Host 白名单、CORS、Fetch Metadata 和 CSRF 双提交校验。
- 请求体大小限制、上传大小限制、登录/注册/聊天/费曼/管理员写操作限流。
- HttpOnly Cookie 会话，服务端 HMAC 存储登录 token。
- 后台 API Key 使用 Fernet 加密存储。
- 模型 Base URL 在保存和请求阶段做 SSRF 防护。
- 后台语音配置的 API Key 同样加密存储，ASR/TTS Base URL 复用模型请求的 SSRF 防护和重定向拦截。
- 管理员用户权限和 API 配置写操作要求最近 10 分钟内重新认证。
- 生产环境关闭 `/docs`、`/redoc` 和 `/openapi.json`。

生产环境启动硬门槛：

- `BLANK_SECRET_KEY` 至少 32 字符，且不能使用示例占位符。
- `BLANK_ADMIN_BOOTSTRAP_KEY` 至少 24 字符，且不能使用示例占位符。
- `BLANK_ALLOWED_HOSTS` 必须显式配置，不能包含通配符。
- `BLANK_CORS_ORIGINS` 必须显式配置 HTTPS 来源，不能使用 localhost/内网地址。
- Cookie 必须启用 `Secure`，`SameSite` 不能为 `none`。
- `BLANK_ALLOW_PRIVATE_MODEL_URLS` 必须为 `false`。

生产部署模板在 `deploy/`：

- `deploy/blank.env.example`：生产环境变量模板。
- `deploy/blank-api.service`：systemd 后端服务模板。
- `deploy/nginx.blank.conf`：nginx HTTPS 反向代理和静态前端托管模板。
- `deploy/blank-backup.service` / `deploy/blank-backup.timer`：PostgreSQL 定时备份。
- `deploy/logrotate.blank`：日志轮转。
- `deploy/fail2ban.blank-auth.conf` / `deploy/fail2ban.blank-jail.local`：登录失败和管理员重认证失败封禁。

上线后检查真实部署：

```bash
./scripts/check-deployment-url.sh https://blank.example.com
```

本机联调允许 HTTP：

```bash
./scripts/check-deployment-url.sh --allow-local-http http://127.0.0.1:8080
```

PostgreSQL 备份和恢复：

```bash
./scripts/backup-postgres.sh
./scripts/restore-postgres.sh --yes backups/blank-YYYYmmddTHHMMSSZ.dump
```

恢复生产库前请先停止后端服务。恢复脚本会先调用 `backup-postgres.sh` 为当前数据库创建安全备份，再使用 `pg_restore --clean --if-exists` 恢复。
