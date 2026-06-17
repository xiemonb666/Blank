import type { Persona } from "../types";

export const personas: Record<
  Persona,
  {
    label: string;
    caption: string;
    prompt: string;
  }
> = {
  plain: {
    label: "大白话",
    caption: "短句、类比、先抓核心",
    prompt: "把抽象概念换成日常语言，用连续提问确认理解。",
  },
  vivid: {
    label: "生动有趣",
    caption: "比喻、节奏、轻量故事",
    prompt: "用有画面感的例子降低枯燥感，但保留关键逻辑。",
  },
  academic: {
    label: "严谨学术",
    caption: "定义、边界、推导链条",
    prompt: "强调概念边界、前置依赖和可验证的逻辑推导。",
  },
};

export const PARSE_JOB_STORAGE_KEY = "blank_parse_job_id";
export const AUTH_SESSION_STORAGE_KEY = "blank_auth_session";
export const LEGACY_TOKEN_STORAGE_KEY = "blank_token";
export const CHAT_SUBMIT_COOLDOWN_MS = 1500;
