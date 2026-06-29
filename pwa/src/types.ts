export type Persona = "plain" | "vivid" | "academic";
export type TutorLearningStyle = "visual" | "verbal" | "active";
export type TutorCommunicationType = "socratic" | "story" | "textbook" | "coach";
export type NodeStatus = "mastered" | "active" | "available" | "locked";
export type Stage = "canvas" | "map" | "flow" | "feynman" | "mastery" | "evidence" | "research" | "admin";
export type UserRole = "admin" | "learner";
export type ApiProvider = "openai" | "vllm" | "ollama" | "custom";
export type ChallengeStage = "warmup" | "mechanism" | "transfer" | "correction" | "recap";

export interface KnowledgeNode {
  id: string;
  title: string;
  summary: string;
  evidence?: string;
  complexity_reason?: string;
  complexity: 1 | 2 | 3 | 4 | 5;
  weight: number;
  status: NodeStatus;
  x: number;
  y: number;
  deps: string[];
}

export interface Message {
  role: "mentor" | "learner";
  text: string;
  node_id?: string | null;
  thinking?: string | null;
  created_at?: string;
}

export interface TutorSettings {
  depth_level: number;
  learning_style: TutorLearningStyle;
  communication_type: TutorCommunicationType;
}

export interface DiagnosticItem {
  label: string;
  value: number;
  note: string;
}

export interface DimensionScore {
  stage: ChallengeStage;
  label: string;
  value: number;
  note: string;
}

export interface NodeLearningProfile {
  node_id: string;
  stage: ChallengeStage;
  dimension_scores: Partial<Record<ChallengeStage, number>>;
  weak_points: string[];
  streak: number;
  failures: number;
  confusion_requests: number;
  confusion_resolved: number;
  confusion_unresolved: number;
  last_challenge: string;
  next_challenge: string;
  badge: string;
  updated_at: string;
}

export interface FeynmanQuestion {
  id: string;
  label: string;
  question: string;
  focus: string;
  difficulty: number;
  stage: ChallengeStage;
  follow_up_of?: string | null;
}

export interface FeynmanAnswer {
  question_id: string;
  label: string;
  question: string;
  answer: string;
  focus?: string | null;
  difficulty?: number | null;
  stage?: ChallengeStage | null;
  follow_up_of?: string | null;
}

export interface FeynmanFollowUpState {
  needed: boolean;
  reason: string;
  question_id?: string | null;
}

export interface QuestionDiagnosticItem {
  question_id: string;
  label: string;
  value: number;
  note: string;
  stage: ChallengeStage;
}

export interface FeynmanAssessmentRecord {
  diagnostics: DiagnosticItem[];
  question_diagnostics: QuestionDiagnosticItem[];
  dimension_scores: DimensionScore[];
  passed: boolean;
  mastery_state: "not_passed" | "passed_next_available" | "passed_path_complete" | "passed_waiting_prerequisite";
  next_reason: string;
  updated_at: string;
}

export interface MemoryEntry {
  id: string;
  kind: "fact" | "cognitive" | "session" | "preference" | "long_term";
  scope: "task" | "node" | "long_term";
  node_id: string | null;
  retention: "short" | "medium" | "long";
  importance: number;
  title: string;
  body: string;
  reason: string;
  created_at: string;
}

export interface User {
  id: string;
  username: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  total_tokens: number;
  today_tokens: number;
}

export interface ApiConfig {
  id: string;
  provider: ApiProvider | string;
  base_url: string;
  api_key_masked: string;
  model: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SpeechCapabilities {
  asr_enabled: boolean;
  tts_enabled: boolean;
  asr_provider?: string | null;
  asr_model?: string | null;
  tts_provider?: string | null;
  tts_voice?: string | null;
}

export interface SpeechTranscription {
  text: string;
  provider?: string | null;
  model?: string | null;
}

export interface ResearchMetric {
  label: string;
  value: number;
  unit: string;
  note: string;
}

export interface WeakPointSummary {
  label: string;
  count: number;
  average_score: number;
}

export interface FeynmanDistributionBucket {
  label: string;
  min_score: number;
  max_score: number;
  count: number;
}

export interface MaterialQualitySummary {
  session_id: string;
  title: string;
  node_count: number;
  evidence_coverage: number;
  dependency_edges: number;
  average_complexity: number;
  updated_at: string;
}

export interface MemoryCategorySummary {
  category: string;
  count: number;
  long_term_count: number;
}

export interface ResearchExperimentRecordInput {
  id?: string | null;
  study_id: string;
  participant_code: string;
  group_label: string;
  material_label?: string;
  pretest_score?: number | null;
  posttest_score?: number | null;
  delayed_score?: number | null;
  system_feynman_score?: number | null;
  human_score?: number | null;
  learning_minutes?: number | null;
  cognitive_load?: number | null;
  notes?: string;
}

export interface ResearchExperimentRecord extends ResearchExperimentRecordInput {
  id: string;
  material_label: string;
  notes: string;
  imported_at: string;
  updated_at: string;
}

export interface ResearchExperimentImportResponse {
  imported_count: number;
  records: ResearchExperimentRecord[];
}

export interface ResearchExperimentGroupSummary {
  study_id: string;
  group_label: string;
  participants: number;
  pretest_average: number | null;
  posttest_average: number | null;
  delayed_average: number | null;
  average_gain: number | null;
  retention_rate: number | null;
  learning_minutes_average: number | null;
  cognitive_load_average: number | null;
}

export interface ResearchScoreAgreement {
  paired_count: number;
  correlation: number | null;
  mean_absolute_gap: number | null;
  system_average: number | null;
  human_average: number | null;
}

export interface ResearchExperimentExport {
  generated_at: string;
  records: ResearchExperimentRecord[];
}

export interface ResearchBlindReviewAnswer {
  sample_id: string;
  session_id: string;
  node_id: string;
  node_title: string;
  question_id: string;
  question_label: string;
  question: string;
  answer: string;
  system_score: number | null;
  system_note: string;
  updated_at: string;
}

export interface ResearchBlindReviewExport {
  generated_at: string;
  answers: ResearchBlindReviewAnswer[];
}

export interface ResearchDashboard {
  generated_at: string;
  metrics: ResearchMetric[];
  weak_points: WeakPointSummary[];
  feynman_distribution: FeynmanDistributionBucket[];
  common_misconceptions: WeakPointSummary[];
  material_quality: MaterialQualitySummary[];
  memory_categories: MemoryCategorySummary[];
  experiment_summaries: ResearchExperimentGroupSummary[];
  score_agreement: ResearchScoreAgreement;
  experiment_records: ResearchExperimentRecord[];
}
