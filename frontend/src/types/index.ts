import type {
  LegacyOrganizationCharacterFields,
  LegacyOrganizationPayloadFields,
} from '../utils/entityCompatibility';

// 用户类型定义
export interface User {
  user_id: string;
  username: string;
  display_name: string;
  avatar_url?: string;
  trust_level: number;
  is_admin: boolean;
  linuxdo_id: string;
  created_at: string;
  last_login: string;
}

export interface EmailLoginPayload {
  email: string;
  code: string;
}

export interface EmailRegisterPayload {
  email: string;
  code: string;
  password: string;
  display_name?: string;
}

export interface EmailSendCodePayload {
  email: string;
  scene: 'register' | 'login' | 'reset_password';
}

export interface EmailResetPasswordPayload {
  email: string;
  code: string;
  new_password: string;
}

export interface SystemSMTPSettings {
  id: string;
  user_id: string;
  smtp_provider: string;
  smtp_host?: string;
  smtp_port: number;
  smtp_username?: string;
  smtp_password?: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_from_email?: string;
  smtp_from_name: string;
  email_auth_enabled: boolean;
  email_register_enabled: boolean;
  verification_code_ttl_minutes: number;
  verification_resend_interval_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface SystemSMTPSettingsUpdate {
  smtp_provider?: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_username?: string;
  smtp_password?: string;
  smtp_use_tls?: boolean;
  smtp_use_ssl?: boolean;
  smtp_from_email?: string;
  smtp_from_name?: string;
  email_auth_enabled?: boolean;
  email_register_enabled?: boolean;
  verification_code_ttl_minutes?: number;
  verification_resend_interval_seconds?: number;
}

// 设置类型定义
export type ReasoningIntensity = 'auto' | 'off' | 'low' | 'medium' | 'high' | 'maximum';

export interface ReasoningCapability {
  provider: string;
  model_pattern: string;
  supported_intensities: ReasoningIntensity[];
  default_intensity: ReasoningIntensity;
  provider_metadata: {
    native_field?: string;
    payload_mappings?: Record<string, Record<string, unknown>>;
    read_only?: boolean;
  };
  last_verified_date: string;
  notes: string;
}

export interface ReasoningCapabilitiesResponse {
  intensities: ReasoningIntensity[];
  capabilities: ReasoningCapability[];
}

export interface Settings {
  id: string;
  user_id: string;
  api_provider: string;
  api_key: string;
  api_base_url: string;
  llm_model: string;
  temperature: number;
  max_tokens: number;
  system_prompt?: string;
  default_reasoning_intensity?: ReasoningIntensity;
  reasoning_overrides?: string;
  allow_ai_entity_generation?: boolean;
  cover_api_provider?: string;
  cover_api_key?: string;
  cover_api_base_url?: string;
  cover_image_model?: string;
  cover_enabled?: boolean;
  preferences?: string;
  created_at: string;
  updated_at: string;
}

export interface SettingsUpdate {
  api_provider?: string;
  api_key?: string;
  api_base_url?: string;
  llm_model?: string;
  temperature?: number;
  max_tokens?: number;
  system_prompt?: string;
  default_reasoning_intensity?: ReasoningIntensity;
  reasoning_overrides?: string;
  allow_ai_entity_generation?: boolean;
  cover_api_provider?: string;
  cover_api_key?: string;
  cover_api_base_url?: string;
  cover_image_model?: string;
  cover_enabled?: boolean;
  preferences?: string;
}

export interface FeatureFlags {
  local_assets_enabled: boolean;
}

// API预设相关类型定义
export interface APIKeyPresetConfig {
  api_provider: string;
  api_key: string;
  api_base_url?: string;
  llm_model: string;
  temperature: number;
  max_tokens: number;
  system_prompt?: string;
  default_reasoning_intensity?: ReasoningIntensity;
}

export interface APIKeyPreset {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  config: APIKeyPresetConfig;
}

export interface PresetCreateRequest {
  name: string;
  description?: string;
  config: APIKeyPresetConfig;
}

export interface PresetUpdateRequest {
  name?: string;
  description?: string;
  config?: APIKeyPresetConfig;
}

export interface PresetListResponse {
  presets: APIKeyPreset[];
  total: number;
  active_preset_id?: string;
  chapter_analysis_preset_id?: string;
}

// LinuxDO 授权 URL 响应
export interface AuthUrlResponse {
  auth_url: string;
  state: string;
}

export interface WorldSettingFieldDefinition {
  label: string;
  type: 'text' | 'textarea' | 'list';
  required: boolean;
}

export interface ProjectWorldSettingData {
  template_id?: string | null;
  template_name?: string | null;
  fields: Record<string, WorldSettingFieldDefinition>;
  values: Record<string, string | string[] | null>;
}

export interface WorldSettingTemplate {
  id: string;
  name: string;
  category: string;
  fields: Record<string, WorldSettingFieldDefinition>;
  example_data: Record<string, string | string[] | null>;
  is_system: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorldSettingTemplateListResponse {
  total: number;
  items: WorldSettingTemplate[];
}

export interface WorldSettingApplyTemplateRequest {
  project_id: string;
  template_id: string;
  values?: Record<string, string | string[] | null>;
  custom_fields?: Record<string, WorldSettingFieldDefinition>;
}

export interface WorldSettingApplyTemplateResponse {
  project_id: string;
  template: WorldSettingTemplate;
  world_setting_data: ProjectWorldSettingData;
}

// 项目类型定义
export interface Project {
  id: string;  // UUID字符串
  title: string;
  description?: string;
  theme?: string;
  genre?: string;
  target_words?: number;
  current_words: number;
  status: 'planning' | 'writing' | 'revising' | 'completed';
  wizard_status?: 'incomplete' | 'completed';
  wizard_step?: number;
  outline_mode: 'one-to-one' | 'one-to-many';  // 大纲章节模式
  world_time_period?: string;
  world_location?: string;
  world_atmosphere?: string;
  world_rules?: string;
  world_setting_data?: ProjectWorldSettingData;
  chapter_count?: number;
  narrative_perspective?: string;
  character_count?: number;
  cover_image_url?: string;
  cover_prompt?: string;
  cover_status?: 'none' | 'generating' | 'ready' | 'failed';
  cover_error?: string;
  cover_updated_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  title: string;
  description?: string;
  theme?: string;
  genre?: string;
  target_words?: number;
  outline_mode?: 'one-to-one' | 'one-to-many';  // 大纲章节模式,默认one-to-many
  wizard_status?: 'incomplete' | 'completed';
  wizard_step?: number;
  world_time_period?: string;
  world_location?: string;
  world_atmosphere?: string;
  world_rules?: string;
  world_setting_data?: ProjectWorldSettingData;
}

export interface ProjectUpdate {
  title?: string;
  description?: string;
  theme?: string;
  genre?: string;
  target_words?: number;
  status?: 'planning' | 'writing' | 'revising' | 'completed';
  world_time_period?: string;
  world_location?: string;
  world_atmosphere?: string;
  world_rules?: string;
  world_setting_data?: ProjectWorldSettingData;
  chapter_count?: number;
  narrative_perspective?: string;
  character_count?: number;
  // current_words 由章节内容自动计算，不在此接口中
}

// 向导专用的项目更新接口，包含向导流程控制字段
export interface ProjectWizardUpdate extends ProjectUpdate {
  wizard_status?: 'incomplete' | 'completed';
  wizard_step?: number;
}

export type OptimizableField =
  | 'title'
  | 'description'
  | 'theme'
  | 'genre'
  | 'world_time_period'
  | 'world_location'
  | 'world_atmosphere'
  | 'world_rules'
  | 'narrative_perspective';

export interface FieldSuggestion {
  value: string;
  reason: string;
}

export interface ProjectOptimizeResult {
  fields: Partial<Record<OptimizableField, FieldSuggestion>>;
  reply: string;
}

export interface OptimizeConversationTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface ProjectOptimizeRequest {
  requirement?: string;
  conversation_history?: OptimizeConversationTurn[];
  current_draft?: Partial<Record<OptimizableField, string>>;
}

// ==================== 项目本地资源 ====================

export type ProjectAssetType = 'avatar' | 'background' | 'sprite';

export interface ProjectAsset {
  id: string;
  project_id: string;
  user_id: string;
  asset_type: ProjectAssetType | string;
  display_name: string;
  original_filename: string;
  storage_filename: string;
  mime_type: string;
  file_size: number;
  content_hash: string;
  file_url: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectAssetListResponse {
  total: number;
  items: ProjectAsset[];
}

export interface ProjectAssetUploadRequest {
  asset_type: ProjectAssetType;
  display_name?: string;
  file: File;
}

// ==================== 创作会话 ====================

export type CreativeSessionStatus = 'active' | 'archived';
export type CreativeSessionRole = 'user' | 'assistant' | 'system' | 'note';

export interface CreativeSessionCreate {
  title: string;
  metadata?: Record<string, unknown> | null;
}

export interface CreativeSessionMessageCreate {
  role?: CreativeSessionRole;
  content: string;
  metadata?: Record<string, unknown> | null;
}

export interface CreativeSession {
  id: string;
  project_id: string;
  user_id: string;
  title: string;
  status: CreativeSessionStatus | string;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CreativeSessionMessage {
  id: string;
  session_id: string;
  project_id: string;
  user_id: string;
  role: CreativeSessionRole | string;
  content: string;
  position: number;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface CreativeSessionDetail extends CreativeSession {
  messages: CreativeSessionMessage[];
}

export interface CreativeSessionListResponse {
  total: number;
  items: CreativeSession[];
}

export interface CreativeSessionSearchResult {
  session_id: string;
  session_title: string;
  message_id: string;
  project_id: string;
  user_id: string;
  role: CreativeSessionRole | string;
  content: string;
  position: number;
  created_at?: string | null;
}

export interface CreativeSessionSearchResponse {
  query: string;
  total: number;
  items: CreativeSessionSearchResult[];
}

// ==================== 快捷回复 / 安全片段 ====================

export type QuickReplyActionType = 'safe_snippet';

export interface QuickReply {
  id: string;
  project_id: string;
  user_id: string;
  label: string;
  action_type: QuickReplyActionType | string;
  snippet: string;
  sort_order: number;
  enabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface QuickReplyCreate {
  label: string;
  action_type?: QuickReplyActionType;
  snippet: string;
  sort_order?: number;
  enabled?: boolean;
}

export interface QuickReplyUpdate {
  label?: string;
  action_type?: QuickReplyActionType;
  snippet?: string;
  sort_order?: number;
  enabled?: boolean;
}

export interface QuickReplyListResponse {
  total: number;
  items: QuickReply[];
}

export interface QuickReplyApplyRequest {
  session_id: string;
}

export interface QuickReplyApplyResponse {
  quick_reply: QuickReply;
  source_type: string;
  trace_label: string;
  action_type: QuickReplyActionType | string;
  applied_content: string;
  prompt_mutation: boolean;
  boundary_decision: string;
  emitted_message: CreativeSessionMessage;
}

// ==================== 旁白声音画像 / Voice Personas ====================

export type VoicePersonaScope = 'project' | 'session';

export interface VoicePersona {
  id: string;
  project_id: string;
  user_id: string;
  session_id?: string | null;
  scope: VoicePersonaScope | string;
  name: string;
  tone: string;
  style: string;
  point_of_view: string;
  constraints: string;
  sort_order: number;
  enabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface VoicePersonaCreate {
  name: string;
  tone?: string;
  style?: string;
  point_of_view?: string;
  constraints?: string;
  session_id?: string | null;
  sort_order?: number;
  enabled?: boolean;
}

export interface VoicePersonaUpdate {
  name?: string;
  tone?: string;
  style?: string;
  point_of_view?: string;
  constraints?: string;
  session_id?: string | null;
  sort_order?: number;
  enabled?: boolean;
}

export interface VoicePersonaListResponse {
  total: number;
  items: VoicePersona[];
}

export interface VoicePersonaPromptTraceItem {
  order: number;
  source_order: number;
  source_type: string;
  trace_id: string;
  id: string;
  name: string;
  scope: string;
  project_id?: string | null;
  session_id?: string | null;
  applied_session_id?: string | null;
  tone: string;
  style: string;
  point_of_view: string;
  constraints: string;
}

export interface VoicePersonaPromptTrace {
  source_type: string;
  trace_version: number;
  schema_version: string;
  trace_id: string;
  selected_voice_persona_id: string;
  selected_voice_persona_ids: string[];
  project_id?: string | null;
  session_id?: string | null;
  profile_scope: string;
  applied_scope: string;
  source_order: number;
  selected_count: number;
  profile: {
    id: string;
    name: string;
    tone: string;
    style: string;
    point_of_view: string;
    constraints: string;
    scope: string;
  };
  budget_estimate: {
    chars_used: number;
    estimated_tokens: number;
    chars_per_token: number;
  };
  items: VoicePersonaPromptTraceItem[];
  final_preview_text: string;
}

export interface VoicePersonaPromptPreviewRequest {
  persona_id: string;
  session_id?: string | null;
  base_prompt?: string;
  injection_enabled?: boolean;
}

export interface VoicePersonaPromptPreviewResponse {
  project_id: string;
  session_id?: string | null;
  trace: VoicePersonaPromptTrace;
  preview_prompt: string;
}

// ==================== 群像场景 / Group Scenes ====================

export interface GroupScenePromptTrace {
  source_type: string;
  trace_version: number;
  schema_version: string;
  trace_id: string;
  project_id: string;
  project_title: string;
  source_order: number;
  participant_character_ids: string[];
  selected_voice_persona_id?: string | null;
  selected_lore_ids: string[];
  selected_prompt_context: string;
  selected_count: number;
  participants: Array<Record<string, unknown>>;
  voice_persona_trace?: VoicePersonaPromptTrace | null;
  lore_items: Array<Record<string, unknown>>;
  boundary_decision: string;
  forbidden_runtime_semantics: string[];
  budget_estimate: {
    chars_used: number;
    estimated_tokens: number;
    chars_per_token: number;
  };
  final_preview_text: string;
}

export interface GroupScene {
  id: string;
  project_id: string;
  user_id: string;
  title: string;
  scenario: string;
  participant_character_ids: string[];
  selected_voice_persona_id?: string | null;
  selected_lore_ids: string[];
  prompt_context: string;
  draft_text: string;
  prompt_trace: GroupScenePromptTrace;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GroupSceneDraftRequest {
  title: string;
  scenario: string;
  participant_character_ids: string[];
  selected_voice_persona_id?: string | null;
  selected_lore_ids?: string[];
  prompt_context?: string;
  draft_text?: string | null;
}

export interface GroupSceneListResponse {
  total: number;
  items: GroupScene[];
}

// 项目创建向导
export interface ProjectWizardRequest {
  title: string;
  theme: string;
  genre?: string;
  chapter_count: number;
  narrative_perspective: string;
  character_count?: number;
  target_words?: number;
  outline_mode?: 'one-to-one' | 'one-to-many';  // 大纲章节模式
  world_building?: {
    time_period: string;
    location: string;
    atmosphere: string;
    rules: string;
  };
}

// ==================== 灵感模式共享契约 ====================

export interface InspirationOptionsContext {
  initial_idea?: string;
  title?: string;
  description?: string;
  theme?: string;
  genre?: string | string[];
  world_setting?: string;
  core_conflict?: string;
  protagonist?: string;
  golden_finger?: string | null;
  [key: string]: unknown;
}

export interface InspirationGuidance {
  channel?: string;
  genre?: string;
  themes?: string[];
  characters?: string[];
  plots?: string[];
  plot_brief?: string;
}

export interface InspirationDirectionCard {
  id: string;
  title: string;
  hook: string;
  genre: string[];
  world_setting: string;
  core_conflict: string;
  protagonist: string;
  golden_finger?: string | null;
  opening_hook: string;
  selling_points: string[];
  risks: string[];
}

export interface InspirationStoryBibleDraft {
  core_idea: string;
  story_promise: string;
  target_genre: string[];
  world_rules: string[];
  core_conflict: string;
  protagonist_profile: string;
  antagonistic_force: string;
  golden_finger?: string | null;
  opening_hook: string;
  tone_and_style: string;
  foreshadowing_seeds: string[];
  constraints: string[];
}

export interface InspirationGenerationContext {
  source: 'inspiration_story_bible';
  initial_idea?: string;
  confirmed_fields?: InspirationOptionsContext;
  direction_card?: InspirationDirectionCard | null;
  story_bible_draft?: InspirationStoryBibleDraft;
  guidance?: InspirationGuidance;
}

export type InspirationQualityDimension =
  | 'novelty'
  | 'writability'
  | 'commercial_hook'
  | 'consistency'
  | 'long_form_potential';

export interface InspirationQualityIssue {
  id: string;
  dimension?: InspirationQualityDimension;
  severity?: 'info' | 'warning' | 'error';
  message: string;
  suggestion?: string;
}

export interface InspirationQualityReport {
  overall_score: number;
  dimensions: Record<InspirationQualityDimension, number>;
  issues: InspirationQualityIssue[];
  repair_suggestions: string[];
  warnings: string[];
}

export interface InspirationRepairResult {
  repaired: boolean;
  draft: InspirationStoryBibleDraft | InspirationDirectionCard;
  remaining_issues: InspirationQualityIssue[];
  warnings: string[];
}

export interface InspirationGenerateCardsRequest {
  idea?: string;
  guidance?: InspirationGuidance;
  context?: InspirationOptionsContext;
  card_count?: number;
}

export interface InspirationGenerateCardsResponse {
  prompt?: string;
  cards: InspirationDirectionCard[];
  warnings: string[];
  error?: string;
}

export type InspirationPlatform = 'qidian' | 'jjwxc' | 'ao3' | 'wattpad';

export interface InspirationBatchRequest {
  base_idea: string;
  platform?: InspirationPlatform;
  channel?: string;
  genre_tags?: string[];
  plot_keywords?: string[];
  character_traits?: string[];
  count?: number;
  extra_requirement?: string;
  previous_cards?: InspirationDirectionCard[];
}

export interface InspirationBatchResponse {
  ideas: InspirationDirectionCard[];
  generation_meta: {
    count: number;
    requested_count: number;
    platform?: InspirationPlatform | null;
    channel?: string | null;
    extra_requirement?: string | null;
    filters: {
      genre_tags: string[];
      plot_keywords: string[];
      character_traits: string[];
    };
    warnings: string[];
  };
}

export interface InspirationMergeCardsRequest {
  cards: [InspirationDirectionCard, InspirationDirectionCard];
  primary_card_id?: string;
  instructions?: string;
}

export interface InspirationMergeCardsResponse {
  card: InspirationDirectionCard;
  warnings: string[];
  error?: string;
}

export interface InspirationGenerateStoryBibleRequest {
  idea?: string;
  direction_card?: InspirationDirectionCard;
  confirmed_fields?: InspirationOptionsContext;
  user_edits?: Partial<InspirationStoryBibleDraft>;
  constraints?: string[];
}

export interface InspirationGenerateStoryBibleResponse {
  story_bible_draft: InspirationStoryBibleDraft;
  warnings: string[];
  error?: string;
}

export interface InspirationEvaluateRequest {
  direction_card?: InspirationDirectionCard;
  story_bible_draft?: InspirationStoryBibleDraft;
  context?: InspirationOptionsContext;
}

export interface InspirationRepairRequest {
  draft: InspirationStoryBibleDraft | InspirationDirectionCard;
  issues?: InspirationQualityIssue[];
  issue_ids?: string[];
  instructions?: string;
}

export const DIRECTION_CARD_LABELS: Record<string, string> = {
  title: '推荐书名', hook: '一句话卖点', genre: '类型标签',
  world_setting: '世界规则', core_conflict: '核心冲突',
  protagonist: '主角原型', golden_finger: '金手指/特殊优势',
  opening_hook: '开篇钩子', selling_points: '预期爽点', risks: '风险提示',
};

export interface WorldBuildingResponse {
  project_id: string;
  time_period: string;
  location: string;
  atmosphere: string;
  rules: string;
}

export interface WorldBuildingDraftResponse {
  project_id?: string;
  result_id?: string;
  time_period?: string;
  location?: string;
  atmosphere?: string;
  rules?: string;
  provider?: string | null;
  model?: string | null;
  reasoning_intensity?: string | null;
  source_type?: string | null;
  created_at?: string | null;
}

export type WorldSettingResultStatus = 'pending' | 'accepted' | 'rejected' | 'superseded';

export interface ProjectWorldSnapshot {
  project_id: string;
  world_time_period?: string | null;
  world_location?: string | null;
  world_atmosphere?: string | null;
  world_rules?: string | null;
}

export interface WorldSettingResult {
  id: string;
  project_id: string;
  run_id?: string | null;
  status: WorldSettingResultStatus;
  world_time_period?: string | null;
  world_location?: string | null;
  world_atmosphere?: string | null;
  world_rules?: string | null;
  prompt?: string | null;
  provider?: string | null;
  model?: string | null;
  reasoning_intensity?: string | null;
  raw_result?: Record<string, unknown> | unknown[] | string | null;
  source_type: string;
  accepted_at?: string | null;
  accepted_by?: string | null;
  supersedes_result_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorldSettingResultListResponse {
  total: number;
  items: WorldSettingResult[];
}

export interface WorldSettingResultOperationResponse {
  changed: boolean;
  reason?: string | null;
  result: WorldSettingResult;
  previous_result?: WorldSettingResult | null;
  active_world: ProjectWorldSnapshot;
}

export interface WorldSettingRejectRequest {
  reason?: string | null;
}

export interface WorldSettingRollbackRequest {
  reason?: string | null;
}

// 大纲类型定义
export interface Outline {
  id: string;
  project_id: string;
  title: string;
  content: string;
  structure?: string;
  order_index: number;
  has_chapters?: boolean;
  created_at: string;
  updated_at: string;
}

export interface OutlineCreate {
  project_id: string;
  title: string;
  content: string;
  structure?: string;
  order_index: number;
}

export interface OutlineUpdate {
  title?: string;
  content?: string;
  structure?: string;  // 支持修改structure字段
  // order_index 只能通过 reorder 接口批量调整
}

// 角色类型定义
export interface Character extends EntityEnrichmentFields, LegacyOrganizationCharacterFields {
  id: string;
  project_id: string;
  name: string;
  age?: string;
  gender?: string;
  role_type?: string;
  personality?: string;
  background?: string;
  appearance?: string;
  relationships?: string;
  organization_members?: string;
  traits?: string;
  avatar_url?: string;
  writing_notes?: string;
  speech_patterns?: string;
  motivations?: string;
  arc_summary?: string;
  card_version?: number;
  // 组织扩展字段（从Organization表关联）
  power_level?: number;
  location?: string;
  motto?: string;
  color?: string;
  // 角色/组织状态
  status?: string;
  status_changed_chapter?: number;
  current_state?: string;
  state_updated_chapter?: number;
  // 职业相关字段
  main_career_id?: string;
  main_career_stage?: number;
  sub_careers?: Array<{
    career_id: string;
    stage: number;
  }>;
  created_at: string;
  updated_at: string;
}

export interface CharacterCreate extends LegacyOrganizationPayloadFields {
  project_id: string;
  name: string;
  age?: string;
  gender?: string;
  role_type?: string;
  personality?: string;
  background?: string;
  appearance?: string;
  relationships?: string;
  organization_members?: string;
  traits?: string;
  avatar_url?: string;
  writing_notes?: string;
  speech_patterns?: string;
  motivations?: string;
  arc_summary?: string;
  card_version?: number;
  power_level?: number;
  location?: string;
  motto?: string;
  color?: string;
  main_career_id?: string;
  main_career_stage?: number;
  sub_careers?: string;
}

export interface CharacterUpdate extends LegacyOrganizationPayloadFields {
  name?: string;
  age?: string;
  gender?: string;
  role_type?: string;
  personality?: string;
  background?: string;
  appearance?: string;
  main_career_id?: string;
  main_career_stage?: number;
  sub_careers?: string;
  organization_members?: string;
  traits?: string;
  writing_notes?: string;
  speech_patterns?: string;
  motivations?: string;
  arc_summary?: string;
  card_version?: number;
  // 组织扩展字段
  power_level?: number;
  location?: string;
  motto?: string;
  color?: string;
}

// ==================== 关系管理 / 来源证据 ====================

export interface RelationshipProvenance {
  id: string;
  source_type: string;
  source_id?: string | null;
  run_id?: string | null;
  candidate_id?: string | null;
  chapter_id?: string | null;
  claim_type?: string | null;
  claim_payload?: Record<string, unknown> | null;
  evidence_text?: string | null;
  source_start?: number | null;
  source_end?: number | null;
  confidence?: number | null;
  status?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

export interface RelationshipHistoryEvent {
  id: string;
  event_type: string;
  event_status: string;
  relationship_name?: string | null;
  source_chapter_id?: string | null;
  source_chapter_order?: number | null;
  valid_from_chapter_id?: string | null;
  valid_from_chapter_order?: number | null;
  valid_to_chapter_id?: string | null;
  valid_to_chapter_order?: number | null;
  story_time_label?: string | null;
  source_start_offset?: number | null;
  source_end_offset?: number | null;
  evidence_text?: string | null;
  confidence?: number | null;
  provenance_id?: string | null;
  supersedes_event_id?: string | null;
  created_at?: string | null;
}

export interface Relationship {
  id: string;
  project_id: string;
  character_from_id: string;
  character_to_id: string;
  relationship_type_id?: number | null;
  relationship_name?: string | null;
  intimacy_level: number;
  status: string;
  description?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  source: string;
  source_chapter_id?: string | null;
  source_chapter_number?: number | null;
  source_chapter_order?: number | null;
  evidence_text?: string | null;
  confidence?: number | null;
  provenance?: RelationshipProvenance[];
  history?: RelationshipHistoryEvent[];
  pending_candidate_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RelationshipCreate {
  project_id: string;
  character_from_id: string;
  character_to_id: string;
  relationship_type_id?: number | null;
  relationship_name?: string | null;
  intimacy_level?: number;
  status?: string;
  description?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface RelationshipUpdate {
  relationship_type_id?: number | null;
  relationship_name?: string | null;
  intimacy_level?: number;
  status?: string;
  description?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface RelationshipType {
  id: number;
  name: string;
  category: string;
  reverse_name?: string | null;
  intimacy_range?: string | null;
  icon?: string | null;
  description?: string | null;
  created_at?: string | null;
}

export interface RelationshipGraphNode {
  id: string;
  name: string;
  type: string;
  role_type?: string | null;
  avatar?: string | null;
}

export interface RelationshipGraphLink {
  id?: string | null;
  source: string;
  target: string;
  relationship: string;
  intimacy: number;
  status: string;
  source_chapter_id?: string | null;
  source_chapter_number?: number | null;
  source_chapter_order?: number | null;
  evidence_text?: string | null;
  confidence?: number | null;
  pending_candidate_count?: number;
}

export interface RelationshipGraphData {
  nodes: RelationshipGraphNode[];
  links: RelationshipGraphLink[];
}

// ==================== 金手指管理 ====================

export type GoldfingerStatus =
  | 'latent'
  | 'active'
  | 'sealed'
  | 'cooldown'
  | 'upgrading'
  | 'lost'
  | 'completed'
  | 'unknown';

export interface Goldfinger {
  id: string;
  project_id: string;
  name: string;
  normalized_name: string;
  owner_character_id?: string | null;
  owner_character_name?: string | null;
  type?: string | null;
  status: GoldfingerStatus;
  summary?: string | null;
  rules?: unknown;
  tasks?: unknown;
  rewards?: unknown;
  limits?: unknown;
  trigger_conditions?: unknown;
  cooldown?: unknown;
  aliases?: unknown;
  metadata?: Record<string, unknown> | null;
  confidence?: number | null;
  last_source_chapter_id?: string | null;
  created_by?: string | null;
  updated_by?: string | null;
  source: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GoldfingerCreate {
  name: string;
  owner_character_id?: string | null;
  owner_character_name?: string | null;
  type?: string | null;
  status?: GoldfingerStatus;
  summary?: string | null;
  rules?: unknown;
  tasks?: unknown;
  rewards?: unknown;
  limits?: unknown;
  trigger_conditions?: unknown;
  cooldown?: unknown;
  aliases?: unknown;
  metadata?: Record<string, unknown> | null;
  confidence?: number | null;
  last_source_chapter_id?: string | null;
}

export type GoldfingerUpdate = Partial<GoldfingerCreate>;

export interface GoldfingerListResponse {
  total: number;
  items: Goldfinger[];
}

export interface GoldfingerHistoryEvent {
  id: string;
  goldfinger_id: string;
  project_id: string;
  chapter_id?: string | null;
  event_type: string;
  old_value?: unknown;
  new_value?: unknown;
  evidence_excerpt?: string | null;
  confidence?: number | null;
  source_type?: string | null;
  created_at?: string | null;
}

export interface GoldfingerHistoryListResponse {
  total: number;
  items: GoldfingerHistoryEvent[];
}

export interface GoldfingerImportItem {
  id?: string | null;
  name?: string | null;
  owner_character_id?: string | null;
  owner_character_name?: string | null;
  type?: string | null;
  status?: GoldfingerStatus | string | null;
  summary?: string | null;
  rules?: unknown;
  tasks?: unknown;
  rewards?: unknown;
  limits?: unknown;
  trigger_conditions?: unknown;
  cooldown?: unknown;
  aliases?: unknown;
  metadata?: Record<string, unknown> | null;
  confidence?: number | null;
  last_source_chapter_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface GoldfingerImportPayload {
  version: string;
  export_time?: string | null;
  export_type?: string | null;
  project_id?: string | null;
  count?: number | null;
  data: GoldfingerImportItem[];
  [key: string]: unknown;
}

export interface GoldfingerImportConflict {
  index: number;
  name?: string | null;
  normalized_name?: string | null;
  existing_id?: string | null;
  reason: string;
}

export interface GoldfingerImportProblem {
  index?: number | null;
  name?: string | null;
  message: string;
}

export interface GoldfingerImportDryRunResult {
  valid: boolean;
  version: string;
  expected_version: 'goldfinger-card.v1';
  total: number;
  creatable: number;
  conflicts: GoldfingerImportConflict[];
  errors: GoldfingerImportProblem[];
  warnings: GoldfingerImportProblem[];
  would_create: Array<Record<string, unknown>>;
  statistics: Record<string, number>;
}

export interface GoldfingerImportResult {
  success: boolean;
  message: string;
  imported: number;
  imported_ids: string[];
  dry_run: GoldfingerImportDryRunResult;
  warnings: GoldfingerImportProblem[];
}

export interface GoldfingerExportPayload extends GoldfingerImportPayload {
  version: 'goldfinger-card.v1';
  export_time: string;
  export_type: 'goldfingers';
  project_id: string;
  count: number;
  data: GoldfingerImportItem[];
}

// ==================== 抽取候选评审 / 实体兼容元数据 ====================

export type ExtractionRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type ExtractionCandidateStatus = 'pending' | 'accepted' | 'rejected' | 'merged' | 'superseded';
export type ExtractionCandidateType =
  | 'character'
  | 'organization'
  | 'profession'
  | 'relationship'
  | 'goldfinger'
  | 'organization_affiliation'
  | 'profession_assignment'
  | 'world_fact'
  | 'character_state';
export type CanonicalTargetType = 'character' | 'organization' | 'career' | 'goldfinger' | 'relationship';

export interface SyncRun {
  id: string;
  project_id: string;
  chapter_id?: string | null;
  trigger_source: string;
  pipeline_version: string;
  schema_version: string;
  prompt_hash?: string | null;
  content_hash: string;
  status: ExtractionRunStatus | string;
  raw_response?: Record<string, unknown> | unknown[] | string | null;
  run_metadata?: Record<string, unknown> | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SyncRunListResponse {
  total: number;
  items: SyncRun[];
}

export interface EntityAlias {
  id: string;
  alias: string;
  normalized_alias?: string;
  source?: string;
  status?: string;
  provenance_id?: string;
}

export interface EntityProvenance {
  id: string;
  source_type: string;
  source_id?: string | null;
  run_id?: string | null;
  candidate_id?: string | null;
  chapter_id?: string | null;
  claim_type?: string | null;
  claim_payload?: Record<string, unknown> | null;
  evidence_text?: string | null;
  confidence?: number | null;
  status?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

export interface EntityTimelinePreview {
  id: string;
  event_type: string;
  event_status: string;
  relationship_name?: string | null;
  position?: string | null;
  career_id?: string | null;
  career_stage?: number | null;
  valid_from_chapter_id?: string | null;
  valid_from_chapter_order?: number | null;
  valid_to_chapter_id?: string | null;
  valid_to_chapter_order?: number | null;
  confidence?: number | null;
}

export interface EntityTimelineSummary {
  total_events: number;
  active_events: number;
  event_type_counts: Record<string, number>;
  latest_events: EntityTimelinePreview[];
}

export interface EntityGenerationPolicyStatus {
  policy_gate: 'entity_generation';
  allowed: boolean;
  mode: 'canonical_allowed' | 'candidate_only' | 'manual_allowed';
  code: string;
  message: string;
  audit_required: boolean;
  override_source: 'admin' | 'advanced_setting' | 'manual' | 'none';
  entity_type: string;
  action_type: string;
  source_endpoint: string;
  project_id: string;
  actor_user_id?: string | null;
  provider?: string | null;
  model?: string | null;
  reason?: string | null;
}

export interface EntityEnrichmentFields {
  aliases?: EntityAlias[];
  provenance?: EntityProvenance[];
  candidate_counts?: Record<ExtractionCandidateStatus | string, number>;
  candidate_count?: number;
  timeline_summary?: EntityTimelineSummary;
  policy_status?: EntityGenerationPolicyStatus;
}

export interface EntityEnrichmentQuery {
  include_provenance?: boolean;
  include_aliases?: boolean;
  include_candidate_counts?: boolean;
  include_timeline?: boolean;
  include_policy_status?: boolean;
}

export interface ExtractionRun {
  id: string;
  project_id: string;
  chapter_id?: string | null;
  trigger_source: string;
  pipeline_version: string;
  schema_version: string;
  prompt_hash?: string | null;
  content_hash: string;
  status: ExtractionRunStatus;
  provider?: string | null;
  model?: string | null;
  reasoning_intensity?: string | null;
  raw_response?: unknown;
  run_metadata?: Record<string, unknown> | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ExtractionRunListResponse {
  total: number;
  items: ExtractionRun[];
}

export interface ExtractionCandidate {
  id: string;
  run_id: string;
  project_id: string;
  user_id: string;
  source_chapter_id?: string | null;
  source_chapter_start_id?: string | null;
  source_chapter_end_id?: string | null;
  candidate_type: ExtractionCandidateType;
  trigger_type: string;
  source_hash: string;
  provider?: string | null;
  model?: string | null;
  reasoning_intensity?: string | null;
  display_name?: string | null;
  normalized_name?: string | null;
  canonical_target_type?: CanonicalTargetType | null;
  canonical_target_id?: string | null;
  status: ExtractionCandidateStatus;
  confidence: number;
  evidence_text: string;
  source_start_offset: number;
  source_end_offset: number;
  source_chapter_number?: number | null;
  source_chapter_order?: number | null;
  valid_from_chapter_id?: string | null;
  valid_from_chapter_order?: number | null;
  valid_to_chapter_id?: string | null;
  valid_to_chapter_order?: number | null;
  story_time_label?: string | null;
  payload: Record<string, unknown>;
  raw_payload?: unknown;
  merge_target_type?: string | null;
  merge_target_id?: string | null;
  reviewer_user_id?: string | null;
  reviewed_at?: string | null;
  accepted_at?: string | null;
  review_required_reason?: string | null;
  rejection_reason?: string | null;
  supersedes_candidate_id?: string | null;
  rollback_of_candidate_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type SyncCandidate = ExtractionCandidate;

export interface SyncCandidateListResponse {
  total: number;
  items: SyncCandidate[];
}

export interface SyncCandidateApproveRequest {
  target_type?: string | null;
  target_id?: string | null;
  override?: boolean;
  supersedes_candidate_id?: string | null;
}

export interface SyncCandidateRejectRequest {
  reason?: string | null;
}

export interface SyncCandidateReviewResponse {
  changed: boolean;
  reason?: string | null;
  candidate: SyncCandidate;
}

export interface ExtractionCandidateListResponse {
  total: number;
  items: ExtractionCandidate[];
}

export interface ExtractionCandidateListParams {
  project_id?: string;
  status?: ExtractionCandidateStatus;
  type?: ExtractionCandidateType;
  chapter_id?: string;
  run_id?: string;
  canonical_target?: string;
  limit?: number;
  offset?: number;
}

export interface CandidateAcceptRequest {
  target_type?: CanonicalTargetType | null;
  target_id?: string | null;
  override?: boolean;
  supersedes_candidate_id?: string | null;
}

export interface CandidateMergeRequest {
  target_type: CanonicalTargetType;
  target_id: string;
  override?: boolean;
}

export interface CandidateRejectRequest {
  reason?: string | null;
}

export interface CandidateRollbackRequest {
  reason?: string | null;
}

export interface CandidateReviewResponse {
  changed: boolean;
  reason?: string | null;
  candidate: ExtractionCandidate;
}

export interface CandidateBatchReviewResponse {
  changed: number;
  failures: Array<{ candidate_id: string; reason: string }>;
  candidates: ExtractionCandidate[];
}

export interface ManualReextractResponse {
  project_id: string;
  scope: 'project' | 'chapter' | 'range';
  total_runs: number;
  runs: ExtractionRun[];
}

export interface CareerStage {
  level: number;
  name: string;
  description?: string;
}

export interface Career extends EntityEnrichmentFields {
  id: string;
  project_id: string;
  name: string;
  type: 'main' | 'sub';
  description?: string;
  category?: string;
  stages: CareerStage[];
  max_stage: number;
  requirements?: string;
  special_abilities?: string;
  worldview_rules?: string;
  attribute_bonuses?: Record<string, unknown> | null;
  source: string;
  created_at?: string;
  updated_at?: string;
}

export interface CareerListResponse {
  total?: number;
  main_careers?: Career[];
  sub_careers?: Career[];
}

export interface CharacterCareerDetail {
  id: string;
  character_id: string;
  career_id: string;
  career_name: string;
  career_type: 'main' | 'sub';
  current_stage: number;
  stage_name: string;
  stage_description?: string;
  stage_progress: number;
  max_stage: number;
  started_at?: string;
  reached_current_stage_at?: string;
  notes?: string;
}

export interface CharacterCareerResponse {
  main_career?: CharacterCareerDetail | null;
  sub_careers?: CharacterCareerDetail[];
}

export interface CharacterCareerAssignmentRequest {
  career_id: string;
  current_stage?: number;
  started_at?: string;
}

export interface CharacterCareerStageUpdateRequest {
  current_stage: number;
  stage_progress: number;
  reached_current_stage_at?: string;
  notes?: string;
}

export interface CareerCreateRequest {
  project_id: string;
  name: string;
  type: 'main' | 'sub';
  description?: string;
  category?: string;
  stages: CareerStage[];
  max_stage: number;
  requirements?: string;
  special_abilities?: string;
  worldview_rules?: string;
  attribute_bonuses?: Record<string, unknown> | null;
  source?: string;
}

export type CareerUpdateRequest = Partial<Omit<CareerCreateRequest, 'project_id'>>;

export interface Organization extends EntityEnrichmentFields {
  id: string;
  character_id: string;
  organization_entity_id?: string;
  name: string;
  type: string;
  purpose: string;
  member_count: number;
  power_level: number;
  location?: string;
  motto?: string;
  color?: string;
}

export interface OrganizationMember {
  id: string;
  character_id: string;
  character_name: string;
  position: string;
  rank: number;
  loyalty: number;
  contribution: number;
  status: string;
  joined_at?: string;
  left_at?: string;
  notes?: string;
}

export interface OrganizationMemberPayload {
  character_id?: string;
  position?: string;
  rank?: number;
  loyalty?: number;
  contribution?: number;
  status?: string;
  joined_at?: string;
  left_at?: string;
  notes?: string;
}

export interface OrganizationUpdateRequest {
  power_level?: number;
  location?: string;
  motto?: string;
  color?: string;
}

export type TimelineEventType = 'relationship' | 'affiliation' | 'profession' | 'status';
export type TimelineEventStatus = 'active' | 'ended' | 'superseded' | 'rolled_back';

export interface TimelineQueryPoint {
  chapter_id?: string | null;
  chapter_number: number;
  chapter_order: number;
}

export interface TimelineStateQuery {
  chapter_id?: string;
  chapter_number?: number;
  chapter_order?: number;
}

export interface TimelineHistoryQuery {
  event_type?: TimelineEventType;
}

export interface TimelineEvent {
  id: string;
  project_id: string;
  relationship_id?: string | null;
  organization_member_id?: string | null;
  character_id?: string | null;
  related_character_id?: string | null;
  organization_entity_id?: string | null;
  career_id?: string | null;
  event_type: TimelineEventType;
  event_status: TimelineEventStatus;
  relationship_name?: string | null;
  position?: string | null;
  rank?: number | null;
  career_stage?: number | null;
  story_time_label?: string | null;
  source_chapter_id?: string | null;
  source_chapter_order?: number | null;
  valid_from_chapter_id?: string | null;
  valid_from_chapter_order?: number | null;
  valid_to_chapter_id?: string | null;
  valid_to_chapter_order?: number | null;
  source_start_offset?: number | null;
  source_end_offset?: number | null;
  evidence_text?: string | null;
  confidence?: number | null;
  provenance_id?: string | null;
  supersedes_event_id?: string | null;
  created_at?: string | null;
}

export interface TimelineStateResponse {
  project_id: string;
  point: TimelineQueryPoint;
  relationships: TimelineEvent[];
  affiliations: TimelineEvent[];
  professions: TimelineEvent[];
}

export interface TimelineHistoryResponse {
  project_id: string;
  event_type?: TimelineEventType | null;
  total: number;
  items: TimelineEvent[];
}

// 展开规划数据结构
export interface ExpansionPlanData {
  key_events: string[];
  character_focus: string[];
  emotional_tone: string;
  narrative_goal: string;
  conflict_type: string;
  estimated_words: number;
  scenes?: Array<{
    location: string;
    characters: string[];
    purpose: string;
  }> | null;
}

// 章节类型定义
export interface Chapter {
  id: string;
  project_id: string;
  title: string;
  content?: string;
  summary?: string;
  chapter_number: number;
  word_count: number;
  status: 'draft' | 'writing' | 'completed';
  expansion_plan?: string; // JSON字符串，解析后为ExpansionPlanData
  outline_id?: string; // 关联的大纲ID
  sub_index?: number; // 大纲下的子章节序号
  outline_title?: string; // 大纲标题（从后端联表查询获得）
  outline_order?: number; // 大纲排序序号（从后端联表查询获得）
  created_at: string;
  updated_at: string;
}

export interface ChapterCreate {
  project_id: string;
  title: string;
  chapter_number: number;
  content?: string;
  summary?: string;
  status?: 'draft' | 'writing' | 'completed';
}

export interface ChapterUpdate {
  title?: string;
  content?: string;
  // chapter_number 不允许修改，由大纲顺序决定
  summary?: string;
  // word_count 自动计算，不允许手动修改
  status?: 'draft' | 'writing' | 'completed';
}

// 章节生成请求类型
export interface ChapterGenerateRequest {
  style_id?: number;
  target_word_count?: number;
}

// 章节生成检查响应
export interface ChapterCanGenerateResponse {
  can_generate: boolean;
  reason: string;
  previous_chapters: {
    id: string;
    chapter_number: number;
    title: string;
    has_content: boolean;
    word_count: number;
  }[];
  chapter_number: number;
}

// AI生成请求类型
export interface GenerateOutlineRequest {
  project_id: string;
  genre?: string;
  theme: string;
  chapter_count: number;
  narrative_perspective: string;
  world_context?: Record<string, unknown>;
  characters_context?: Character[];
  target_words?: number;
  requirements?: string;
  provider?: string;
  model?: string;
  // 续写功能新增字段
  mode?: 'auto' | 'new' | 'continue';
  story_direction?: string;
  plot_stage?: 'development' | 'climax' | 'ending';
  keep_existing?: boolean;
}

// 大纲重排序请求类型
export interface OutlineReorderItem {
  id: string;
  order_index: number;
}

export interface OutlineReorderRequest {
  orders: OutlineReorderItem[];
}

// 大纲展开相关类型定义
export interface ChapterPlanItem {
  sub_index: number;
  title: string;
  plot_summary: string;
  key_events: string[];
  character_focus: string[];
  emotional_tone: string;
  narrative_goal: string;
  conflict_type: string;
  estimated_words: number;
  scenes?: Array<{
    location: string;
    characters: string[];
    purpose: string;
  }>;
}

export interface OutlineExpansionRequest {
  target_chapter_count: number;
  expansion_strategy?: 'balanced' | 'climax' | 'detail';
  auto_create_chapters?: boolean;
  provider?: string;
  model?: string;
}

export interface OutlineExpansionResponse {
  outline_id: string;
  outline_title: string;
  target_chapter_count: number;
  actual_chapter_count: number;
  expansion_strategy: string;
  chapter_plans: ChapterPlanItem[];
  created_chapters?: Array<{
    id: string;
    chapter_number: number;
    title: string;
    summary: string;
    outline_id: string;
    sub_index: number;
    status: string;
  }> | null;
}

export interface BatchOutlineExpansionRequest {
  project_id: string;
  outline_ids?: string[];
  chapters_per_outline: number;
  expansion_strategy?: 'balanced' | 'climax' | 'detail';
  auto_create_chapters?: boolean;
  provider?: string;
  model?: string;
}

export interface BatchOutlineExpansionResponse {
  project_id: string;
  total_outlines_expanded: number;
  total_chapters_created: number;
  expansion_results: OutlineExpansionResponse[];
  skipped_outlines?: Array<{
    outline_id: string;
    outline_title: string;
    reason: string;
  }>;
}

export interface GenerateCharacterRequest {
  project_id: string;
  name?: string;
  role_type?: string;
  background?: string;
  requirements?: string;
  provider?: string;
  model?: string;
}

export interface PolishTextRequest {
  text: string;
  style?: string;
}

// 向导API响应类型
export interface GenerateCharactersResponse {
  characters: Character[];
}

export interface GenerateOutlineResponse {
  outlines: Outline[];
}

// API响应类型
export interface ApiResponse<T> {
  data: T;
  message?: string;
}

// 写作风格类型定义
export interface WritingStyle {
  id: number;
  user_id: string | null;  // NULL 表示全局预设风格
  name: string;
  style_type: 'preset' | 'custom';
  preset_id?: string;
  description?: string;
  prompt_content: string;
  is_default: boolean;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export interface WritingStyleCreate {
  name: string;
  style_type?: 'preset' | 'custom';
  preset_id?: string;
  description?: string;
  prompt_content: string;
}

export interface WritingStyleUpdate {
  name?: string;
  description?: string;
  prompt_content?: string;
  order_index?: number;
}

export interface PresetStyle {
  id: string;
  name: string;
  description: string;
  prompt_content: string;
}

export interface WritingStyleListResponse {
  styles: WritingStyle[];
  total: number;
}

export interface PaginationResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// 向导表单数据类型
export interface WizardBasicInfo {
  title: string;
  description: string;
  theme: string;
  genre: string | string[];
  chapter_count: number;
  narrative_perspective: string;
  character_count?: number;
  target_words?: number;
  outline_mode?: 'one-to-one' | 'one-to-many';  // 大纲章节模式
}

// API 错误响应类型
export interface ApiError {
  response?: {
    data?: {
      detail?: string;
    };
  };
  message?: string;
}

// 章节分析任务相关类型
export interface AnalysisTask {
  has_task: boolean;
  task_id: string | null;
  chapter_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'none';
  progress: number;
  error_message?: string | null;
  auto_recovered?: boolean;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface BatchAnalysisStatusResponse {
  project_id: string;
  total: number;
  items: Record<string, AnalysisTask>;
}

export interface BatchAnalyzeUnanalyzedRequest {
  chapter_ids?: string[];
}

export interface BatchAnalyzeUnanalyzedResponse {
  project_id: string;
  total_candidates: number;
  total_started: number;
  total_skipped_no_content: number;
  total_skipped_running: number;
  total_already_completed: number;
  started_tasks: Record<string, AnalysisTask>;
}

// 分析结果 - 钩子
export interface AnalysisHook {
  type: string;
  content: string;
  strength: number;
  position: string;
}

// 分析结果 - 伏笔
export interface AnalysisForeshadow {
  content: string;
  type: 'planted' | 'resolved';
  strength: number;
  subtlety: number;
  reference_chapter?: number;
}

// 分析结果 - 冲突
export interface AnalysisConflict {
  types: string[];
  parties: string[];
  level: number;
  description: string;
  resolution_progress: number;
}

// 分析结果 - 情感曲线
export interface AnalysisEmotionalArc {
  primary_emotion: string;
  intensity: number;
  curve: string;
  secondary_emotions: string[];
}

// 分析结果 - 角色状态
export interface AnalysisCharacterState {
  character_name: string;
  state_before: string;
  state_after: string;
  psychological_change: string;
  key_event: string;
  relationship_changes: Record<string, string>;
}

// 分析结果 - 情节点
export interface AnalysisPlotPoint {
  content: string;
  type: 'revelation' | 'conflict' | 'resolution' | 'transition';
  importance: number;
  impact: string;
}

// 分析结果 - 场景
export interface AnalysisScene {
  location: string;
  atmosphere: string;
  duration: string;
}

// 分析结果 - 评分
export interface AnalysisScores {
  pacing: number;
  engagement: number;
  coherence: number;
  overall: number;
}

// 完整分析数据 - 匹配后端PlotAnalysis模型
export interface AnalysisData {
  id: string;
  chapter_id: string;
  plot_stage: string;
  conflict_level: number;
  conflict_types: string[];
  emotional_tone: string;
  emotional_intensity: number;
  hooks: AnalysisHook[];
  hooks_count: number;
  foreshadows: AnalysisForeshadow[];
  foreshadows_planted: number;
  foreshadows_resolved: number;
  plot_points: AnalysisPlotPoint[];
  plot_points_count: number;
  character_states: AnalysisCharacterState[];
  scenes?: AnalysisScene[];
  pacing: string;
  overall_quality_score: number;
  pacing_score: number;
  engagement_score: number;
  coherence_score: number;
  analysis_report: string;
  suggestions: string[];
  dialogue_ratio: number;
  description_ratio: number;
  created_at: string;
}

// 记忆片段
export interface StoryMemory {
  id: string;
  type: 'hook' | 'foreshadow' | 'plot_point' | 'character_event';
  title: string;
  content: string;
  importance: number;
  tags: string[];
  is_foreshadow: 0 | 1 | 2; // 0=普通, 1=已埋下, 2=已回收
}

export interface EntityChangesSummaryItem {
  updated_count?: number;
  state_updated_count?: number;
  relationship_created_count?: number;
  relationship_updated_count?: number;
  org_updated_count?: number;
  changes: string[];
}

// 章节分析结果响应 - 匹配后端API返回
export interface ChapterAnalysisResponse {
  chapter_id: string;
  analysis: AnalysisData;  // 注意：后端返回的是analysis而不是analysis_data
  memories: StoryMemory[];
  created_at: string;
  entity_changes?: {
    careers: EntityChangesSummaryItem;
    character_states: EntityChangesSummaryItem;
    organization_states: EntityChangesSummaryItem;
  };
}

// 手动触发分析响应
export interface TriggerAnalysisResponse {
  task_id: string;
  chapter_id: string;
  status: string;
  message: string;
}

// MCP 插件类型定义 - 优化后只包含必要字段
export interface MCPPlugin {
  id: string;
  plugin_name: string;
  display_name: string;
  description?: string;
  plugin_type: 'http' | 'stdio' | 'streamable_http' | 'sse';
  category: string;

  // HTTP类型字段
  server_url?: string;
  headers?: Record<string, string>;

  // Stdio类型字段
  command?: string;
  args?: string[];
  env?: Record<string, string>;

  // 状态字段
  enabled: boolean;
  status: 'active' | 'inactive' | 'error';
  last_error?: string;
  last_test_at?: string;

  // 时间戳
  created_at: string;
}

export interface MCPPluginCreate {
  plugin_name: string;
  display_name?: string;
  description?: string;
  server_type: 'http' | 'stdio' | 'streamable_http' | 'sse';
  server_url?: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  headers?: Record<string, string>;
  enabled?: boolean;
}

export interface MCPPluginUpdate {
  display_name?: string;
  description?: string;
  server_url?: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  headers?: Record<string, string>;
  enabled?: boolean;
}

export interface MCPTool {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

export interface MCPTestResult {
  success: boolean;
  message: string;
  tools?: MCPTool[];
  tools_count?: number;
  response_time_ms?: number;
  error?: string;
  error_type?: string;
  suggestions?: string[];
}

export interface MCPToolCallRequest {
  plugin_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface MCPToolCallResponse {
  success: boolean;
  result?: unknown;
  error?: string;
}

// 伏笔管理类型定义
export type ForeshadowStatus = 'pending' | 'planted' | 'resolved' | 'partially_resolved' | 'abandoned';
export type ForeshadowSourceType = 'analysis' | 'manual';
export type ForeshadowCategory = 'identity' | 'mystery' | 'item' | 'relationship' | 'event' | 'ability' | 'prophecy';

export interface Foreshadow {
  id: string;
  project_id: string;
  title: string;
  content: string;
  hint_text?: string;
  resolution_text?: string;
  source_type?: ForeshadowSourceType;
  source_memory_id?: string;
  source_analysis_id?: string;
  plant_chapter_id?: string;
  plant_chapter_number?: number;
  target_resolve_chapter_id?: string;
  target_resolve_chapter_number?: number;
  actual_resolve_chapter_id?: string;
  actual_resolve_chapter_number?: number;
  status: ForeshadowStatus;
  is_long_term: boolean;
  importance: number;
  strength: number;
  subtlety: number;
  urgency: number;
  related_characters?: string[];
  related_foreshadow_ids?: string[];
  tags?: string[];
  category?: ForeshadowCategory;
  notes?: string;
  resolution_notes?: string;
  auto_remind: boolean;
  remind_before_chapters: number;
  include_in_context: boolean;
  created_at?: string;
  updated_at?: string;
  planted_at?: string;
  resolved_at?: string;
}

export interface ForeshadowCreate {
  project_id: string;
  title: string;
  content: string;
  hint_text?: string;
  resolution_text?: string;
  plant_chapter_number?: number;
  target_resolve_chapter_number?: number;
  is_long_term?: boolean;
  importance?: number;
  strength?: number;
  subtlety?: number;
  related_characters?: string[];
  tags?: string[];
  category?: ForeshadowCategory;
  notes?: string;
  resolution_notes?: string;
  auto_remind?: boolean;
  remind_before_chapters?: number;
  include_in_context?: boolean;
}

export interface ForeshadowUpdate {
  title?: string;
  content?: string;
  hint_text?: string;
  resolution_text?: string;
  plant_chapter_number?: number;
  target_resolve_chapter_number?: number;
  status?: ForeshadowStatus;
  is_long_term?: boolean;
  importance?: number;
  strength?: number;
  subtlety?: number;
  urgency?: number;
  related_characters?: string[];
  related_foreshadow_ids?: string[];
  tags?: string[];
  category?: ForeshadowCategory;
  notes?: string;
  resolution_notes?: string;
  auto_remind?: boolean;
  remind_before_chapters?: number;
  include_in_context?: boolean;
}

export interface ForeshadowStats {
  total: number;
  pending: number;
  planted: number;
  resolved: number;
  partially_resolved: number;
  abandoned: number;
  long_term_count: number;
  overdue_count: number;
}

export interface ForeshadowListResponse {
  total: number;
  items: Foreshadow[];
  stats?: ForeshadowStats;
}

export interface PlantForeshadowRequest {
  chapter_id: string;
  chapter_number: number;
  hint_text?: string;
}

export interface ResolveForeshadowRequest {
  chapter_id: string;
  chapter_number: number;
  resolution_text?: string;
  is_partial?: boolean;
}

export interface SyncFromAnalysisRequest {
  chapter_ids?: string[];
  overwrite_existing?: boolean;
  auto_set_planted?: boolean;
}

export interface SyncFromAnalysisResponse {
  synced_count: number;
  skipped_count: number;
  new_foreshadows: Foreshadow[];
  skipped_reasons: Array<{ source_memory_id: string; reason: string }>;
}

export interface ForeshadowContextResponse {
  chapter_number: number;
  context_text: string;
  pending_plant: Foreshadow[];
  pending_resolve: Foreshadow[];
  overdue: Foreshadow[];
  recently_planted: Foreshadow[];
}

// ==================== 拆书导入类型定义 ====================

export type BookImportTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type BookImportWarningLevel = 'info' | 'warning' | 'error';
export type BookImportExtractMode = 'tail' | 'full';

export interface BookImportWarning {
  code: string;
  message: string;
  level: BookImportWarningLevel;
}

export interface BookImportProjectSuggestion {
  title: string;
  description?: string;
  theme?: string;
  genre?: string;
  narrative_perspective: string;
  target_words: number;
}

export interface BookImportChapter {
  title: string;
  content: string;
  summary?: string;
  chapter_number: number;
  outline_title?: string;
}

export interface BookImportOutline {
  title: string;
  content?: string;
  order_index: number;
  structure?: Record<string, unknown>;
}

export interface BookImportTask {
  task_id: string;
  status: BookImportTaskStatus;
  progress: number;
  message?: string;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface BookImportPreview {
  task_id: string;
  project_suggestion: BookImportProjectSuggestion;
  chapters: BookImportChapter[];
  outlines: BookImportOutline[];
  warnings: BookImportWarning[];
}

export interface BookImportApplyPayload {
  project_suggestion: BookImportProjectSuggestion;
  chapters: BookImportChapter[];
  outlines: BookImportOutline[];
  import_mode?: 'append' | 'overwrite';
}

export interface BookImportCreateTaskPayload {
  file: File;
  extract_mode?: BookImportExtractMode;
  tail_chapter_count?: number;
}

export interface BookImportResult {
  success: boolean;
  project_id: string;
  statistics: {
    chapters: number;
    outlines: number;
    generated_careers?: number;
    generated_entities?: number;
    generated_world_building?: number;
  };
  warnings: BookImportWarning[];
}

export interface BookImportStepFailure {
  step_name: string;       // world_building / career_system / characters
  step_label: string;      // 中文名
  error: string;           // 错误详情
  retry_count?: number;    // 已重试次数
}

export interface BookImportRetryResult {
  success: boolean;
  project_id: string;
  retry_results: Record<string, number>;
  still_failed: BookImportStepFailure[];
}

// ==================== 提示词工坊类型定义 ====================

export interface PromptWorkshopItem {
  id: string;
  name: string;
  description?: string;
  prompt_content: string;
  category: string;
  tags?: string[];
  author_name?: string;
  is_official: boolean;
  download_count: number;
  like_count: number;
  is_liked?: boolean;
  created_at?: string;
}

export interface PromptSubmission {
  id: string;
  name: string;
  description?: string;
  prompt_content?: string;
  category: string;
  tags?: string[];
  author_display_name?: string;
  is_anonymous: boolean;
  status: 'pending' | 'approved' | 'rejected';
  review_note?: string;
  reviewed_at?: string;
  created_at?: string;
  source_instance?: string;
  submitter_name?: string;
}

export interface PromptSubmissionCreate {
  name: string;
  description?: string;
  prompt_content: string;
  category: string;
  tags?: string[];
  author_display_name?: string;
  is_anonymous?: boolean;
  source_style_id?: number;
}

export interface PromptWorkshopCategory {
  id: string;
  name: string;
  count: number;
}

export interface PromptWorkshopListResponse {
  success: boolean;
  data: {
    total: number;
    page: number;
    limit: number;
    items: PromptWorkshopItem[];
    categories: PromptWorkshopCategory[];
  };
}

export interface PromptWorkshopStatusResponse {
  mode: 'client' | 'server';
  instance_id: string;
  cloud_url?: string;
  cloud_connected?: boolean;
}

export interface PromptAssemblyLayerRequest {
  id: string;
  source_type: string;
  content: string;
  label?: string;
  order?: number | null;
  enabled?: boolean;
  metadata?: Record<string, unknown>;
}

export interface PromptAssemblyTraceRequest {
  trace_version?: number;
  layers: PromptAssemblyLayerRequest[];
  separator?: string;
}

export interface PromptAssemblyTraceLayer {
  order: number;
  id: string;
  label: string;
  source_type: string;
  enabled: boolean;
  content_hash: string;
  content_length: number;
  metadata: Record<string, unknown>;
}

export interface PromptAssemblyTrace {
  trace_version: number;
  schema_version: string;
  trace_id: string;
  preset_boundary: string;
  boundary_decision: string;
  validation: {
    valid: boolean;
    errors: Array<Record<string, unknown>>;
    expected_trace_version: number;
    allowed_source_types: string[];
  };
  layer_order: string[];
  layers: PromptAssemblyTraceLayer[];
  final_prompt: string;
  final_prompt_hash: string;
}

export interface PromptAssemblyTraceResponse {
  success: boolean;
  boundary: {
    mode: string;
    owner: string;
    duplicates_prompt_stack: boolean;
    persistence: string;
    reason: string;
  };
  trace: PromptAssemblyTrace;
}

export interface LorebookPromptPreviewRequest {
  activation_text: string;
  max_chars?: number | null;
  max_tokens?: number | null;
  chars_per_token?: number;
}

export interface LorebookPromptTraceItem {
  order: number;
  id: string;
  title: string;
  source_type: string;
  entry_source_type: string;
  priority: number;
  matched_keys: string[];
  content: string;
  original_content_length: number;
  selected_content_length: number;
  trimmed: boolean;
}

export interface LorebookPromptTrace {
  source_type: string;
  selected_lore_ids: string[];
  total_candidates: number;
  selected_count: number;
  budget_estimate: {
    chars_used: number;
    budget_chars?: number | null;
    estimated_tokens: number;
    chars_per_token: number;
  };
  items: LorebookPromptTraceItem[];
  final_preview_text: string;
}

export interface LorebookPromptPreviewResponse {
  project_id: string;
  trace: LorebookPromptTrace;
}

export interface DataBankRetrievalRequest {
  query: string;
  limit?: number;
}

export interface DataBankRetrievalResult {
  order: number;
  source_type: string;
  item_source_type: string;
  item_id: string;
  chunk_id: string;
  title: string;
  filename?: string | null;
  chunk_index: number;
  score: number;
  matched_terms: string[];
  content: string;
  char_start: number;
  char_end: number;
  content_hash: string;
}

export interface DataBankRetrievalTraceResponse {
  project_id: string;
  query: string;
  strategy: string;
  total_candidates: number;
  returned_count: number;
  results: DataBankRetrievalResult[];
}

export interface PromptWorkshopAdminStats {
  total_items: number;
  total_official: number;
  total_pending: number;
  total_downloads: number;
  total_likes: number;
}

// ==================== 公告类型定义 ====================

export type AnnouncementLevel = 'info' | 'success' | 'warning' | 'error';
export type AnnouncementStatus = 'draft' | 'published' | 'hidden';

export interface Announcement {
  id: string;
  title: string;
  content: string;
  summary?: string | null;
  level: AnnouncementLevel;
  status?: AnnouncementStatus;
  pinned: boolean;
  author_id?: string | null;
  author_name?: string | null;
  publish_at?: string | null;
  expire_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AnnouncementCreate {
  title: string;
  content: string;
  summary?: string;
  level?: AnnouncementLevel;
  status?: AnnouncementStatus;
  pinned?: boolean;
  publish_at?: string;
  expire_at?: string;
}

export interface AnnouncementUpdate {
  title?: string;
  content?: string;
  summary?: string;
  level?: AnnouncementLevel;
  status?: AnnouncementStatus;
  pinned?: boolean;
  publish_at?: string | null;
  expire_at?: string | null;
}

export interface AnnouncementListResponse {
  success: boolean;
  data: {
    total: number;
    page: number;
    limit: number;
    items: Announcement[];
    active_ids?: string[];
    latest_updated_at?: string | null;
    server_time?: string;
  };
}

export interface AnnouncementStatusResponse {
  mode: 'client' | 'server' | string;
  instance_id: string;
  cloud_url?: string;
  cloud_connected?: boolean;
}

// 提示词工坊分类常量
export const PROMPT_CATEGORIES: Record<string, string> = {
  general: '通用',
  fantasy: '玄幻/仙侠',
  martial: '武侠',
  romance: '言情',
  scifi: '科幻',
  horror: '悬疑/惊悚',
  history: '历史',
  urban: '都市',
  game: '游戏/电竞',
  other: '其他',
};
