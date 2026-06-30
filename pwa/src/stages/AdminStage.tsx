import { FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import type { ApiConfigInput } from "../api";
import { PagedList } from "../components/DesignPrimitives";
import { V2ModeToggle } from "../components/V2ModeToggle";
import type { ApiConfig, User } from "../types";

interface AdminStageProps {
  users: User[];
  apiConfigs: ApiConfig[];
  form: ApiConfigInput;
  isBusy: boolean;
  v2Enabled: boolean;
  onFormChange: (value: ApiConfigInput) => void;
  onSaveConfig: (event: FormEvent<HTMLFormElement>) => void;
  onRefresh: () => void;
  onToggleV2: () => void;
  onEditConfig: (config: ApiConfig) => void;
  onToggleConfig: (config: ApiConfig) => void;
  onDeleteConfig: (config: ApiConfig) => void;
  onRoleChange: (user: User, role: "admin" | "learner") => void;
  onActiveToggle: (user: User) => void;
}

export function AdminStage({
  users,
  apiConfigs,
  form,
  isBusy,
  v2Enabled,
  onFormChange,
  onSaveConfig,
  onRefresh,
  onToggleV2,
  onEditConfig,
  onToggleConfig,
  onDeleteConfig,
  onRoleChange,
  onActiveToggle,
}: AdminStageProps) {
  const activeConfigCount = apiConfigs.filter((config) => isKnownApiProvider(config.provider) && config.is_active).length;
  const activeUserCount = users.filter((item) => item.is_active).length;
  const invalidConfigCount = apiConfigs.filter((config) => !isKnownApiProvider(config.provider)).length;
  const todayTokens = users.reduce((total, item) => total + (item.today_tokens ?? 0), 0);
  const totalTokens = users.reduce((total, item) => total + (item.total_tokens ?? 0), 0);
  const applyPreset = (preset: ApiConfigInput) => {
    onFormChange({ ...form, ...preset, api_key: form.api_key });
  };

  return (
    <div className="admin-layout">
      <section className="admin-panel admin-config-panel">
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

      <div className="admin-stack">
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

        <section className="admin-panel admin-list-panel">
          <div className="section-heading admin-heading-row">
            <div>
              <p className="eyebrow">Users</p>
              <h3>用户与权限</h3>
            </div>
            <b>{users.length}</b>
          </div>
          <PagedList
            items={users}
            pageSize={2}
            ariaLabel="用户与权限"
            className="admin-list-pager"
            empty={<p className="admin-empty">暂无用户。</p>}
            renderItem={(item) => (
              <div className="admin-row user-row" key={item.id}>
                <div>
                  <strong>{item.username}</strong>
                  <span>{item.role === "admin" ? "管理员" : "学习者"}</span>
                  <small>{item.is_active ? "账号启用" : "账号停用"}</small>
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
                <div className="row-actions">
                  <button
                    className="secondary-button compact"
                    type="button"
                    onClick={() => onRoleChange(item, item.role === "admin" ? "learner" : "admin")}
                    disabled={isBusy}
                  >
                    {item.role === "admin" ? "降为学习者" : "设为管理员"}
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
            )}
          />
        </section>
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
