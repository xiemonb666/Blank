# Blank

Blank 是一个教育学习闭环 MVP，包含黑白线条风前端和 FastAPI 后端。

## 当前架构状态

- V2 主路线：前端默认使用 `/api/v2/chat/stream` 多智能体流式对话，已接入主认证、CSRF、用户隔离、会话持久化、GraphRAG 检索和材料片段回退。
- V1 过时回退：旧 `/api/sessions/{id}/chat` 单链路导师仍保留用于故障回退，不再作为产品主路线。
- GraphRAG 默认能力：默认启用 Neo4j 图谱与向量检索；解析完成后会尝试写入实体、关系和向量片段，检索或索引失败会记录原因并回退到当前材料片段。
- 数据库默认值：PostgreSQL 是默认主存储，Redis 是默认限流后端，Neo4j 是默认 GraphRAG 底座。SQLite 路线已移除。

## 功能

- 材料输入：上传 PDF、TXT、Markdown、CSV、JSON，创建学习会话；扫描版 PDF 会提示先 OCR。
- 解析状态：材料提交后进入持久化解析任务，刷新页面会继续显示解析进度，直到完成或失败。
- 知识拓扑：根据材料生成知识节点、复杂度、依赖关系和解锁状态；可接入外部模型增强解析质量。
- 苏格拉底学习流：前端调节 Persona；对话保持流式输出，并记录困惑状态。
- 思考摘要：导师消息上方显示可展开的推理要点摘要，帮助理解回答依据。
- 自适应降维：连续卡顿后自动切换到大白话解释。
- 费曼验证：提交解释后返回概念覆盖、逻辑连贯、表达负荷诊断。
- 记忆系统：PostgreSQL 按用户持久化会话、消息与认知记录。
- 账号系统：注册、登录、HttpOnly Cookie 会话、双提交 CSRF 校验、管理员/学习者权限。
- 后台管理：配置 OpenAI / vLLM / Ollama / Custom 的 Base URL、API Key 和模型，支持启停/删除 API 配置，管理用户权限与启停。启用新配置会自动停用其他配置。
- 教师/研究端：管理员可查看班级薄弱点、费曼评分分布、材料节点质量、常见误区、长期记忆类别和 token 成本指标；支持导入/导出匿名前测、后测、延迟测、组别和人工盲评记录，并可导出匿名费曼答卷用于教师盲评。

## 启动

一键启动：

```bash
./start.sh
```

Windows 用户可使用 PowerShell 版本：

```powershell
.\start.ps1
```

脚本会自动选择 `blank-learning` Conda 环境或 `backend/.venv`，缺少依赖时安装后端和前端依赖，并启动前端 `5173` 与后端 `8000`。如果服务已经在运行，会直接打印访问地址。默认基础设施必须已经可用；本机开发可先运行 `./scripts/infra.sh up`，或直接使用 `./start.sh --with-infra` / `.\start.ps1 -WithInfra` 让脚本通过 Docker Compose 启动 PostgreSQL、Redis 和 Neo4j。

本地默认基础设施：

```bash
./scripts/infra.sh up
./scripts/infra.sh status
```

推荐使用 Conda 隔离环境：

```bash
conda env create -f environment.yml
conda activate blank-learning
cd pwa && npm install && cd ..
./scripts/dev.sh
```

也可以使用本地 venv：

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements-dev.txt
cd pwa && npm install && cd ..
./scripts/dev.sh
```

访问：

```text
前端：http://localhost:5173/
后端：http://localhost:8000/docs
```

默认开发脚本只监听本机 `127.0.0.1`，避免把服务暴露到局域网。确需远程访问时再显式设置
`BLANK_BACKEND_HOST` / `BLANK_FRONTEND_HOST`，并同步配置 `BLANK_ALLOWED_HOSTS` 与 `BLANK_CORS_ORIGINS`；如果监听非本机地址但未配置 Host/CORS，脚本会拒绝启动。

## 构建

```bash
cd pwa
npm run build
```

## 测试

```bash
source backend/.venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest backend/test_api.py backend/test_v2_api.py
```

完整安全审计可以直接运行：

```bash
./scripts/security-audit.sh
```

这个脚本会串行执行后端测试、生产启动门禁模拟、开发环境外网监听保护、部署模板静态检查、供应链依赖检查、secret 泄露扫描、本地生产 API URL 探测、前端部署 URL 探测、前端 CSP/CSRF/管理员重认证静态检查、前端生产构建和 `npm audit`。生产启动门禁也可以单独运行：

```bash
./scripts/test-production-security.sh
```

## 接口

- `POST /api/sessions`：用文本创建学习会话。
- `POST /api/sessions/upload`：上传文件创建学习会话。
- `POST /api/parse-jobs` / `POST /api/parse-jobs/upload`：创建持久化解析任务，限制短时间重复提交。
- `GET /api/parse-jobs/{id}`：查询解析进度，完成后返回生成的学习会话。
- `GET /api/sessions`：读取当前用户历史学习记录，管理员可查看全部。
- `GET /api/sessions/{id}`：读取会话。
- `POST /api/sessions/{id}/select-node`：切换当前节点。
- `POST /api/sessions/{id}/chat`：发送学习流消息。
- `POST /api/sessions/{id}/chat/stream`：流式发送学习流消息，返回思考摘要、增量文本和完成状态。
- `POST /api/v2/chat/stream`：V2 多智能体主路线流式接口，使用同一套 Cookie/CSRF/用户隔离安全模型，并把用户消息和导师回复写回学习会话。
- `POST /api/sessions/{id}/feynman`：提交费曼解释并获得诊断。
- `POST /api/auth/register` / `POST /api/auth/login`：注册登录。
- `GET /api/admin/research-dashboard`：教师/研究端聚合指标，读取真实学习记录和管理员导入的匿名实验记录。
- `POST /api/admin/research-experiments`：管理员导入匿名前后测、延迟测、组别和人工盲评记录，要求最近 10 分钟内重认证。
- `GET /api/admin/research-experiments/export`：导出匿名实验记录 JSON，不包含用户名、材料原文或聊天正文。
- `GET /api/admin/research-blind-review/export`：导出匿名费曼答卷，供教师盲评，不包含用户名、材料原文或聊天正文。
- `GET /api/admin/users`：后台用户管理。
- `GET/POST/PATCH/DELETE /api/admin/api-configs`：后台 API 配置管理。

当前知识点拆分、学习状态判断、导师对话、费曼诊断和记忆推荐都通过已启用的模型配置真实请求 LLM；如果未启用 API 配置、模型接口连接失败、认证失败或返回格式错误，前端会显示清晰错误，不会静默失败或使用本地伪结果。
当 Base URL 为 `https://api.kimi.com/coding/...` 时，后端会自动添加 `User-Agent: KimiCLI/1.6`，并使用后台 API Key 作为 `Authorization: Bearer <token>`；Kimi coding 请求超时默认放宽到 120 秒。

## 安全配置

- `BLANK_ALLOWED_HOSTS`：允许的 Host 头，生产环境必须设置为实际域名，多个值用逗号分隔。
- `BLANK_CORS_ORIGINS`：允许访问后端的前端来源，生产环境必须设置为实际 HTTPS 前端地址。
- `BLANK_ADMIN_BOOTSTRAP_KEY`：首次注册管理员的引导密钥；生产环境至少 24 个字符，不能使用 `.env.example` 占位符。
- `BLANK_SECRET_KEY`：API Key 加密主密钥，至少 32 个字符；生产环境必须设置随机强值并妥善保管，不能使用 `.env.example` 占位符。
- `BLANK_TOKEN_HASH_KEY`：可选的登录 token HMAC 专用密钥；生产环境如设置，至少 32 个字符且不能使用占位符。未设置时使用 `BLANK_SECRET_KEY`。
- `BLANK_DATABASE_URL`：PostgreSQL 连接字符串，默认 `postgresql://blank:blank@127.0.0.1:5432/blank`。
- `BLANK_REDIS_URL`：Redis 限流后端，默认 `redis://127.0.0.1:6379/0`。仅测试环境或显式 `BLANK_ALLOW_IN_MEMORY_RATE_LIMIT=true` 才允许内存限流回退。
- `BLANK_MAX_REQUEST_BYTES`：非上传 JSON 请求体大小上限，默认 1MB。
- `BLANK_MODEL_CONNECT_TIMEOUT`：模型接口单个解析地址的 TCP 连接超时，默认 12 秒；同一域名多个地址会自动重试。
- `BLANK_MODEL_READ_TIMEOUT` / `BLANK_SLOW_MODEL_READ_TIMEOUT`：模型接口响应读取超时，默认 90 秒；Kimi/DeepSeek 等慢接口默认 240 秒。
- `BLANK_DEBUG_LOG_ENABLED` / `BLANK_DEBUG_LOG_PATH`：高细节调试日志开关和路径，默认写入 `backend/data/debug.log`，记录请求、响应、LLM 输入输出和 V2 agent/RAG 事件。
- `BLANK_DEBUG_LOG_ROTATE_WHEN` / `BLANK_DEBUG_LOG_MAX_BYTES` / `BLANK_DEBUG_LOG_BACKUP_COUNT`：调试日志按时间和大小轮转，默认每天轮转、单文件 10MB、保留 14 份。
- `BLANK_ALLOW_PRIVATE_MODEL_URLS`：仅本地开发/测试可设为 true；生产环境不要开启，避免模型 Base URL SSRF 风险。
- `BLANK_TRUST_PROXY_HEADERS`：只有在可信反向代理已经清洗 `X-Forwarded-For` 时才开启。
- `BLANK_ALLOW_PUBLIC_REGISTRATION`：生产环境默认关闭公开注册；只有明确需要开放注册时才设为 true。首个管理员仍可通过 `BLANK_ADMIN_BOOTSTRAP_KEY` 初始化。
- `BLANK_GRAPHRAG_ENABLED`：GraphRAG 默认启用；只有显式设为 `false` / `0` / `off` 才关闭。
- `BLANK_NEO4J_URI` / `BLANK_NEO4J_USER` / `BLANK_NEO4J_PASSWORD`：GraphRAG 的 Neo4j 连接配置。必须显式配置密码；未配置密码时索引/检索会失败并回退到材料片段。

后端会默认限制 Host、CORS、请求体大小、上传大小、登录/注册频率、模型 Base URL、token 有效期，使用服务密钥 HMAC 存储登录 token，并加密保存后台 API Key。模型外连会在配置保存和实际请求时校验 Base URL，并在请求连接阶段阻断 DNS 重绑定到内网、本机或保留地址。浏览器 Cookie 会话的写请求需要可信 Origin 和 `X-CSRF-Token` 双提交校验。设置 `BLANK_ENV=production` 后，启动时会强制检查 Host/CORS/主密钥/管理员引导密钥等生产安全配置。
后台用户权限和 API 配置写操作要求管理员在最近 10 分钟内重新验证密码，并对重认证失败做限流和审计，降低长期会话被盗后直接劫持模型配置或权限的风险。
已存在账号的登录失败会写入审计日志，但不会记录密码内容，也不会在登录响应中暴露账号是否存在。
生产环境还会关闭 `/docs`、`/redoc` 和 `/openapi.json`，避免公开接口结构。
生产环境默认禁止普通公开注册，防止公网部署后被任意创建账号；除非显式设置 `BLANK_ALLOW_PUBLIC_REGISTRATION=true`。
如果生产环境沿用 `change-this...`、`example`、`password` 等示例弱密钥，后端会拒绝启动。
上线前必须至少跑通 `./scripts/security-audit.sh`，并在真实部署层完成 HTTPS、反向代理 Host 白名单、访问日志脱敏、数据库备份和恢复演练。
生产启动 uvicorn 时必须加 `--no-server-header`，反向代理也不要回写 `Server`、`X-Powered-By` 等实现信息；`./scripts/check-deployment-url.sh` 会检查这类暴露。

`deploy/` 目录提供生产部署硬化模板：

- `deploy/blank.env.example`：生产环境变量模板，替换域名和所有密钥后放到 `/etc/blank/blank.env`。
- `deploy/blank-api.service`：systemd 服务模板，后端只监听 `127.0.0.1`，开启 systemd 沙箱和最小写路径。
- `deploy/nginx.blank.conf`：nginx HTTPS 反向代理模板，包含 TLS、HSTS、Host 转发、隐藏实现头和静态前端托管。
- `deploy/blank-backup.service` / `deploy/blank-backup.timer`：每 6 小时执行 PostgreSQL 逻辑备份，适合安装到 systemd。
- `deploy/logrotate.blank`：轮转 `/var/log/blank` 和 nginx Blank 日志，保留 30 天并压缩。
- `deploy/fail2ban.blank-auth.conf` / `deploy/fail2ban.blank-jail.local`：读取 `/var/log/blank/security.log`，对重复登录失败和管理员重认证失败做封禁。

修改模板后运行：

```bash
./scripts/check-deploy-templates.sh
```

提交或部署前也可以单独运行 secret 扫描：

```bash
./scripts/test-secret-scan.sh
```

脚本会先注入临时假泄露 key，确认扫描器能失败，再清理临时文件并跑正式扫描。扫描会跳过 `node_modules`、构建产物、运行数据和缓存目录，拦截私钥、真实形态 OpenAI key、长 Bearer token、JWT、GitHub token、AWS access key 和明显硬编码强密钥。测试假 key 和模板占位符会被允许。

供应链检查可以单独运行：

```bash
./scripts/check-supply-chain.sh
```

脚本会要求 Python requirements 使用 `==` 精确固定版本、拒绝 URL/git/file 依赖，要求 `package-lock.json` 使用官方 npm registry、包含 integrity，并拒绝危险 npm script。若环境安装了 `pip-audit`，还会自动审计 Python 漏洞。

上线后对真实后端域名执行：

```bash
./scripts/check-deployment-url.sh https://blank.example.com
```

脚本会检查 HTTPS、HSTS、API 与前端根路径的关键安全响应头、前端 HTTP CSP、`/docs` 和 `/openapi.json` 是否关闭，以及异常 Host 头是否被拒绝。只有本机联调才允许：

```bash
./scripts/check-deployment-url.sh --allow-local-http http://127.0.0.1:8000
```

PostgreSQL 数据库备份和恢复：

```bash
./scripts/backup-postgres.sh
./scripts/restore-postgres.sh --yes backups/blank-YYYYmmddTHHMMSSZ.dump
```

恢复生产库前先停止后端服务；恢复脚本会先调用 `backup-postgres.sh` 为当前 PostgreSQL 数据库创建安全备份，再使用 `pg_restore --clean --if-exists` 恢复。
