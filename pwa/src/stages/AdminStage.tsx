import { FormEvent, useState, type ReactNode } from "react";
import { ArrowRight, Bot, Mic2, Plus, Save, UsersRound } from "lucide-react";
import type { AdminUserCreateInput, AdminUserUpdateInput, ApiConfigInput, SpeechConfigInput } from "../api";
import { PagedList, SegmentedControl } from "../components/DesignPrimitives";
import { V2ModeToggle } from "../components/V2ModeToggle";
import type { ApiConfig, Organization, SpeechConfig, User, UserRole } from "../types";

interface AdminStageProps {
  users: User[];
  organizations: Organization[];
  apiConfigs: ApiConfig[];
  speechConfigs: SpeechConfig[];
  form: ApiConfigInput;
  speechForm: SpeechConfigInput;
  isBusy: boolean;
  v2Enabled: boolean;
  onFormChange: (value: ApiConfigInput) => void;
  onSpeechFormChange: (value: SpeechConfigInput) => void;
  onSaveConfig: (event: FormEvent<HTMLFormElement>) => void;
  onSaveSpeechConfig: (event: FormEvent<HTMLFormElement>) => void;
  onRefresh: () => void;
  onToggleV2: () => void;
  onEditConfig: (config: ApiConfig) => void;
  onToggleConfig: (config: ApiConfig) => void;
  onDeleteConfig: (config: ApiConfig) => void;
  onEditSpeechConfig: (config: SpeechConfig) => void;
  onToggleSpeechConfig: (config: SpeechConfig) => void;
  onDeleteSpeechConfig: (config: SpeechConfig) => void;
  onCreateUser: (payload: AdminUserCreateInput) => void;
  onRoleChange: (user: User, payload: AdminUserUpdateInput) => void;
  onActiveToggle: (user: User) => void;
}

type AdminTab = "model" | "speech" | "users";

const adminTabs: Record<AdminTab, { label: string; caption: string; icon: ReactNode }> = {
  model: { label: "模型", caption: "配置默认模型接口和可用 Provider。", icon: <Bot size={16} /> },
  speech: { label: "语音", caption: "管理 ASR/TTS 服务配置。", icon: <Mic2 size={16} /> },
  users: { label: "用户", caption: "创建账号并调整角色权限。", icon: <UsersRound size={16} /> },
};

export function AdminStage({
  users,
  organizations,
  apiConfigs,
  speechConfigs,
  form,
  speechForm,
  isBusy,
  v2Enabled,
  onFormChange,
  onSpeechFormChange,
  onSaveConfig,
  onSaveSpeechConfig,
  onRefresh,
  onToggleV2,
  onEditConfig,
  onToggleConfig,
  onDeleteConfig,
  onEditSpeechConfig,
  onToggleSpeechConfig,
  onDeleteSpeechConfig,
  onCreateUser,
  onRoleChange,
  onActiveToggle,
}: AdminStageProps) {
  const [activeTab, setActiveTab] = useState<AdminTab>(() => resolveInitialAdminTab());
  const [createDraft, setCreateDraft] = useState<AdminUserCreateInput>({
    username: "",
    password: "",
    role: "learner",
    is_active: true,
    organization_name: "",
    organization_code: "",
  });
  const [userDrafts, setUserDrafts] = useState<Record<string, { role: UserRole; organizationCode: string; organizationName: string }>>({});
  const activeConfigCount = apiConfigs.filter((config) => isKnownApiProvider(config.provider) && config.is_active).length;
  const activeSpeechCount = speechConfigs.filter((config) => config.is_active).length;
  const activeUserCount = users.filter((item) => item.is_active).length;
  const invalidConfigCount = apiConfigs.filter((config) => !isKnownApiProvider(config.provider)).length;
  const todayTokens = users.reduce((total, item) => total + (item.today_tokens ?? 0), 0);
  const totalTokens = users.reduce((total, item) => total + (item.total_tokens ?? 0), 0);
  const applyPreset = (preset: ApiConfigInput) => {
    onFormChange({ ...form, ...preset, api_key: form.api_key });
  };
  const applySpeechPreset = (preset: SpeechConfigInput) => {
    onSpeechFormChange({ ...speechForm, ...preset, api_key: speechForm.api_key });
  };
  const organizationCodes = organizations.map((organization) => organization.code);
  const updateUserDraft = (
    userId: string,
    user: User,
    patch: Partial<{ role: UserRole; organizationCode: string; organizationName: string }>,
  ) => {
    setUserDrafts((current) => ({
      ...current,
      [userId]: {
        role: current[userId]?.role ?? user.role,
        organizationCode: current[userId]?.organizationCode ?? user.organization_code ?? "",
        organizationName: current[userId]?.organizationName ?? "",
        ...patch,
      },
    }));
  };
  const userDraftFor = (item: User) => (
    userDrafts[item.id] ?? {
      role: item.role,
      organizationCode: item.organization_code ?? "",
      organizationName: "",
    }
  );
  const submitCreateUser = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onCreateUser(createDraft);
    setCreateDraft({
      username: "",
      password: "",
      role: "learner",
      is_active: true,
      organization_name: "",
      organization_code: "",
    });
  };
  const applyUserDraft = (item: User) => {
    const draft = userDraftFor(item);
    onRoleChange(item, {
      role: draft.role,
      organization_code: draft.organizationCode,
      organization_name: draft.organizationName,
    });
  };

  return (
    <div className="admin-layout admin-tabbed">
      <section className="admin-panel admin-command-panel">
        <div className="section-heading">
          <p className="eyebrow">API Settings</p>
          <h2>后台管理</h2>
          <span>配置模型接口、管理用户权限。</span>
        </div>
        <div className="admin-status-strip" aria-label="后台状态">
          <div>
            <span>活跃模型</span>
            <strong>{activeConfigCount}/{apiConfigs.length}</strong>
          </div>
          <div>
            <span>语音服务</span>
            <strong>{activeSpeechCount}/{speechConfigs.length}</strong>
          </div>
          <div>
            <span>今日 Token</span>
            <strong title={`${todayTokens} tokens`}>{formatTokenCount(todayTokens)}</strong>
          </div>
          <div className={invalidConfigCount > 0 ? "risk" : ""}>
            <span>配置风险</span>
            <strong>{invalidConfigCount > 0 ? `${invalidConfigCount} 项异常` : "无异常"}</strong>
          </div>
          <p>
            {activeUserCount}/{users.length} 个用户可用；累计模型消耗 {formatTokenCount(totalTokens)} token。权限和 API 写操作需要最近管理员重认证；未执行连通性测试时不显示模型健康结论。
          </p>
        </div>
        <div className="admin-mode-panel" aria-label="学习链路模式">
          <div>
            <span>默认学习链路</span>
            <strong>{v2Enabled ? "V2 多智能体" : "V1 过时回退"}</strong>
            <small>{v2Enabled ? "聊天默认进入 Router / Socrates / Critic 工作流。" : "仅用于故障回退，不作为当前主路线。"}</small>
          </div>
          <V2ModeToggle enabled={v2Enabled} onToggle={onToggleV2} />
        </div>
        <SegmentedControl
          label="后台管理视图"
          value={activeTab}
          options={adminTabs}
          orientation="vertical"
          className="admin-tabs"
          onChange={setActiveTab}
        />
      </section>

      {activeTab === "model" && (
        <>
          <section className="admin-panel admin-config-panel admin-tab-panel">
            <div className="section-heading admin-heading-row">
              <div>
                <p className="eyebrow">Model Provider</p>
                <h3>模型接口</h3>
              </div>
            </div>
            <form className="admin-form" onSubmit={onSaveConfig}>
          <div className="provider-presets" aria-label="常用模型预设">
            {API_CONFIG_PRESETS.map((preset) => (
              <button
                className="secondary-button compact"
                type="button"
                key={preset.label}
                onClick={() => applyPreset(preset.value)}
                disabled={isBusy}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <label>
            <span>格式</span>
            <select
              value={form.provider}
              onChange={(event) =>
                onFormChange({ ...form, provider: event.target.value as ApiConfigInput["provider"] })
              }
            >
              <option value="openai">openai</option>
              <option value="vllm">vllm</option>
              <option value="ollama">ollama</option>
              <option value="custom">custom</option>
            </select>
          </label>
          <label>
            <span>Base URL</span>
            <input
              value={form.base_url}
              onChange={(event) => onFormChange({ ...form, base_url: event.target.value })}
              placeholder="https://api.openai.com/v1"
            />
          </label>
          <label>
            <span>API Key</span>
            <input
              value={form.api_key}
              onChange={(event) => onFormChange({ ...form, api_key: event.target.value })}
              placeholder="sk-..."
            />
          </label>
          <label>
            <span>Model</span>
            <input
              value={form.model}
              onChange={(event) => onFormChange({ ...form, model: event.target.value })}
              placeholder="gpt-4.1-mini / llama3"
            />
          </label>
          <label className="toggle-line">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => onFormChange({ ...form, is_active: event.target.checked })}
            />
            <span>启用</span>
          </label>
          <div className="flow-actions">
            <button className="secondary-button" type="button" onClick={onRefresh} disabled={isBusy}>
              刷新
            </button>
            <button className="primary-button" type="submit" disabled={isBusy}>
              保存配置
              <ArrowRight size={18} />
            </button>
          </div>
            </form>
          </section>
        </>
      )}

      {activeTab === "speech" && (
        <>
          <section className="admin-panel admin-config-panel admin-tab-panel">
            <div className="section-heading admin-heading-row">
              <div>
                <p className="eyebrow">Speech Provider</p>
                <h3>语音接口</h3>
              </div>
            </div>
        <form className="admin-form" onSubmit={onSaveSpeechConfig}>
          <div className="provider-presets" aria-label="常用语音预设">
            {SPEECH_CONFIG_PRESETS.map((preset) => (
              <button
                className="secondary-button compact"
                type="button"
                key={preset.label}
                onClick={() => applySpeechPreset(preset.value)}
                disabled={isBusy}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <label>
            <span>类型</span>
            <select
              value={speechForm.kind}
              onChange={(event) =>
                onSpeechFormChange({
                  ...speechForm,
                  kind: event.target.value as SpeechConfigInput["kind"],
                  path: event.target.value === "asr" ? "/v1/audio/transcriptions" : "/v1/audio/speech",
                  model: event.target.value === "asr" ? "SenseVoiceSmall" : "supertonic",
                })
              }
            >
              <option value="asr">ASR</option>
              <option value="tts">TTS</option>
            </select>
          </label>
          <label>
            <span>Provider</span>
            <input
              value={speechForm.provider}
              onChange={(event) => onSpeechFormChange({ ...speechForm, provider: event.target.value })}
              placeholder={speechForm.kind === "asr" ? "sensevoice-openai" : "supertonic-http"}
            />
          </label>
          <label>
            <span>Base URL</span>
            <input
              value={speechForm.base_url}
              onChange={(event) => onSpeechFormChange({ ...speechForm, base_url: event.target.value })}
              placeholder={speechForm.kind === "asr" ? "http://127.0.0.1:10098" : "http://127.0.0.1:7788"}
            />
          </label>
          <label>
            <span>API Key</span>
            <input
              value={speechForm.api_key}
              onChange={(event) => onSpeechFormChange({ ...speechForm, api_key: event.target.value })}
              placeholder={speechForm.kind === "asr" ? "blank-local-asr" : "blank-local-tts"}
            />
          </label>
          <label>
            <span>Model</span>
            <input
              value={speechForm.model}
              onChange={(event) => onSpeechFormChange({ ...speechForm, model: event.target.value })}
              placeholder={speechForm.kind === "asr" ? "SenseVoiceSmall" : "supertonic"}
            />
          </label>
          <label>
            <span>Path</span>
            <input
              value={speechForm.path}
              onChange={(event) => onSpeechFormChange({ ...speechForm, path: event.target.value })}
              placeholder={speechForm.kind === "asr" ? "/v1/audio/transcriptions" : "/v1/audio/speech"}
            />
          </label>
          {speechForm.kind === "tts" && (
            <>
              <label>
                <span>Voice</span>
                <input
                  value={speechForm.voice ?? ""}
                  onChange={(event) => onSpeechFormChange({ ...speechForm, voice: event.target.value })}
                  placeholder="F1"
                />
              </label>
              <label>
                <span>Language</span>
                <input
                  value={speechForm.language ?? ""}
                  onChange={(event) => onSpeechFormChange({ ...speechForm, language: event.target.value })}
                  placeholder="zh"
                />
              </label>
              <label>
                <span>Format</span>
                <select
                  value={speechForm.response_format ?? "wav"}
                  onChange={(event) => onSpeechFormChange({ ...speechForm, response_format: event.target.value })}
                >
                  <option value="wav">wav</option>
                  <option value="mp3">mp3</option>
                  <option value="opus">opus</option>
                </select>
              </label>
            </>
          )}
          <label className="toggle-line">
            <input
              type="checkbox"
              checked={speechForm.is_active}
              onChange={(event) => onSpeechFormChange({ ...speechForm, is_active: event.target.checked })}
            />
            <span>启用</span>
          </label>
          <div className="flow-actions">
            <button className="secondary-button" type="button" onClick={onRefresh} disabled={isBusy}>
              刷新
            </button>
            <button className="primary-button" type="submit" disabled={isBusy}>
              保存语音配置
              <ArrowRight size={18} />
            </button>
          </div>
        </form>
      </section>
        </>
      )}

      <div className={`admin-stack ${activeTab === "users" ? "admin-users-stack" : ""}`}>
        {activeTab === "model" && (
        <section className="admin-panel admin-list-panel">
          <div className="section-heading admin-heading-row">
            <div>
              <p className="eyebrow">Configured Providers</p>
              <h3>API 配置</h3>
            </div>
            <b>{apiConfigs.length}</b>
          </div>
          <PagedList
            items={apiConfigs}
            pageSize={2}
            ariaLabel="API 配置"
            className="admin-list-pager"
            empty={<p className="admin-empty">暂无 API 配置。</p>}
            renderItem={(config) => {
              const providerIsValid = isKnownApiProvider(config.provider);
              return (
                <div className={`admin-row ${providerIsValid ? "" : "invalid"}`} key={config.id}>
                  <div>
                    <strong>{config.provider}</strong>
                    <span>{config.base_url}</span>
                    <small>
                      {providerIsValid ? config.model || "未设置模型" : "配置异常，请删除后重建"} · {config.api_key_masked || "无 key"}
                    </small>
                  </div>
                  <div className="row-actions">
                    <b>{providerIsValid ? (config.is_active ? "启用" : "停用") : "异常"}</b>
                    <button
                      className="secondary-button compact"
                      type="button"
                      onClick={() => onEditConfig(config)}
                      disabled={!providerIsValid}
                    >
                      载入
                    </button>
                    <button
                      className="secondary-button compact"
                      type="button"
                      onClick={() => onToggleConfig(config)}
                      disabled={isBusy || !providerIsValid}
                    >
                      {config.is_active ? "停用" : "启用"}
                    </button>
                    <button
                      className="secondary-button compact danger"
                      type="button"
                      onClick={() => onDeleteConfig(config)}
                      disabled={isBusy}
                    >
                      删除
                    </button>
                  </div>
                </div>
              );
            }}
          />
        </section>
        )}

        {activeTab === "speech" && (
        <section className="admin-panel admin-list-panel">
          <div className="section-heading admin-heading-row">
            <div>
              <p className="eyebrow">Speech</p>
              <h3>语音配置</h3>
            </div>
            <b>{speechConfigs.length}</b>
          </div>
          <PagedList
            items={speechConfigs}
            pageSize={2}
            ariaLabel="语音配置"
            className="admin-list-pager"
            empty={<p className="admin-empty">暂无语音配置。</p>}
            renderItem={(config) => (
              <div className="admin-row" key={config.id}>
                <div>
                  <strong>{speechKindLabel(config.kind)} · {config.provider}</strong>
                  <span>{config.base_url}</span>
                  <small>
                    {config.model} · {config.path} · {config.api_key_masked || "无 key"}
                    {config.kind === "tts" && config.voice ? ` · ${config.voice}` : ""}
                  </small>
                </div>
                <div className="row-actions">
                  <b>{config.is_active ? "启用" : "停用"}</b>
                  <button
                    className="secondary-button compact"
                    type="button"
                    onClick={() => onEditSpeechConfig(config)}
                    disabled={isBusy}
                  >
                    载入
                  </button>
                  <button
                    className="secondary-button compact"
                    type="button"
                    onClick={() => onToggleSpeechConfig(config)}
                    disabled={isBusy}
                  >
                    {config.is_active ? "停用" : "启用"}
                  </button>
                  <button
                    className="secondary-button compact danger"
                    type="button"
                    onClick={() => onDeleteSpeechConfig(config)}
                    disabled={isBusy}
                  >
                    删除
                  </button>
                </div>
              </div>
            )}
          />
        </section>
        )}

        {activeTab === "users" && (
        <section className="admin-panel admin-list-panel admin-users-panel">
          <div className="section-heading admin-heading-row">
            <div>
              <p className="eyebrow">Users</p>
              <h3>用户与权限</h3>
            </div>
            <b>{users.length}</b>
          </div>
          <form className="admin-user-create-form" onSubmit={submitCreateUser}>
            <label>
              <span>账号</span>
              <input
                value={createDraft.username}
                minLength={2}
                maxLength={32}
                onChange={(event) => setCreateDraft({ ...createDraft, username: event.target.value })}
                placeholder="username"
              />
            </label>
            <label>
              <span>密码</span>
              <input
                type="password"
                value={createDraft.password}
                minLength={8}
                onChange={(event) => setCreateDraft({ ...createDraft, password: event.target.value })}
                placeholder="至少 8 位"
              />
            </label>
            <label>
              <span>角色</span>
              <select
                value={createDraft.role}
                onChange={(event) => setCreateDraft({ ...createDraft, role: event.target.value as UserRole })}
              >
                <option value="learner">个人学习者</option>
                <option value="org_member">组织成员</option>
                <option value="org_manager">组织管理者</option>
                <option value="admin">系统管理员</option>
              </select>
            </label>
            {createDraft.role === "org_member" && (
              <label>
                <span>组织 ID</span>
                <input
                  value={createDraft.organization_code ?? ""}
                  list="admin-organization-codes"
                  minLength={4}
                  maxLength={32}
                  onChange={(event) => setCreateDraft({ ...createDraft, organization_code: event.target.value })}
                  placeholder="ORG-XXXX"
                />
              </label>
            )}
            {createDraft.role === "org_manager" && (
              <>
                <label>
                  <span>新组织名</span>
                  <input
                    value={createDraft.organization_name ?? ""}
                    maxLength={80}
                    onChange={(event) => setCreateDraft({ ...createDraft, organization_name: event.target.value })}
                    placeholder="例如：高一物理组"
                  />
                </label>
                <label>
                  <span>组织 ID</span>
                  <input
                    value={createDraft.organization_code ?? ""}
                    list="admin-organization-codes"
                    maxLength={32}
                    onChange={(event) => setCreateDraft({ ...createDraft, organization_code: event.target.value })}
                    placeholder="绑定已有组织"
                  />
                </label>
              </>
            )}
            <label className="toggle-line">
              <input
                type="checkbox"
                checked={createDraft.is_active ?? true}
                onChange={(event) => setCreateDraft({ ...createDraft, is_active: event.target.checked })}
              />
              <span>启用</span>
            </label>
            <button className="primary-button compact" type="submit" disabled={isBusy}>
              <Plus size={16} />
              创建
            </button>
            <datalist id="admin-organization-codes">
              {organizationCodes.map((code) => (
                <option value={code} key={code} />
              ))}
            </datalist>
          </form>
          <PagedList
            items={users}
            pageSize={1}
            ariaLabel="用户与权限"
            className="admin-list-pager"
            empty={<p className="admin-empty">暂无用户。</p>}
            renderItem={(item) => {
              const draft = userDraftFor(item);
              return (
                <div className="admin-row user-row" key={item.id}>
                  <div>
                    <strong>{item.username}</strong>
                    <span>{roleLabel(item.role)}{item.organization_name ? ` · ${item.organization_name}` : ""}</span>
                    <small>{item.username} · {roleLabel(item.role)} · {item.is_active ? "账号启用" : "账号停用"}{item.organization_code ? ` · ${item.organization_code}` : ""}</small>
                    <div className="user-token-metrics" aria-label={`${item.username} token 用量`}>
                      <span title={`${item.total_tokens ?? 0} tokens`}>
                        <b>{formatTokenCount(item.total_tokens ?? 0)}</b>
                        总 token
                      </span>
                      <span title={`${item.today_tokens ?? 0} tokens`}>
                        <b>{formatTokenCount(item.today_tokens ?? 0)}</b>
                        今日 token
                      </span>
                    </div>
                  </div>
                  <div className="row-actions user-role-actions">
                    <select
                      className="compact-role-select"
                      value={draft.role}
                      onChange={(event) => updateUserDraft(item.id, item, { role: event.target.value as UserRole })}
                      disabled={isBusy}
                    >
                      <option value="admin">系统管理员</option>
                      <option value="org_manager">组织管理者</option>
                      <option value="org_member">组织成员</option>
                      <option value="learner">个人学习者</option>
                    </select>
                    {(draft.role === "org_manager" || draft.role === "org_member") && (
                      <input
                        className="compact-org-input"
                        value={draft.organizationCode}
                        list="admin-organization-codes"
                        onChange={(event) => updateUserDraft(item.id, item, { organizationCode: event.target.value })}
                        placeholder="组织 ID"
                        disabled={isBusy}
                      />
                    )}
                    {draft.role === "org_manager" && (
                      <input
                        className="compact-org-input"
                        value={draft.organizationName}
                        onChange={(event) => updateUserDraft(item.id, item, { organizationName: event.target.value })}
                        placeholder="新组织名"
                        disabled={isBusy}
                      />
                    )}
                    <button
                      className="secondary-button compact"
                      type="button"
                      onClick={() => applyUserDraft(item)}
                      disabled={isBusy}
                    >
                      <Save size={14} />
                      应用
                    </button>
                    <button
                      className="secondary-button compact"
                      type="button"
                      onClick={() => onActiveToggle(item)}
                      disabled={isBusy}
                    >
                      {item.is_active ? "停用" : "启用"}
                    </button>
                  </div>
                </div>
              );
            }}
          />
        </section>
        )}
      </div>
    </div>
  );
}

function isKnownApiProvider(provider: string): provider is ApiConfigInput["provider"] {
  return provider === "openai" || provider === "vllm" || provider === "ollama" || provider === "custom";
}

function formatTokenCount(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}m`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(value >= 10_000 ? 0 : 1)}k`;
  return `${value}`;
}

function roleLabel(role: UserRole) {
  switch (role) {
    case "admin":
      return "系统管理员";
    case "org_manager":
      return "组织管理者";
    case "org_member":
      return "组织成员";
    case "learner":
      return "个人学习者";
  }
}

function speechKindLabel(kind: SpeechConfig["kind"]) {
  return kind === "asr" ? "ASR" : "TTS";
}

const API_CONFIG_PRESETS: Array<{ label: string; value: ApiConfigInput }> = [
  {
    label: "Kimi",
    value: {
      provider: "openai",
      base_url: "https://api.moonshot.cn/v1",
      api_key: "",
      model: "kimi-latest",
      is_active: true,
    },
  },
  {
    label: "DeepSeek",
    value: {
      provider: "openai",
      base_url: "https://api.deepseek.com",
      api_key: "",
      model: "deepseek-chat",
      is_active: true,
    },
  },
  {
    label: "OpenAI",
    value: {
      provider: "openai",
      base_url: "https://api.openai.com/v1",
      api_key: "",
      model: "gpt-4.1-mini",
      is_active: true,
    },
  },
];

const SPEECH_CONFIG_PRESETS: Array<{ label: string; value: SpeechConfigInput }> = [
  {
    label: "SenseVoice",
    value: {
      kind: "asr",
      provider: "sensevoice-openai",
      base_url: "http://127.0.0.1:10098",
      api_key: "",
      model: "SenseVoiceSmall",
      path: "/v1/audio/transcriptions",
      is_active: true,
      voice: "",
      language: "zh",
      response_format: "",
    },
  },
  {
    label: "Supertonic",
    value: {
      kind: "tts",
      provider: "supertonic-http",
      base_url: "http://127.0.0.1:7788",
      api_key: "",
      model: "supertonic",
      path: "/v1/audio/speech",
      is_active: true,
      voice: "F1",
      language: "zh",
      response_format: "wav",
    },
  },
];

function resolveInitialAdminTab(): AdminTab {
  if (!import.meta.env.DEV || typeof window === "undefined") return "model";
  const tab = new URLSearchParams(window.location.search).get("ui-review-admin");
  return tab === "speech" || tab === "users" ? tab : "model";
}
