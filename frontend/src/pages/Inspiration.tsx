import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Card, Input, Button, Space, Typography, message, Spin, Modal, theme, Checkbox, Tag, Radio, Select } from 'antd';
import { SendOutlined, ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import { inspirationApi, projectApi } from '../services/api';
import { AIProjectGenerator, type GenerationConfig } from '../components/generation/AIProjectGenerator';
import { CHANNELS, getGenresByChannel, THEME_TAGS, CHARACTER_TAGS, PLOT_TAGS, MAX_TAGS_PER_DIMENSION } from '../constants/novelTaxonomy';
import { DIRECTION_CARD_LABELS } from '../types';
import type { InspirationGuidance } from '../types';
import type { InspirationDirectionCard, InspirationGenerationContext, InspirationOptionsContext, InspirationQualityReport, InspirationStoryBibleDraft, Project, ProjectCreate } from '../types';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

type Step = 'channel_select' | 'genre_select' | 'tag_select' | 'plot_brief' | 'idea' | 'direction_cards' | 'perspective' | 'outline_mode' | 'confirm' | 'generating' | 'complete';

const entrySteps = new Set<Step>(['channel_select', 'genre_select', 'tag_select', 'plot_brief']);
const restorableSteps = new Set<Step>(['channel_select', 'genre_select', 'tag_select', 'plot_brief', 'idea', 'direction_cards', 'perspective', 'outline_mode', 'confirm']);
const TAG_COLLAPSED_VISIBLE_COUNT = 24;

type TaxonomyTagOption = (typeof THEME_TAGS)[number];
type TagDimension = 'theme' | 'character' | 'plot';

interface Message {
  type: 'ai' | 'user';
  content: string;
  options?: string[];
  optionsDisabled?: boolean; // 标记选项是否已禁用
}

interface WizardData {
  title: string;
  description: string;
  theme: string;
  genre: string[];
  world_setting?: string;
  core_conflict?: string;
  protagonist?: string;
  golden_finger?: string | null;
  narrative_perspective: string;
  outline_mode: 'one-to-one' | 'one-to-many';
}

type InspirationDraftAction = 'save_inspiration' | 'create_project_draft';

interface InspirationDraftRecord {
  id: string;
  title: string;
  description: string;
  theme: string;
  genre: string[];
  world_setting?: string;
  core_conflict?: string;
  protagonist?: string;
  golden_finger?: string | null;
  narrative_perspective: string;
  outline_mode: 'one-to-one' | 'one-to-many';
  initial_idea: string;
  story_bible_draft?: InspirationStoryBibleDraft;
  created_at: string;
  status: 'draft';
}

interface InspirationDraftActionClients {
  saveInspiration: (draft: InspirationDraftRecord) => void;
  createProjectDraft: (payload: ProjectCreate) => Promise<Project>;
}

// 缓存数据接口
interface CacheData {
  messages: Message[];
  currentStep: Step;
  wizardData: Partial<WizardData>;
  initialIdea: string;
  directionCards?: InspirationDirectionCard[];
  selectedDirectionCardIds?: string[];
  activeDirectionCard?: InspirationDirectionCard | null;
  storyBibleDraft?: InspirationStoryBibleDraft;
  storyBibleQualityReport?: InspirationQualityReport | null;
  storyBibleQualityError?: string | null;
  timestamp: number;
}

// 缓存键
const CACHE_KEY = 'inspiration_conversation_cache';
const INSPIRATION_DRAFTS_KEY = 'inspiration_saved_drafts';
// 缓存有效期：24小时
const CACHE_EXPIRY = 24 * 60 * 60 * 1000;

function normalizeWizardData(
  data: WizardData,
  initialIdea: string,
  storyBibleDraft?: InspirationStoryBibleDraft,
): InspirationDraftRecord {
  const draft: InspirationDraftRecord = {
    id: `inspiration-${Date.now()}`,
    title: data.title,
    description: data.description,
    theme: data.theme,
    genre: data.genre,
    world_setting: data.world_setting,
    core_conflict: data.core_conflict,
    protagonist: data.protagonist,
    golden_finger: data.golden_finger,
    narrative_perspective: data.narrative_perspective,
    outline_mode: data.outline_mode,
    initial_idea: initialIdea,
    created_at: new Date().toISOString(),
    status: 'draft',
  };

  if (storyBibleDraft) {
    draft.story_bible_draft = storyBibleDraft;
  }

  return draft;
}

function buildProjectDraftPayload(data: WizardData): ProjectCreate {
  const payload: ProjectCreate = {
    title: data.title,
    description: data.description,
    theme: data.theme,
    genre: data.genre.join('、'),
    target_words: 100000,
    outline_mode: data.outline_mode,
  };

  if (data.world_setting) {
    payload.world_rules = data.world_setting;
  }

  return payload;
}

function buildProjectEntryPath(projectId: string): string {
  return `/project/${projectId}/sponsor`;
}

type InspirationGenerationConfig = GenerationConfig & {
  world_setting?: string;
  core_conflict?: string;
  protagonist?: string;
  golden_finger?: string;
};

function buildInspirationGenerationContext(
  data: WizardData,
  initialIdea: string,
  storyBibleDraft?: InspirationStoryBibleDraft,
  activeDirectionCard?: InspirationDirectionCard | null,
  guidance?: InspirationGuidance,
): InspirationGenerationContext | undefined {
  if (!storyBibleDraft) {
    return undefined;
  }

  const context: InspirationGenerationContext = {
    source: 'inspiration_story_bible',
    initial_idea: initialIdea || undefined,
    confirmed_fields: buildOptionsContext(data, initialIdea),
    direction_card: activeDirectionCard || undefined,
    story_bible_draft: storyBibleDraft,
  };

  if (guidance) {
    context.guidance = guidance;
  }

  return context;
}

function buildGenerationConfig(
  data: WizardData,
  initialIdea: string = '',
  storyBibleDraft?: InspirationStoryBibleDraft,
  activeDirectionCard?: InspirationDirectionCard | null,
  guidance?: InspirationGuidance,
): InspirationGenerationConfig {
  const config: InspirationGenerationConfig = {
    title: data.title,
    description: data.description,
    theme: data.theme,
    genre: data.genre,
    narrative_perspective: data.narrative_perspective,
    target_words: 100000,
    chapter_count: 3,
    character_count: 5,
    outline_mode: data.outline_mode || 'one-to-many',
  };

  if (data.world_setting) {
    config.world_setting = data.world_setting;
  }
  if (data.core_conflict) {
    config.core_conflict = data.core_conflict;
  }
  if (data.protagonist) {
    config.protagonist = data.protagonist;
  }
  if (data.golden_finger) {
    config.golden_finger = data.golden_finger;
  }

  const inspirationContext = buildInspirationGenerationContext(data, initialIdea, storyBibleDraft, activeDirectionCard, guidance);
  if (inspirationContext) {
    config.inspiration_context = inspirationContext;
  }

  return config;
}

const DIRECTION_CARD_COUNT = 3;

const storyBibleFieldOrder = [
  'core_idea',
  'story_promise',
  'target_genre',
  'world_rules',
  'core_conflict',
  'protagonist_profile',
  'antagonistic_force',
  'golden_finger',
  'opening_hook',
  'tone_and_style',
  'foreshadowing_seeds',
  'constraints',
] as const satisfies readonly (keyof InspirationStoryBibleDraft)[];

type StoryBibleField = typeof storyBibleFieldOrder[number];

const storyBibleFieldLabels: Record<StoryBibleField, string> = {
  core_idea: '核心创意',
  story_promise: '故事承诺',
  target_genre: '目标类型',
  world_rules: '世界规则',
  core_conflict: '核心冲突',
  protagonist_profile: '主角画像',
  antagonistic_force: '对抗力量',
  golden_finger: '金手指/特殊优势',
  opening_hook: '开篇钩子',
  tone_and_style: '语气风格',
  foreshadowing_seeds: '伏笔种子',
  constraints: '写作约束',
};

const storyBibleListFields = new Set<StoryBibleField>([
  'target_genre',
  'world_rules',
  'foreshadowing_seeds',
  'constraints',
]);

const directionCardFieldOrder = [
  'hook',
  'title',
  'genre',
  'world_setting',
  'core_conflict',
  'protagonist',
  'golden_finger',
  'opening_hook',
  'selling_points',
  'risks',
] as const;

function formatDirectionCardValue(value: string | string[] | null | undefined): string {
  if (Array.isArray(value)) {
    return value.join('、');
  }

  if (!value) {
    return '无';
  }

  return value;
}

function storyBibleFieldToText(draft: InspirationStoryBibleDraft, field: StoryBibleField): string {
  const value = draft[field];
  if (Array.isArray(value)) {
    return value.join('\n');
  }
  return value ?? '';
}

function storyBibleTextToValue(field: StoryBibleField, value: string): string | string[] | null {
  if (storyBibleListFields.has(field)) {
    return value.split('\n').map(item => item.trim()).filter(Boolean);
  }
  if (field === 'golden_finger') {
    return value.trim() || null;
  }
  return value;
}

function isStoryBibleDraft(draft: InspirationStoryBibleDraft | InspirationDirectionCard): draft is InspirationStoryBibleDraft {
  return 'core_idea' in draft && 'story_promise' in draft;
}

function formatQualityDimensionLabel(dimension: keyof InspirationQualityReport['dimensions']): string {
  const labels: Record<keyof InspirationQualityReport['dimensions'], string> = {
    novelty: '新颖度',
    writability: '可写性',
    commercial_hook: '商业爽点',
    consistency: '一致性',
    long_form_potential: '长篇支撑度',
  };
  return labels[dimension] || dimension;
}

function directionCardToWizardData(card: InspirationDirectionCard): Partial<WizardData> {
  return {
    title: card.title,
    description: card.hook,
    theme: card.core_conflict,
    genre: card.genre,
    world_setting: card.world_setting,
    core_conflict: card.core_conflict,
    protagonist: card.protagonist,
    golden_finger: card.golden_finger || null,
  };
}

function buildOptionsContext(data: Partial<WizardData>, initialIdea: string): InspirationOptionsContext {
  return {
    initial_idea: initialIdea,
    title: data.title,
    description: data.description,
    theme: data.theme,
    genre: data.genre,
    world_setting: data.world_setting,
    core_conflict: data.core_conflict,
    protagonist: data.protagonist,
    golden_finger: data.golden_finger,
  };
}

function saveInspirationDraftToStorage(draft: InspirationDraftRecord, storage: Storage = localStorage): void {
  const raw = storage.getItem(INSPIRATION_DRAFTS_KEY);
  const existing = raw ? JSON.parse(raw) as InspirationDraftRecord[] : [];
  storage.setItem(INSPIRATION_DRAFTS_KEY, JSON.stringify([draft, ...existing].slice(0, 20)));
}

async function runInspirationDraftAction(
  action: InspirationDraftAction,
  data: WizardData,
  initialIdea: string,
  clients: InspirationDraftActionClients,
  storyBibleDraft?: InspirationStoryBibleDraft,
): Promise<InspirationDraftRecord | Project> {
  if (action === 'save_inspiration') {
    const draft = normalizeWizardData(data, initialIdea, storyBibleDraft);
    clients.saveInspiration(draft);
    return draft;
  }

  return clients.createProjectDraft(buildProjectDraftPayload(data));
}

interface InspirationTestUtils {
  INSPIRATION_DRAFTS_KEY: string;
  buildProjectDraftPayload: typeof buildProjectDraftPayload;
  buildProjectEntryPath: typeof buildProjectEntryPath;
  normalizeWizardData: typeof normalizeWizardData;
  runInspirationDraftAction: typeof runInspirationDraftAction;
  saveInspirationDraftToStorage: typeof saveInspirationDraftToStorage;
}

type InspirationComponent = React.FC & {
  __testUtils: InspirationTestUtils;
};

const InspirationImpl: React.FC = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState<Step>('channel_select');
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const { token } = theme.useToken();

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const [messages, setMessages] = useState<Message[]>([
    {
      type: 'ai',
      content: '你好！我是你的AI创作助手。让我们一起创作一部精彩的小说吧！\n\n请告诉我，你想写一本什么样的小说？',
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [draftActionLoading, setDraftActionLoading] = useState<InspirationDraftAction | null>(null);
  const [createdDraftProjectId, setCreatedDraftProjectId] = useState<string | null>(null);
  const [directionCards, setDirectionCards] = useState<InspirationDirectionCard[]>([]);
  const [selectedDirectionCardIds, setSelectedDirectionCardIds] = useState<string[]>([]);
  const [activeDirectionCard, setActiveDirectionCard] = useState<InspirationDirectionCard | null>(null);
  const [storyBibleDraft, setStoryBibleDraft] = useState<InspirationStoryBibleDraft | undefined>(undefined);
  const [storyBibleGenerating, setStoryBibleGenerating] = useState(false);
  const [storyBibleQualityLoading, setStoryBibleQualityLoading] = useState(false);
  const [storyBibleRepairing, setStoryBibleRepairing] = useState(false);
  const [storyBibleQualityReport, setStoryBibleQualityReport] = useState<InspirationQualityReport | null>(null);
  const [storyBibleQualityError, setStoryBibleQualityError] = useState<string | null>(null);

  // 收集的数据
  const [wizardData, setWizardData] = useState<Partial<WizardData>>({});
  // 保存用户的原始想法，用于保持上下文一致性
  const [initialIdea, setInitialIdea] = useState<string>('');
  const [selectedChannel, setSelectedChannel] = useState('');
  const [selectedGenre, setSelectedGenre] = useState('');
  const [selectedThemes, setSelectedThemes] = useState<string[]>([]);
  const [selectedCharacters, setSelectedCharacters] = useState<string[]>([]);
  const [selectedPlots, setSelectedPlots] = useState<string[]>([]);
  const [plotBrief, setPlotBrief] = useState('');
  const [guidanceEntryActive, setGuidanceEntryActive] = useState(false);
  const [themeTagsExpanded, setThemeTagsExpanded] = useState(false);
  const [characterTagsExpanded, setCharacterTagsExpanded] = useState(false);
  const [plotTagsExpanded, setPlotTagsExpanded] = useState(false);
   
  // 生成配置
  const [generationConfig, setGenerationConfig] = useState<InspirationGenerationConfig | null>(null);

  // Modal hook
  const [modal, contextHolder] = Modal.useModal();

  // 滚动容器引用
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const submitInFlightRef = useRef(false);

  // 标记是否已经加载缓存
  const [cacheLoaded, setCacheLoaded] = useState(false);

  // ==================== 缓存管理函数 ====================

  // 清除缓存
  const clearCache = useCallback(() => {
    try {
      localStorage.removeItem(CACHE_KEY);
    } catch (error) {
      console.error('清除缓存失败:', error);
    }
  }, []);

  // 保存到缓存
  const saveToCache = useCallback(() => {
    try {
      // 只在对话阶段保存，生成阶段不保存
      if (currentStep === 'generating' || currentStep === 'complete') {
        return;
      }

      if (guidanceEntryActive) {
        return;
      }

      // 只有用户有输入时才保存（至少两条消息：AI问候+用户回复）
      if (messages.length <= 1) {
        return;
      }

      const cacheData: CacheData = {
        messages,
        currentStep,
        wizardData,
        initialIdea,
        directionCards,
        selectedDirectionCardIds,
        activeDirectionCard,
        storyBibleDraft,
        storyBibleQualityReport,
        storyBibleQualityError,
        timestamp: Date.now()
      };

      localStorage.setItem(CACHE_KEY, JSON.stringify(cacheData));
    } catch (error) {
      console.error('保存缓存失败:', error);
    }
  }, [currentStep, messages, wizardData, initialIdea, directionCards, selectedDirectionCardIds, activeDirectionCard, storyBibleDraft, storyBibleQualityReport, storyBibleQualityError, guidanceEntryActive]);

  // 从缓存恢复
  const restoreFromCache = useCallback((): boolean => {
    try {
      const cached = localStorage.getItem(CACHE_KEY);
      if (!cached) {
        return false;
      }

      const cacheData: CacheData = JSON.parse(cached);
      const age = Date.now() - cacheData.timestamp;

      // 检查缓存是否过期
      if (age > CACHE_EXPIRY) {
        clearCache();
        return false;
      }

      // 必须有有效的对话数据
      if (!cacheData.messages || cacheData.messages.length <= 1) {
        return false;
      }

      if (!restorableSteps.has(cacheData.currentStep)) {
        clearCache();
        return false;
      }

      // 恢复所有状态
      setMessages(cacheData.messages);
      setCurrentStep(cacheData.currentStep);
      setWizardData(cacheData.wizardData);
      setInitialIdea(cacheData.initialIdea);
      setDirectionCards(cacheData.directionCards || []);
      setSelectedDirectionCardIds(cacheData.selectedDirectionCardIds || []);
      setActiveDirectionCard(cacheData.activeDirectionCard || null);
      setStoryBibleDraft(cacheData.storyBibleDraft);
      setStoryBibleQualityReport(cacheData.storyBibleQualityReport || null);
      setStoryBibleQualityError(cacheData.storyBibleQualityError || null);

      message.success('已恢复上次的对话进度', 2);
      return true;
    } catch (error) {
      console.error('恢复缓存失败:', error);
      clearCache();
      return false;
    }
  }, [clearCache]);

  // ==================== 组件挂载时恢复缓存 ====================

  useEffect(() => {
    if (!cacheLoaded) {
      restoreFromCache();
      setCacheLoaded(true);
    }
  }, [cacheLoaded, restoreFromCache]);

  // ==================== 自动保存：状态变化时保存 ====================

  useEffect(() => {
    // 防抖保存
    const timer = setTimeout(() => {
      if (cacheLoaded) {
        saveToCache();
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [messages, currentStep, wizardData, initialIdea, directionCards, selectedDirectionCardIds, activeDirectionCard, storyBibleDraft, storyBibleQualityReport, storyBibleQualityError, cacheLoaded, saveToCache]);

  // 自动滚动到底部
  const scrollToBottom = () => {
    setTimeout(() => {
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTo({
          top: chatContainerRef.current.scrollHeight,
          behavior: 'smooth'
        });
      }
    }, 100);
  };

  // 当消息更新时自动滚动
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const selectedChannelLabel = CHANNELS.find(channel => channel.id === selectedChannel)?.label || '';
  const selectedGenreOptions = selectedChannel ? getGenresByChannel(selectedChannel) : [];

  const resetGuidanceSelections = () => {
    setSelectedChannel('');
    setSelectedGenre('');
    setSelectedThemes([]);
    setSelectedCharacters([]);
    setSelectedPlots([]);
    setPlotBrief('');
    setGuidanceEntryActive(false);
    setThemeTagsExpanded(false);
    setCharacterTagsExpanded(false);
    setPlotTagsExpanded(false);
  };

  const handleChannelChange = (channelId: string) => {
    setSelectedChannel(channelId);
    setSelectedGenre('');
    setSelectedThemes([]);
    setSelectedCharacters([]);
    setSelectedPlots([]);
    setPlotBrief('');
    setThemeTagsExpanded(false);
    setCharacterTagsExpanded(false);
    setPlotTagsExpanded(false);
  };

  const handleGenreChange = (genreLabel: string) => {
    setSelectedGenre(genreLabel);
  };

  const handleSkipTagFlow = () => {
    resetGuidanceSelections();
    setInputValue('');
    setMessages([
      {
        type: 'ai',
        content: '你好！我是你的AI创作助手。让我们一起创作一部精彩的小说吧！\n\n请告诉我，你想写一本什么样的小说？',
      }
    ]);
    setCurrentStep('idea');
  };

  const toggleTagSelection = (dimension: TagDimension, label: string, checked: boolean) => {
    const dimensionConfig = {
      theme: {
        label: '主题标签',
        selected: selectedThemes,
        setSelected: setSelectedThemes,
      },
      character: {
        label: '角色标签',
        selected: selectedCharacters,
        setSelected: setSelectedCharacters,
      },
      plot: {
        label: '情节标签',
        selected: selectedPlots,
        setSelected: setSelectedPlots,
      },
    }[dimension];

    const alreadySelected = dimensionConfig.selected.includes(label);
    if (checked && !alreadySelected && dimensionConfig.selected.length >= MAX_TAGS_PER_DIMENSION) {
      message.warning(`${dimensionConfig.label}最多选择 ${MAX_TAGS_PER_DIMENSION} 个`);
      return;
    }

    if (checked) {
      dimensionConfig.setSelected(alreadySelected ? dimensionConfig.selected : [...dimensionConfig.selected, label]);
      return;
    }

    dimensionConfig.setSelected(dimensionConfig.selected.filter(item => item !== label));
  };

  const getVisibleTagOptions = (
    options: TaxonomyTagOption[],
    selectedValues: string[],
    expanded: boolean,
  ): TaxonomyTagOption[] => {
    if (expanded || options.length <= TAG_COLLAPSED_VISIBLE_COUNT) {
      return options;
    }

    const leadingOptions = options.slice(0, TAG_COLLAPSED_VISIBLE_COUNT);
    const leadingIds = new Set(leadingOptions.map(option => option.id));
    const selectedSet = new Set(selectedValues);
    const selectedOverflowOptions = options.filter(option => selectedSet.has(option.label) && !leadingIds.has(option.id));

    return [...leadingOptions, ...selectedOverflowOptions];
  };

  const buildCurrentGuidance = (): InspirationGuidance | undefined => {
    const trimmedPlotBrief = plotBrief.trim();
    const guidance: InspirationGuidance = {
      channel: selectedChannelLabel || undefined,
      genre: selectedGenre || undefined,
      themes: selectedThemes,
      characters: selectedCharacters,
      plots: selectedPlots,
      plot_brief: trimmedPlotBrief || undefined,
    };

    const hasGuidance = Boolean(
      guidance.channel
      || guidance.genre
      || guidance.themes?.length
      || guidance.characters?.length
      || guidance.plots?.length
      || guidance.plot_brief,
    );

    return hasGuidance ? guidance : undefined;
  };

  const buildSynthesizedIdeaFromGuidance = (guidance: InspirationGuidance): string => {
    const categoryText = [
      guidance.channel,
      guidance.genre ? `${guidance.genre}题材` : undefined,
    ].filter(Boolean).join(' ');
    const tagParts = [
      guidance.themes?.length ? `${guidance.themes.join('、')}主题` : undefined,
      guidance.characters?.length ? `${guidance.characters.join('、')}角色` : undefined,
      guidance.plots?.length ? `${guidance.plots.join('、')}情节` : undefined,
    ].filter(Boolean);
    const core = [categoryText, ...tagParts].filter(Boolean).join('，');

    return `${core || '具有明确网文卖点'}的小说`;
  };

  const buildGuidanceMessage = (guidance: InspirationGuidance, idea: string): string => {
    return [
      '从标签导向生成故事方向：',
      guidance.channel ? `频道：${guidance.channel}` : null,
      guidance.genre ? `题材：${guidance.genre}` : null,
      guidance.themes?.length ? `主题：${guidance.themes.join('、')}` : null,
      guidance.characters?.length ? `角色：${guidance.characters.join('、')}` : null,
      guidance.plots?.length ? `情节：${guidance.plots.join('、')}` : null,
      guidance.plot_brief ? `剧情简述：${guidance.plot_brief}` : `自动补全创意：${idea}`,
    ].filter(Boolean).join('\n');
  };

  const requestDirectionCards = async (idea: string, guidance?: InspirationGuidance) => {
    const response = await inspirationApi.generateCards({
      idea,
      guidance,
      card_count: DIRECTION_CARD_COUNT,
      context: {
        initial_idea: idea,
        description: idea,
      },
    });

      if (response.error || !response.cards || response.cards.length === 0) {
        setDirectionCards([]);
        setSelectedDirectionCardIds([]);
        setActiveDirectionCard(null);
      const errorMessage: Message = {
        type: 'ai',
        content: response.error
          ? `生成故事方向时出错：${response.error}\n\n请重新生成一批方向，或重新开始调整初始创意。`
          : '暂时没有生成可用的故事方向，请重新生成一批方向，或重新开始调整初始创意。',
      };
      setMessages(prev => [...prev, errorMessage]);
      setCurrentStep('direction_cards');
      return;
    }

    setDirectionCards(response.cards);
    setSelectedDirectionCardIds([]);
    setActiveDirectionCard(null);
    const aiMessage: Message = {
      type: 'ai',
      content: response.prompt || '我先为你生成了三张故事方向卡。可以选择一个继续深化，也可以合并两个方向。',
    };
    setMessages(prev => [...prev, aiMessage]);
    setCurrentStep('direction_cards');
  };

  const handleGenerateGuidedCards = async () => {
    if (submitInFlightRef.current || loading || draftActionLoading) {
      return;
    }

    const guidance = buildCurrentGuidance();
    if (!guidance?.channel || !guidance.genre) {
      message.warning('请先选择频道和题材');
      return;
    }

    const synthesizedIdea = guidance.plot_brief?.trim() || buildSynthesizedIdeaFromGuidance(guidance);
    submitInFlightRef.current = true;
    setGuidanceEntryActive(true);
    setInitialIdea(synthesizedIdea);
    setMessages([
      {
        type: 'ai',
        content: '已收到你的标签导向，我会先生成三张故事方向卡供你比较。',
      },
      {
        type: 'user',
        content: buildGuidanceMessage(guidance, synthesizedIdea),
      },
    ]);
    setLoading(true);

    try {
      await requestDirectionCards(synthesizedIdea, guidance);
    } catch (error: unknown) {
      console.error('生成标签导向故事方向失败:', error);
      const errMsg = error instanceof Error ? error.message : '生成失败，请重试';
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || errMsg);
    } finally {
      submitInFlightRef.current = false;
      setLoading(false);
    }
  };

  const continueWithDirectionCard = (card: InspirationDirectionCard) => {
    const updatedData = {
      ...wizardData,
      ...directionCardToWizardData(card),
    };
    setWizardData(updatedData);
    setActiveDirectionCard(card);
    setStoryBibleDraft(undefined);
    setStoryBibleQualityReport(null);
    setStoryBibleQualityError(null);

    const userMessage: Message = {
      type: 'user',
      content: `继续深化此方向：${card.title}`,
    };
    const aiMessage: Message = {
      type: 'ai',
      content: '已将方向卡的书名、类型、世界规则、核心冲突、主角原型与金手指写入后续上下文。接下来，请选择小说的叙事视角：',
      options: ['第一人称', '第三人称', '全知视角']
    };
    setMessages(prev => [...prev, userMessage, aiMessage]);
    setCurrentStep('perspective');
    setSelectedDirectionCardIds([]);
  };

  const handleToggleDirectionCard = (cardId: string) => {
    setSelectedDirectionCardIds(prev => {
      if (prev.includes(cardId)) {
        return prev.filter(id => id !== cardId);
      }
      return [...prev, cardId];
    });
  };

  const handleRegenerateDirectionCards = async () => {
    if (!initialIdea.trim()) {
      message.warning('缺少原始创意，无法重新生成方向');
      return;
    }

    setLoading(true);
    try {
      await requestDirectionCards(initialIdea);
      message.success('已重新生成一批方向');
    } catch (error: unknown) {
      console.error('重新生成方向卡失败:', error);
      const errMsg = error instanceof Error ? error.message : '重新生成失败，请重试';
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || errMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleMergeDirectionCards = async () => {
    const selectedCards = selectedDirectionCardIds
      .map(id => directionCards.find(card => card.id === id))
      .filter((card): card is InspirationDirectionCard => Boolean(card));

    if (selectedCards.length !== 2) {
      message.warning('请选择且仅选择两个方向进行合并');
      return;
    }

    const [primaryCard, secondaryCard] = selectedCards;
    if (!primaryCard || !secondaryCard) {
      message.warning('请选择且仅选择两个方向进行合并');
      return;
    }

    setLoading(true);
    try {
      const cardsToMerge: [InspirationDirectionCard, InspirationDirectionCard] = [primaryCard, secondaryCard];
      const response = await inspirationApi.mergeCards({
        cards: cardsToMerge,
        primary_card_id: primaryCard.id,
      });

      if (response.error || !response.card) {
        message.error(response.error || '合并方向失败，请重试');
        return;
      }

      setDirectionCards([response.card]);
      setSelectedDirectionCardIds([response.card.id]);
      setActiveDirectionCard(response.card);
      const aiMessage: Message = {
        type: 'ai',
        content: `已合并为新的故事方向「${response.card.title}」。你可以继续深化此方向，或重新生成一批方向。`,
      };
      setMessages(prev => [...prev, aiMessage]);
      message.success('方向已合并');
    } catch (error: unknown) {
      console.error('合并方向卡失败:', error);
      const errMsg = error instanceof Error ? error.message : '合并失败，请重试';
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || errMsg);
    } finally {
      setLoading(false);
    }
  };

  const updateStoryBibleField = (field: StoryBibleField, value: string) => {
    setStoryBibleDraft(prev => {
      if (!prev) {
        return prev;
      }

      return {
        ...prev,
        [field]: storyBibleTextToValue(field, value),
      } as InspirationStoryBibleDraft;
    });
  };

  const handleGenerateStoryBible = async () => {
    const data = wizardData as Partial<WizardData>;
    if (!initialIdea.trim() && !data.description && !activeDirectionCard) {
      message.warning('缺少原始创意或故事方向，无法生成故事圣经草稿');
      return;
    }

    setStoryBibleGenerating(true);
    setStoryBibleQualityReport(null);
    setStoryBibleQualityError(null);

    try {
      const response = await inspirationApi.generateStoryBible({
        idea: initialIdea,
        direction_card: activeDirectionCard || undefined,
        confirmed_fields: buildOptionsContext(data, initialIdea),
        user_edits: storyBibleDraft,
        constraints: storyBibleDraft?.constraints || [],
      });

      if (response.error || !response.story_bible_draft) {
        message.error(response.error || '生成故事圣经草稿失败，请重试');
        return;
      }

      const draft = response.story_bible_draft;
      setStoryBibleDraft(draft);
      message.success('故事圣经草稿已生成');

      setStoryBibleQualityLoading(true);
      try {
        const report = await inspirationApi.evaluate({
          story_bible_draft: draft,
          context: buildOptionsContext(data, initialIdea),
        });
        setStoryBibleQualityReport(report);
      } catch (error: unknown) {
        console.error('故事圣经质量评估失败:', error);
        const errMsg = error instanceof Error ? error.message : '质量评估失败，请稍后重试';
        const axiosError = error as { response?: { data?: { detail?: string | { message?: string } } } };
        const detail = axiosError.response?.data?.detail;
        setStoryBibleQualityError(typeof detail === 'string' ? detail : detail?.message || errMsg);
        message.warning('故事圣经已生成，但质量评估失败');
      } finally {
        setStoryBibleQualityLoading(false);
      }
    } catch (error: unknown) {
      console.error('生成故事圣经草稿失败:', error);
      const errMsg = error instanceof Error ? error.message : '生成故事圣经草稿失败，请重试';
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || errMsg);
    } finally {
      setStoryBibleGenerating(false);
    }
  };

  const handleRepairStoryBible = async () => {
    if (!storyBibleDraft) {
      message.warning('请先生成故事圣经草稿');
      return;
    }

    if (storyBibleRepairing) {
      return;
    }

    const issues = storyBibleQualityReport?.issues || [];
    setStoryBibleRepairing(true);
    setStoryBibleQualityError(null);

    try {
      const result = await inspirationApi.repair({
        draft: storyBibleDraft,
        issues,
        issue_ids: issues.map(issue => issue.id),
        instructions: '只执行一次针对当前质量报告的修复；保留用户确认的故事方向、核心前提和未被问题命中的字段。',
      });

      if (result.repaired && isStoryBibleDraft(result.draft)) {
        setStoryBibleDraft(result.draft);
        message.success('故事圣经已完成一次修复');
      } else {
        message.warning(result.warnings?.[0] || '本次修复未能完成，已保留原草稿');
      }

      if (storyBibleQualityReport) {
        setStoryBibleQualityReport({
          ...storyBibleQualityReport,
          issues: result.remaining_issues || [],
          warnings: [...(storyBibleQualityReport.warnings || []), ...(result.warnings || [])],
        });
      }
    } catch (error: unknown) {
      console.error('故事圣经修复失败:', error);
      const errMsg = error instanceof Error ? error.message : '修复失败，请稍后重试';
      const axiosError = error as { response?: { data?: { detail?: string | { message?: string } } } };
      const detail = axiosError.response?.data?.detail;
      setStoryBibleQualityError(typeof detail === 'string' ? detail : detail?.message || errMsg);
      message.error('故事圣经修复失败，请重试');
    } finally {
      setStoryBibleRepairing(false);
    }
  };

  const handleSendMessage = async () => {
    if (submitInFlightRef.current || loading || draftActionLoading) {
      return;
    }

    if (!inputValue.trim()) {
      message.warning('请输入内容');
      return;
    }

    submitInFlightRef.current = true;

    const userMessage: Message = {
      type: 'user',
      content: inputValue,
    };
    setMessages(prev => [...prev, userMessage]);

    const userInput = inputValue;
    setInputValue('');
    setLoading(true);

    try {
      if (currentStep === 'idea') {
        setGuidanceEntryActive(false);
        setInitialIdea(userInput);
        await requestDirectionCards(userInput);
      } else {
        await handleCustomInput(userInput);
      }
    } catch (error: unknown) {
      console.error('发送消息失败:', error);
      const errMsg = error instanceof Error ? error.message : '生成失败，请重试';
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || errMsg);
    } finally {
      submitInFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleSelectOption = async (option: string) => {
    // 立即禁用当前消息的选项（单选场景）
    setMessages(prev => {
      const newMessages = [...prev];
      const lastAiMessageIndex = newMessages.map((m, i) => m.type === 'ai' && m.options ? i : -1).filter(i => i >= 0).pop();
      if (lastAiMessageIndex !== undefined && lastAiMessageIndex >= 0) {
        newMessages[lastAiMessageIndex] = {
          ...newMessages[lastAiMessageIndex],
          optionsDisabled: true
        };
      }
      return newMessages;
    });

    if (currentStep === 'perspective') {
      const userMessage: Message = {
        type: 'user',
        content: option,
      };
      setMessages(prev => [...prev, userMessage]);

      const updatedData = { ...wizardData, narrative_perspective: option };
      setWizardData(updatedData);

      // 询问大纲模式
      const aiMessage: Message = {
        type: 'ai',
        content: `很好！现在请选择你想要的大纲模式：

📋 一对一模式：传统模式，一个大纲对应一个章节，适合结构清晰、章节独立的小说。

📚 一对多模式：细化模式，一个大纲可以展开成多个章节，适合需要详细展开情节的小说。

请选择：`,
        options: ['📋 一对一模式', '📚 一对多模式']
      };
      setMessages(prev => [...prev, aiMessage]);
      setCurrentStep('outline_mode');
      return;
    }

    if (currentStep === 'outline_mode') {
      const userMessage: Message = {
        type: 'user',
        content: option,
      };
      setMessages(prev => [...prev, userMessage]);

      // 将选项转换为实际的模式值
      const modeValue: 'one-to-one' | 'one-to-many' =
        option === '📋 一对一模式' ? 'one-to-one' : 'one-to-many';

      const updatedData = {
        ...wizardData,
        outline_mode: modeValue,
        genre: wizardData.genre || []
      } as WizardData;
      setWizardData(updatedData);

      // 显示摘要
      const modeText = modeValue === 'one-to-one' ? '一对一模式' : '一对多模式';
      const hiddenStepSummaryLines = [
        updatedData.world_setting ? `🌍 世界规则：${updatedData.world_setting}` : null,
        updatedData.core_conflict ? `⚔️ 核心冲突：${updatedData.core_conflict}` : null,
        updatedData.protagonist ? `👤 主角原型：${updatedData.protagonist}` : null,
        updatedData.golden_finger ? `✨ 金手指：${updatedData.golden_finger}` : null,
      ].filter(Boolean).join('\n');
      const summary = `
太棒了！你的小说设定已完成，请确认：

📖 书名：${updatedData.title}
📝 简介：${updatedData.description}
🎯 主题：${updatedData.theme}
🏷️ 类型：${updatedData.genre.join('、')}
${hiddenStepSummaryLines ? `${hiddenStepSummaryLines}\n` : ''}👁️ 视角：${updatedData.narrative_perspective}
📋 大纲模式：${modeText}

请选择下一步操作：
      `.trim();

      const aiMessage: Message = {
        type: 'ai',
        content: summary,
        options: ['生成故事圣经草稿', '保存灵感草稿', '创建项目草稿', '开始完整项目生成', '重新开始']
      };
      setMessages(prev => [...prev, aiMessage]);
      setCurrentStep('confirm');
      return;
    }

    if (currentStep === 'confirm') {
      if (option === '生成故事圣经草稿') {
        const userMessage: Message = {
          type: 'user',
          content: '生成故事圣经草稿',
        };
        setMessages(prev => [...prev, userMessage]);
        await handleGenerateStoryBible();
        const aiMessage: Message = {
          type: 'ai',
          content: '故事圣经草稿处理完成。你可以在上方继续编辑草稿，或选择保存灵感草稿、创建项目草稿、开始完整项目生成。',
          options: ['保存灵感草稿', '创建项目草稿', '开始完整项目生成', '重新开始'],
        };
        setMessages(prev => [...prev, aiMessage]);
        return;
      }

      if (option === '保存灵感草稿') {
        const userMessage: Message = {
          type: 'user',
          content: '保存灵感草稿',
        };
        setMessages(prev => [...prev, userMessage]);

        setDraftActionLoading('save_inspiration');
        try {
          const data = wizardData as WizardData;
          const draft = await runInspirationDraftAction('save_inspiration', data, initialIdea, {
            saveInspiration: saveInspirationDraftToStorage,
            createProjectDraft: projectApi.createProject,
          }, storyBibleDraft) as InspirationDraftRecord;
          const aiMessage: Message = {
            type: 'ai',
            content: `已保存为灵感草稿「${draft.title}」。这不会创建角色、组织、职业或改写世界观；你仍可以选择创建项目草稿或进入完整生成流程。`,
            options: ['创建项目草稿', '开始完整项目生成', '重新开始'],
          };
          setMessages(prev => [...prev, aiMessage]);
          message.success('灵感草稿已保存');
        } catch (error) {
          console.error('保存灵感草稿失败:', error);
          message.error('保存灵感草稿失败');
        } finally {
          setDraftActionLoading(null);
        }
        return;
      }

      if (option === '创建项目草稿') {
        const userMessage: Message = {
          type: 'user',
          content: '创建项目草稿',
        };
        setMessages(prev => [...prev, userMessage]);

        setDraftActionLoading('create_project_draft');
        try {
          const data = wizardData as WizardData;
          const project = await runInspirationDraftAction('create_project_draft', data, initialIdea, {
            saveInspiration: saveInspirationDraftToStorage,
            createProjectDraft: projectApi.createProject,
          }) as Project;
          if (!project.id) {
            throw new Error('项目创建成功但未返回项目ID');
          }

          clearCache();
          const aiMessage: Message = {
            type: 'ai',
            content: `项目草稿《${project.title}》已创建。当前只保存基础创意信息，没有自动创建角色、组织、职业或覆盖世界观；你可以进入项目后通过评审结果逐步接受 AI 草稿。`,
            options: ['进入项目', '重新开始'],
          };
          setMessages(prev => [...prev, aiMessage]);
          setCreatedDraftProjectId(project.id);
          message.success('项目草稿已创建');
          setTimeout(() => navigate(buildProjectEntryPath(project.id)), 800);
        } catch (error) {
          console.error('创建项目草稿失败:', error);
          message.error('创建项目草稿失败，请重试');
        } finally {
          setDraftActionLoading(null);
        }
        return;
      }

      if (option === '进入项目') {
        if (createdDraftProjectId) {
          navigate(buildProjectEntryPath(createdDraftProjectId));
        }
        return;
      }

      if (option === '开始完整项目生成') {
        const userMessage: Message = {
          type: 'user',
          content: '开始完整项目生成',
        };
        setMessages(prev => [...prev, userMessage]);

        const aiMessage: Message = {
          type: 'ai',
          content: '好的！将进入完整生成流程。后续角色、组织、职业会遵循候选/策略评审规则，不再作为默认静默入库路径。'
        };
        setMessages(prev => [...prev, aiMessage]);

        // 清除缓存（对话完成，进入生成阶段）
        clearCache();

        // 开始生成项目
        const data = wizardData as WizardData;
        const guidance = buildCurrentGuidance();
        const config = buildGenerationConfig(data, initialIdea, storyBibleDraft, activeDirectionCard, guidance);
        setGenerationConfig(config);
        setCurrentStep('generating');
        return;
      } else if (option === '重新开始') {
        handleRestart();
        return;
      }
    }

    message.info('请按当前新版流程选择方向卡或确认操作');
  };

  const handleCustomInput = async (input: string) => {
    setLoading(true);
    try {
      const updatedData = { ...wizardData };

      if (currentStep === 'perspective') {
        updatedData.narrative_perspective = input;
        setWizardData(updatedData);
        
        // 直接进入大纲模式选择
        const aiMessage: Message = {
          type: 'ai',
          content: `很好！现在请选择你想要的大纲模式：

📋 一对一模式：传统模式，一个大纲对应一个章节，适合结构清晰、章节独立的小说。

📚 一对多模式：细化模式，一个大纲可以展开成多个章节，适合需要详细展开情节的小说。

请选择：`,
          options: ['📋 一对一模式', '📚 一对多模式']
        };
        setMessages(prev => [...prev, aiMessage]);
        setCurrentStep('outline_mode');
        setLoading(false);
        return;
      } else if (currentStep === 'outline_mode') {
        // 大纲模式不支持自定义输入
        message.warning('请从选项中选择一个大纲模式');
        setLoading(false);
        return;
      }

      message.info('请按新版流程选择方向卡操作或确认选项');
    } catch (error: unknown) {
      console.error('处理自定义输入失败:', error);
      const errMsg = error instanceof Error ? error.message : '处理失败，请重试';
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError.response?.data?.detail || errMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleRestart = () => {
    // 清除缓存
    clearCache();

    setCurrentStep('channel_select');
    setMessages([
      {
        type: 'ai',
        content: '好的，让我们重新开始！\n\n请告诉我，你想写一本什么样的小说？',
      }
    ]);
    setWizardData({});
    setInitialIdea('');
    resetGuidanceSelections();
    setInputValue('');
    setDirectionCards([]);
    setSelectedDirectionCardIds([]);
    setActiveDirectionCard(null);
    setStoryBibleDraft(undefined);
    setStoryBibleGenerating(false);
    setStoryBibleQualityLoading(false);
    setStoryBibleQualityReport(null);
    setStoryBibleQualityError(null);
    setCreatedDraftProjectId(null);
    setLoading(false);
  };

  const handleBack = () => {
    navigate('/projects');
  };

  // 生成完成回调
  const handleComplete = (_projectId: string) => {
    void _projectId;
    // 确保清除缓存
    clearCache();
    setCurrentStep('complete');
  };

  // 返回对话界面
  const handleBackToChat = () => {
    clearCache();
    setCurrentStep('idea');
    setGenerationConfig(null);
    handleRestart();
  };

  const renderGuidancePreview = () => {
    const previewItems = [
      selectedChannelLabel ? { label: '频道', value: selectedChannelLabel } : null,
      selectedGenre ? { label: '题材', value: selectedGenre } : null,
      selectedThemes.length ? { label: '主题', value: selectedThemes.join('、') } : null,
      selectedCharacters.length ? { label: '角色', value: selectedCharacters.join('、') } : null,
      selectedPlots.length ? { label: '情节', value: selectedPlots.join('、') } : null,
    ].filter((item): item is { label: string; value: string } => Boolean(item));

    if (previewItems.length === 0) {
      return null;
    }

    return (
      <Alert
        type="info"
        showIcon
        message="当前创作导向"
        description={(
          <Space wrap size={[8, 8]}>
            {previewItems.map(item => (
              <Tag key={item.label} color="processing">
                {item.label}：{item.value}
              </Tag>
            ))}
          </Space>
        )}
      />
    );
  };

  const renderTagPool = (
    title: string,
    options: TaxonomyTagOption[],
    selectedValues: string[],
    expanded: boolean,
    setExpanded: (expanded: boolean) => void,
    dimension: TagDimension,
  ) => {
    const visibleOptions = getVisibleTagOptions(options, selectedValues, expanded);
    const hasOverflow = options.length > TAG_COLLAPSED_VISIBLE_COUNT;
    const reachedLimit = selectedValues.length >= MAX_TAGS_PER_DIMENSION;

    return (
      <Card size="small" styles={{ body: { padding: 14 } }}>
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
            <Text strong>{title}</Text>
            <Tag color={reachedLimit ? 'warning' : 'default'}>
              已选 {selectedValues.length}/{MAX_TAGS_PER_DIMENSION}
            </Tag>
          </div>

          <Space wrap size={[8, 8]}>
            {visibleOptions.map(option => {
              const checked = selectedValues.includes(option.label);
              const selectionBlocked = !checked && reachedLimit;

              return (
                <Tag.CheckableTag
                  key={option.id}
                  checked={checked}
                  onClick={(event) => {
                    if (selectionBlocked) {
                      event.preventDefault();
                      event.stopPropagation();
                      message.warning(`${title}最多选择 ${MAX_TAGS_PER_DIMENSION} 个`);
                    }
                  }}
                  onChange={(nextChecked) => {
                    if (selectionBlocked && nextChecked) {
                      return;
                    }
                    toggleTagSelection(dimension, option.label, nextChecked);
                  }}
                  style={{
                    marginInlineEnd: 0,
                    opacity: selectionBlocked ? 0.45 : 1,
                    cursor: selectionBlocked ? 'not-allowed' : 'pointer',
                  }}
                  aria-disabled={selectionBlocked}
                >
                  {option.label}
                </Tag.CheckableTag>
              );
            })}
          </Space>

          {hasOverflow && (
            <Button type="link" size="small" onClick={() => setExpanded(!expanded)} style={{ alignSelf: 'flex-start', padding: 0 }}>
              {expanded ? '收起 ▲' : `展开 ▼（共 ${options.length} 个）`}
            </Button>
          )}
        </Space>
      </Card>
    );
  };

  const renderEntryStepPanel = () => {
    const stepIndexMap: Record<Step, number> = {
      channel_select: 1,
      genre_select: 2,
      tag_select: 3,
      plot_brief: 4,
      idea: 0,
      direction_cards: 0,
      perspective: 0,
      outline_mode: 0,
      confirm: 0,
      generating: 0,
      complete: 0,
    };

    if (!entrySteps.has(currentStep)) {
      return null;
    }

    return (
      <Card
        style={{
          marginBottom: 16,
          borderColor: token.colorPrimaryBorder,
          boxShadow: `0 8px 24px color-mix(in srgb, ${token.colorTextBase} 16%, transparent)`,
        }}
      >
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">标签导向入口 · 第 {stepIndexMap[currentStep]}/4 步</Text>
            <Title level={4} style={{ margin: 0 }}>先用频道、题材和标签收束灵感</Title>
            <Text type="secondary">也可以跳过这些步骤，直接回到原来的自由输入模式。</Text>
          </Space>

          {currentStep !== 'channel_select' && renderGuidancePreview()}

          {currentStep === 'channel_select' && (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Text strong>选择一个创作频道</Text>
              <Radio.Group
                optionType="button"
                buttonStyle="solid"
                size="large"
                value={selectedChannel || undefined}
                options={CHANNELS.map(channel => ({ label: channel.label, value: channel.id }))}
                onChange={(event) => handleChannelChange(event.target.value)}
              />
              <Space wrap>
                <Button type="primary" disabled={!selectedChannel} onClick={() => setCurrentStep('genre_select')}>
                  下一步：选择题材
                </Button>
                <Button onClick={handleSkipTagFlow}>跳过标签选择，直接自由输入</Button>
              </Space>
            </Space>
          )}

          {currentStep === 'genre_select' && (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Text strong>选择一个题材</Text>
              <Select
                size="large"
                placeholder="请选择题材"
                value={selectedGenre || undefined}
                options={selectedGenreOptions.map(genre => ({ label: genre.label, value: genre.label }))}
                onChange={handleGenreChange}
                style={{ width: '100%' }}
              />
              <Space wrap>
                <Button onClick={() => setCurrentStep('channel_select')}>上一步</Button>
                <Button type="primary" disabled={!selectedGenre} onClick={() => setCurrentStep('tag_select')}>
                  下一步：选择标签
                </Button>
                <Button onClick={handleSkipTagFlow}>跳过标签选择，直接自由输入</Button>
              </Space>
            </Space>
          )}

          {currentStep === 'tag_select' && (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              {renderTagPool('主题标签', THEME_TAGS, selectedThemes, themeTagsExpanded, setThemeTagsExpanded, 'theme')}
              {renderTagPool('角色标签', CHARACTER_TAGS, selectedCharacters, characterTagsExpanded, setCharacterTagsExpanded, 'character')}
              {renderTagPool('情节标签', PLOT_TAGS, selectedPlots, plotTagsExpanded, setPlotTagsExpanded, 'plot')}
              <Space wrap>
                <Button onClick={() => setCurrentStep('genre_select')}>上一步</Button>
                <Button type="primary" onClick={() => setCurrentStep('plot_brief')}>
                  下一步：补充剧情简述
                </Button>
                <Button onClick={handleSkipTagFlow}>跳过标签选择，直接自由输入</Button>
              </Space>
            </Space>
          )}

          {currentStep === 'plot_brief' && (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text strong>补充剧情简述（可选）</Text>
                <Text type="secondary">留空时会根据已选频道、题材和标签自动合成一句创意。</Text>
              </Space>
              <TextArea
                value={plotBrief}
                onChange={(event) => setPlotBrief(event.target.value)}
                placeholder="例如：主角在灵气复苏后的废土城市中经营一家能连接诸天的旧书店……"
                autoSize={{ minRows: 4, maxRows: 8 }}
                disabled={loading}
              />
              <Space wrap>
                <Button onClick={() => setCurrentStep('tag_select')} disabled={loading}>上一步</Button>
                <Button type="primary" onClick={handleGenerateGuidedCards} loading={loading}>
                  {plotBrief.trim() ? '生成故事方向' : '跳过简述并生成方向'}
                </Button>
                <Button onClick={handleSkipTagFlow} disabled={loading}>改用自由输入</Button>
              </Space>
            </Space>
          )}
        </Space>
      </Card>
    );
  };

  const renderDirectionCards = () => {
    if (currentStep !== 'direction_cards') {
      return null;
    }

    return (
      <Card
        style={{
          marginBottom: 16,
          borderColor: token.colorPrimaryBorder,
          boxShadow: `0 6px 18px color-mix(in srgb, ${token.colorTextBase} 12%, transparent)`,
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Title level={4} style={{ margin: 0 }}>故事方向</Title>
            <Text type="secondary">默认先比较三张方向卡；选中两个时，先点选的方向会作为合并主方向。</Text>
          </Space>

          {directionCards.length > 0 ? (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {directionCards.map((card) => {
                const selected = selectedDirectionCardIds.includes(card.id);

                return (
                  <Card
                    key={card.id}
                    hoverable={!loading}
                    onClick={() => !loading && handleToggleDirectionCard(card.id)}
                    style={{
                      cursor: loading ? 'not-allowed' : 'pointer',
                      border: selected ? `2px solid ${token.colorPrimary}` : `1px solid ${token.colorBorder}`,
                      background: selected ? token.colorPrimaryBg : token.colorBgContainer,
                      opacity: loading ? 0.7 : 1,
                      transition: 'all 0.3s ease',
                    }}
                    styles={{ body: { padding: 16 } }}
                  >
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      <Space style={{ width: '100%', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <Space align="start">
                          <Checkbox
                            checked={selected}
                            disabled={loading}
                            onClick={(event) => event.stopPropagation()}
                            onChange={() => handleToggleDirectionCard(card.id)}
                          />
                          <Space direction="vertical" size={2}>
                            <Text strong>{DIRECTION_CARD_LABELS.title}：{card.title}</Text>
                            <Text type="secondary">{DIRECTION_CARD_LABELS.hook}：{card.hook}</Text>
                          </Space>
                        </Space>
                        {selected && (
                          <Tag color="processing">第 {selectedDirectionCardIds.indexOf(card.id) + 1} 选择</Tag>
                        )}
                      </Space>

                      <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        {directionCardFieldOrder.map(field => {
                          if (field === 'title' || field === 'hook') {
                            return null;
                          }

                          return (
                            <div key={field} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                              <Text strong style={{ minWidth: 108, color: token.colorTextSecondary }}>
                                {DIRECTION_CARD_LABELS[field]}
                              </Text>
                              <Text>{formatDirectionCardValue(card[field])}</Text>
                            </div>
                          );
                        })}
                      </Space>

                      <Button
                        type="primary"
                        block
                        onClick={(event) => {
                          event.stopPropagation();
                          continueWithDirectionCard(card);
                        }}
                        disabled={loading}
                      >
                        继续深化此方向
                      </Button>
                    </Space>
                  </Card>
                );
              })}
            </Space>
          ) : (
            <Text type="secondary">暂无可用方向卡。</Text>
          )}

          <Space wrap>
            <Button onClick={handleRegenerateDirectionCards} loading={loading}>
              重新生成一批方向
            </Button>
            <Button onClick={handleMergeDirectionCards} loading={loading}>
              合并方向
            </Button>
          </Space>
        </Space>
      </Card>
    );
  };

  const renderStoryBiblePanel = () => {
    if (currentStep !== 'confirm') {
      return null;
    }

    const panelShadow = `0 6px 18px color-mix(in srgb, ${token.colorTextBase} 12%, transparent)`;

    return (
      <Card
        title="故事圣经草稿"
        style={{
          marginBottom: token.marginMD,
          borderColor: storyBibleDraft ? token.colorPrimaryBorder : token.colorBorder,
          boxShadow: panelShadow,
        }}
        extra={(
          <Button
            type={storyBibleDraft ? 'default' : 'primary'}
            onClick={handleGenerateStoryBible}
            loading={storyBibleGenerating}
            disabled={Boolean(draftActionLoading)}
          >
            {storyBibleDraft ? '重新生成故事圣经草稿' : '生成故事圣经草稿'}
          </Button>
        )}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Text type="secondary">
            草稿只保存在本地灵感草稿中；创建项目草稿仍只写入基础安全字段，不会自动创建角色、世界观或伏笔记录。
          </Text>

          {!storyBibleDraft ? (
            <Alert
              type="info"
              showIcon
              message="尚未生成故事圣经草稿"
              description="需要时点击“生成故事圣经草稿”整理核心设定，并自动获取质量评估。"
            />
          ) : (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
                  gap: token.marginMD,
                }}
              >
                {storyBibleFieldOrder.map(field => (
                  <div
                    key={field}
                    style={{
                      gridColumn: storyBibleListFields.has(field) || field === 'core_idea' || field === 'story_promise'
                        ? '1 / -1'
                        : undefined,
                    }}
                  >
                    <Space direction="vertical" size={token.marginXXS} style={{ width: '100%' }}>
                      <Text strong>{storyBibleFieldLabels[field]}</Text>
                      <TextArea
                        aria-label={storyBibleFieldLabels[field]}
                        value={storyBibleFieldToText(storyBibleDraft, field)}
                        onChange={(event) => updateStoryBibleField(field, event.target.value)}
                        autoSize={{ minRows: storyBibleListFields.has(field) ? 3 : 2, maxRows: 6 }}
                        placeholder={storyBibleListFields.has(field) ? '每行一条' : `填写${storyBibleFieldLabels[field]}`}
                      />
                    </Space>
                  </div>
                ))}
              </div>

              {storyBibleQualityLoading && (
                <Alert type="info" showIcon message="正在自动评估故事圣经质量..." />
              )}

              {storyBibleQualityError && (
                <Alert
                  type="warning"
                  showIcon
                  message="质量评估暂未完成"
                  description={storyBibleQualityError}
                />
              )}

              {storyBibleQualityReport && (
                <Card
                  size="small"
                  title={`质量评估：${storyBibleQualityReport.overall_score} 分`}
                  extra={(
                    <Button
                      size="small"
                      onClick={handleRepairStoryBible}
                      loading={storyBibleRepairing}
                      disabled={storyBibleGenerating || storyBibleQualityLoading}
                    >
                      一键修复
                    </Button>
                  )}
                  style={{ background: token.colorBgLayout }}
                >
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    <Space wrap>
                      {Object.entries(storyBibleQualityReport.dimensions).map(([dimension, score]) => (
                        <Tag key={dimension} color="processing">
                          {formatQualityDimensionLabel(dimension as keyof InspirationQualityReport['dimensions'])}：{score}
                        </Tag>
                      ))}
                    </Space>

                    {storyBibleQualityReport.issues.length > 0 && (
                      <Space direction="vertical" size={token.marginXXS} style={{ width: '100%' }}>
                        <Text strong>问题与建议</Text>
                        {storyBibleQualityReport.issues.map(issue => (
                          <Alert
                            key={issue.id}
                            type={issue.severity === 'error' ? 'error' : issue.severity === 'info' ? 'info' : 'warning'}
                            showIcon
                            message={issue.message}
                            description={issue.suggestion}
                          />
                        ))}
                      </Space>
                    )}

                    {storyBibleQualityReport.repair_suggestions.length > 0 && (
                      <Text type="secondary">
                        修复建议：{storyBibleQualityReport.repair_suggestions.join('；')}
                      </Text>
                    )}

                    {storyBibleQualityReport.warnings.length > 0 && (
                      <Alert
                        type="warning"
                        showIcon
                        message="修复/评估提示"
                        description={storyBibleQualityReport.warnings.join('；')}
                      />
                    )}
                  </Space>
                </Card>
              )}
            </Space>
          )}
        </Space>
      </Card>
    );
  };

  // 渲染对话界面
  const renderChat = () => {
    if (entrySteps.has(currentStep)) {
      return renderEntryStepPanel();
    }

    return (
      <>
      {renderDirectionCards()}
      {renderStoryBiblePanel()}

      <Card
        ref={chatContainerRef}
        style={{
          height: isMobile ? 'calc(100vh - 280px)' : 600,
          overflowY: 'auto',
          marginBottom: 16,
          boxShadow: `0 8px 24px color-mix(in srgb, ${token.colorTextBase} 20%, transparent)`,
          scrollBehavior: 'smooth'
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {messages.map((msg, index) => (
            <div
              key={index}
              style={{
                display: 'flex',
                justifyContent: msg.type === 'ai' ? 'flex-start' : 'flex-end',
                alignItems: 'flex-start',
                animation: 'fadeInUp 0.5s ease-out',
                animationFillMode: 'both',
                animationDelay: `${index * 0.1}s`
              }}
            >
              <div style={{
                maxWidth: '80%',
                padding: '12px 16px',
                borderRadius: 12,
                background: msg.type === 'ai' ? token.colorBgContainer : token.colorPrimary,
                color: msg.type === 'ai' ? token.colorText : token.colorWhite,
                boxShadow: msg.type === 'ai'
                  ? `0 2px 10px color-mix(in srgb, ${token.colorTextBase} 12%, transparent)`
                  : `0 4px 14px color-mix(in srgb, ${token.colorPrimary} 30%, transparent)`,
              }}>
                <Paragraph
                  style={{
                    margin: 0,
                    color: msg.type === 'ai' ? token.colorText : token.colorWhite,
                    whiteSpace: 'pre-wrap'
                  }}
                >
                  {msg.content}
                </Paragraph>

                {msg.options && msg.options.length > 0 && (
                  <Space
                    direction="vertical"
                    style={{ width: '100%', marginTop: 12 }}
                    size="small"
                  >
                    {msg.options.map((option, optIndex) => (
                      <Card
                        key={optIndex}
                        hoverable={!msg.optionsDisabled && !draftActionLoading}
                        size="small"
                        onClick={() => !msg.optionsDisabled && !draftActionLoading && handleSelectOption(option)}
                        style={{
                          cursor: msg.optionsDisabled || draftActionLoading ? 'not-allowed' : 'pointer',
                          border: `1px solid ${token.colorBorder}`,
                          background: msg.optionsDisabled
                            ? token.colorBgLayout
                            : token.colorBgContainer,
                          opacity: msg.optionsDisabled || draftActionLoading ? 0.6 : 1,
                          animation: 'floatIn 0.6s ease-out',
                          animationDelay: `${optIndex * 0.1}s`,
                          animationFillMode: 'both',
                          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                        }}
                        onMouseEnter={(e) => {
                          if (!msg.optionsDisabled && !draftActionLoading) {
                            e.currentTarget.style.transform = 'translateY(-2px) scale(1.02)';
                            e.currentTarget.style.boxShadow = `0 8px 22px color-mix(in srgb, ${token.colorTextBase} 14%, transparent)`;
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!msg.optionsDisabled && !draftActionLoading) {
                            e.currentTarget.style.transform = 'translateY(0) scale(1)';
                            e.currentTarget.style.boxShadow = 'none';
                          }
                        }}
                      >
                        {option}
                      </Card>
                    ))}
                  </Space>
                )}
              </div>
            </div>
          ))}

          {(loading || draftActionLoading) && (
            <div style={{
              textAlign: 'center',
              padding: 20,
              animation: 'fadeIn 0.3s ease-in'
            }}>
              <Spin tip={draftActionLoading ? "正在保存草稿..." : "AI思考中..."} />
            </div>
          )}

          <div ref={messagesEndRef} />
        </Space>
      </Card>

      <Card
        style={{ boxShadow: `0 4px 12px color-mix(in srgb, ${token.colorTextBase} 14%, transparent)` }}
        styles={{ body: { padding: 12 } }}
      >
        <Space.Compact style={{ width: '100%' }}>
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={
              currentStep === 'idea'
                ? '例如：我想写一本关于时间旅行的科幻小说...'
                : currentStep === 'direction_cards'
                  ? '请选择方向卡操作...'
                : '输入自定义内容，或点击上方选项卡片...'
            }
            autoSize={{ minRows: 2, maxRows: 4 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            disabled={loading || Boolean(draftActionLoading) || currentStep === 'direction_cards'}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSendMessage}
            loading={loading || Boolean(draftActionLoading)}
            disabled={currentStep === 'direction_cards'}
            style={{ height: 'auto' }}
          >
            发送
          </Button>
        </Space.Compact>
        <Text type="secondary" style={{ fontSize: 12, marginTop: 8, display: 'block' }}>
          💡 提示：按 Enter 发送，Shift+Enter 换行
        </Text>
      </Card>
      </>
    );
  };

  return (
    <div style={{
      minHeight: '100dvh',
      background: token.colorBgBase,
    }}>
      {contextHolder}
      <style>
        {`
          @keyframes fadeInUp {
            from {
              opacity: 0;
              transform: translateY(20px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }
          
          @keyframes floatIn {
            0% {
              opacity: 0;
              transform: translateY(10px) scale(0.95);
            }
            60% {
              transform: translateY(-5px) scale(1.02);
            }
            100% {
              opacity: 1;
              transform: translateY(0) scale(1);
            }
          }
          
          @keyframes fadeIn {
            from {
              opacity: 0;
            }
            to {
              opacity: 1;
            }
          }
        `}
      </style>

      {/* 顶部标题栏 - 固定不滚动 */}
      <div style={{
        position: 'sticky',
        top: 0,
        zIndex: 100,
        background: token.colorPrimary,
        boxShadow: `0 6px 20px color-mix(in srgb, ${token.colorPrimary} 30%, transparent)`,
      }}>
        <div style={{
          maxWidth: 1200,
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: isMobile ? '12px 16px' : '16px 24px',
        }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={handleBack}
            size={isMobile ? 'middle' : 'large'}
            style={{
              background: `color-mix(in srgb, ${token.colorWhite} 20%, transparent)`,
              borderColor: `color-mix(in srgb, ${token.colorWhite} 30%, transparent)`,
              color: token.colorWhite,
            }}
          >
            {isMobile ? '返回' : '返回首页'}
          </Button>

          <div style={{ textAlign: 'center' }}>
            <Title
              level={isMobile ? 4 : 2}
              style={{
                margin: 0,
                color: token.colorWhite,
                textShadow: '0 2px 4px color-mix(in srgb, var(--ant-color-black) 18%, transparent)',
                lineHeight: 1.2
              }}
            >
              ✨ 灵感模式
            </Title>
          </div>

          {/* 重新开始按钮 - 只在对话进行中显示 */}
          {currentStep !== 'channel_select' && currentStep !== 'idea' && currentStep !== 'generating' && currentStep !== 'complete' ? (
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                modal.confirm({
                  title: '确认重新开始',
                  content: '确定要重新开始吗？当前的对话进度将会丢失。',
                  okText: '确认',
                  cancelText: '取消',
                  centered: true,
                  okButtonProps: { danger: true },
                  onOk: () => {
                    handleRestart();
                  },
                });
              }}
              size={isMobile ? 'middle' : 'large'}
              style={{
                background: `color-mix(in srgb, ${token.colorWhite} 20%, transparent)`,
                borderColor: `color-mix(in srgb, ${token.colorWhite} 30%, transparent)`,
                color: token.colorWhite,
              }}
            >
              {isMobile ? '重新' : '重新开始'}
            </Button>
          ) : (
            <div style={{ width: isMobile ? 60 : 120 }}></div>
          )}
        </div>
      </div>

      <div style={{
        maxWidth: 800,
        margin: '0 auto',
        padding: isMobile ? '16px 12px' : '24px 24px',
      }}>
        {restorableSteps.has(currentStep) && renderChat()}
        {(currentStep === 'generating' || currentStep === 'complete') && generationConfig && (
          <AIProjectGenerator
            config={generationConfig}
            storagePrefix="inspiration"
            onComplete={handleComplete}
            onBack={handleBackToChat}
            isMobile={isMobile}
          />
        )}
      </div>
    </div>
  );
};

const Inspiration = InspirationImpl as InspirationComponent;

Inspiration.__testUtils = {
  INSPIRATION_DRAFTS_KEY,
  buildProjectDraftPayload,
  buildProjectEntryPath,
  normalizeWizardData,
  runInspirationDraftAction,
  saveInspirationDraftToStorage,
};

export default Inspiration;
