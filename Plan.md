# 《Blank》V2 主路线与挑战杯证据化路线图

**产品愿景**：通过极简界面和 AI 引导，把学习材料转化为“输入 -> 拆解 -> 学习 -> 输出（费曼）-> 证据化研究”的闭环体验。当前主路线是 V2 多智能体 + GraphRAG + PostgreSQL + Redis。

---

## 一、当前主路线（V2）

V2 是当前默认产品路径，面向比赛演示、内测和后续生产演练。

1. **材料输入与解析**
   - 支持 PDF、TXT、Markdown、CSV、JSON 等文本型材料。
   - 上传后进入持久化解析任务，刷新页面仍能轮询进度。
   - 解析完成或失败后清空解析任务中的原始材料内容，减少长期留存。

2. **知识节点与 GraphRAG**
   - 后端调用已启用的 OpenAI/vLLM/Ollama/Custom 兼容模型，把材料拆成知识节点。
   - 节点包含复杂度、权重、前置依赖、解锁状态和二维布局坐标。
   - GraphRAG 默认启用，解析完成后尝试写入 Neo4j 实体、关系和向量片段。
   - 图实体、关系和向量块按 `tenant_id`、`user_id`、`session_id`、`source_id` 隔离；索引或检索失败时回退到当前材料片段并记录原因。

3. **多智能体学习流**
   - 默认接口：`POST /api/v2/chat/stream`。
   - 已接入主认证、CSRF、用户隔离和会话持久化。
   - Router / Socrates / Feynman / Critic 工作流以流式状态暴露给前端，并把用户消息、导师回复和可映射的费曼维度分写回学习会话。

4. **费曼验证与记忆**
   - 当前以文本回答为主，按基础理解、机制解释、迁移应用、纠错复述等维度诊断。
   - 评分结果写回节点画像、掌握状态和记忆系统。
   - 通过后推荐下一个可学习节点；长期偏好、跨节点卡点和反复困惑进入长期记忆类别。

5. **账号、权限和默认基础设施**
   - 主数据存储为 PostgreSQL，通过 `SessionStore` 封装。
   - Redis 是默认限流后端；只有测试环境或显式 `BLANK_ALLOW_IN_MEMORY_RATE_LIMIT=true` 才允许内存回退。
   - 使用 HttpOnly Cookie + CSRF 双提交令牌。
   - 后台 API Key 加密存储，管理员敏感写操作需要最近 10 分钟内重新验证密码。

---

## 二、V1 过时回退

V1 单链路导师接口仍保留用于故障排查和紧急回退，但不再作为产品主路线或答辩主叙事。

- 接口：`POST /api/sessions/{id}/chat` 与 `POST /api/sessions/{id}/chat/stream`。
- 前端后台可切回 V1，但 UI 明确标记为“V1 过时回退”。
- 新功能、教师端指标和 GraphRAG 证据优先沿 V2 路径补齐。

---

## 三、教师端 / 研究端

管理员可进入教师/研究端查看真实聚合指标，当前已覆盖：

- 班级薄弱维度分布。
- 费曼评分分布。
- 材料节点质量：节点数、证据覆盖率、依赖边数量、平均复杂度。
- 常见误区排行。
- 长期记忆类别。
- 今日和累计 token 消耗。
- 匿名实验记录导入/导出。
- 前测、后测、延迟测、组间对比和保持率。
- 系统费曼评分与人工盲评分一致性。
- 匿名费曼答卷导出，供教师盲评。

后续国赛证据建设优先补：

- 真实 30 到 60 人样本数据。
- ChatGPT / 自学 / 题库对照组真实执行记录。
- 消融实验：聊天、聊天+节点、聊天+节点+费曼、聊天+节点+费曼+记忆。

---

## 四、上线门禁

上线或提交评审前至少执行：

```bash
python -m compileall backend/app
cd pwa && npm run security:check && npm run build
./scripts/check-deploy-templates.sh
```

完整环境验证需要 PostgreSQL、Redis、Neo4j 和模型 API 配置可用后再运行：

```bash
./scripts/infra.sh up
python -m pytest backend/test_api.py backend/test_v2_api.py
./scripts/security-audit.sh
```

生产环境还必须完成：

- 显式配置 `BLANK_SECRET_KEY`、`BLANK_ADMIN_BOOTSTRAP_KEY`、`BLANK_ALLOWED_HOSTS`、`BLANK_CORS_ORIGINS`。
- 显式配置 `BLANK_DATABASE_URL`、`BLANK_REDIS_URL`、`BLANK_NEO4J_URI`、`BLANK_NEO4J_PASSWORD`。
- 使用 HTTPS 反向代理，后端只监听本机地址。
- 禁止生产环境开启私有模型 URL。
- 跑通 PostgreSQL 备份和恢复演练。
