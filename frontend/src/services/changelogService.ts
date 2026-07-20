/**
 * 更新日志服务
 * 通过应用后端 API 获取配置的仓库提交历史并转换为更新日志
 */
import api from './api';

export interface GitHubCommit {
  sha: string;
  commit: {
    author: {
      name: string;
      email: string;
      date: string;
    };
    message: string;
  };
  html_url: string;
  author: {
    login: string;
    avatar_url: string;
  } | null;
}

export interface ChangelogEntry {
  id: string;
  date: string;
  version?: string;
  author: {
    name: string;
    avatar?: string;
    username?: string;
  };
  message: string;
  commitUrl: string;
  type: 'feature' | 'fix' | 'docs' | 'style' | 'refactor' | 'perf' | 'test' | 'chore' | 'update' | 'other';
  scope?: string;
}

const REPOSITORY_SLUG = (import.meta.env.VITE_REPOSITORY_SLUG || '').trim();
const [REPO_OWNER = '', REPO_NAME = '', ...REPOSITORY_EXTRA_PARTS] = REPOSITORY_SLUG.split('/');

export const isChangelogConfigured = (): boolean => Boolean(
  REPO_OWNER && REPO_NAME && REPOSITORY_EXTRA_PARTS.length === 0,
);

interface ChangelogApiResponse {
  commits: GitHubCommit[];
  cached: boolean;
  cache_time?: string | null;
}
/**
 * 提交类型映射表
 * 统一不同别名到标准类型
 */
const TYPE_MAPPING: Record<string, ChangelogEntry['type']> = {
  // 功能类
  'feat': 'feature',
  'feature': 'feature',
  'update': 'update',
  
  // 修复类
  'fix': 'fix',
  
  // 文档类
  'docs': 'docs',
  'doc': 'docs',
  
  // 样式类
  'style': 'style',
  
  // 重构类
  'refactor': 'refactor',
  
  // 性能类
  'perf': 'perf',
  
  // 测试类
  'test': 'test',
  
  // 杂项类
  'chore': 'chore',
};

/**
 * 从提交信息中解析类型和作用域
 *
 * 匹配优先级（从高到低）：
 * 1. 标准 Conventional Commits 格式: type(scope): message 或 type: message
 * 2. 方括号格式: [type] message
 * 3. 简单前缀格式: type: message（支持中文冒号）
 * 4. 关键词模糊匹配（中英文）
 */
function parseCommitType(message: string): { type: ChangelogEntry['type']; scope?: string; cleanMessage: string } {
  const lowerMessage = message.toLowerCase().trim();
  
  // 优先级1：标准 Conventional Commits 格式 - type(scope): message 或 type: message
  // 匹配所有支持的类型
  const conventionalPattern = new RegExp(
    `^(${Object.keys(TYPE_MAPPING).join('|')})(?:\\(([^)]+)\\))?\\s*[:\\:：]\\s*(.+)`,
    'i'
  );
  const conventionalMatch = message.match(conventionalPattern);
  if (conventionalMatch) {
    const typeStr = conventionalMatch[1].toLowerCase();
    const mappedType = TYPE_MAPPING[typeStr] || 'other';
    return {
      type: mappedType,
      scope: conventionalMatch[2],
      cleanMessage: conventionalMatch[3].trim(),
    };
  }

  // 优先级2：方括号格式 - [type] message
  const bracketPattern = new RegExp(
    `^\\[(${Object.keys(TYPE_MAPPING).join('|')})\\]\\s*(.+)`,
    'i'
  );
  const bracketMatch = message.match(bracketPattern);
  if (bracketMatch) {
    const typeStr = bracketMatch[1].toLowerCase();
    const mappedType = TYPE_MAPPING[typeStr] || 'other';
    return {
      type: mappedType,
      cleanMessage: bracketMatch[2].trim(),
    };
  }

  // 优先级3：简单前缀格式 - type: message（支持英文和中文冒号）
  for (const [key, value] of Object.entries(TYPE_MAPPING)) {
    const prefixPattern = new RegExp(`^${key}\\s*[:\\:：]\\s*`, 'i');
    if (prefixPattern.test(lowerMessage)) {
      const cleanMsg = message.replace(prefixPattern, '').trim();
      return { type: value, cleanMessage: cleanMsg };
    }
  }

  // 优先级4：关键词模糊匹配（仅当前面都不匹配时）
  const keywordMap: Array<{ keywords: string[]; type: ChangelogEntry['type'] }> = [
    { keywords: ['修复', 'fix'], type: 'fix' },
    { keywords: ['优化', 'perf'], type: 'perf' },
    { keywords: ['文档', 'document'], type: 'docs' },
    { keywords: ['新增', '添加', '增加', 'add'], type: 'feature' },
    { keywords: ['更新', 'update'], type: 'update' },
    { keywords: ['样式', 'style'], type: 'style' },
    { keywords: ['重构', 'refactor'], type: 'refactor' },
    { keywords: ['测试', 'test'], type: 'test' },
  ];

  for (const { keywords, type } of keywordMap) {
    if (keywords.some(keyword => lowerMessage.includes(keyword))) {
      return { type, cleanMessage: message };
    }
  }

  // 默认类型
  return { type: 'other', cleanMessage: message };
}

/**
 * 通过应用后端获取配置仓库的提交历史
 */
export async function fetchGitHubCommits(page: number = 1, perPage: number = 30): Promise<GitHubCommit[]> {
  try {
    const response = await api.get<unknown, ChangelogApiResponse>('/changelog', {
      params: { page, per_page: perPage },
    });
    if (!response || !Array.isArray(response.commits)) {
      throw new Error('更新日志响应格式无效');
    }
    return response.commits;
  } catch (error) {
    console.error('获取更新日志失败:', error);
    throw error;
  }
}

/**
 * 将GitHub提交转换为更新日志条目
 */
export function convertCommitsToChangelog(commits: GitHubCommit[]): ChangelogEntry[] {
  return commits.map(commit => {
    const { type, scope, cleanMessage } = parseCommitType(commit.commit.message);
    
    return {
      id: commit.sha,
      date: commit.commit.author.date,
      author: {
        name: commit.commit.author.name,
        avatar: commit.author?.avatar_url,
        username: commit.author?.login,
      },
      message: cleanMessage,
      commitUrl: commit.html_url,
      type,
      scope,
    };
  });
}

/**
 * 获取格式化的更新日志
 */
export async function fetchChangelog(page: number = 1, perPage: number = 30): Promise<ChangelogEntry[]> {
  const commits = await fetchGitHubCommits(page, perPage);
  return convertCommitsToChangelog(commits);
}

/**
 * 按日期分组更新日志
 */
export function groupChangelogByDate(entries: ChangelogEntry[]): Map<string, ChangelogEntry[]> {
  const grouped = new Map<string, ChangelogEntry[]>();
  
  entries.forEach(entry => {
    const date = new Date(entry.date).toISOString().split('T')[0];
    const existing = grouped.get(date) || [];
    existing.push(entry);
    grouped.set(date, existing);
  });
  
  return grouped;
}

/**
 * 检查是否应该获取更新日志（避免频繁请求）
 */
export function shouldFetchChangelog(): boolean {
  const lastFetch = localStorage.getItem('changelog_last_fetch');
  
  if (!lastFetch) {
    return true;
  }
  
  const lastFetchTime = new Date(lastFetch).getTime();
  const now = Date.now();
  const oneHourMs = 60 * 60 * 1000; // 1小时
  
  return now - lastFetchTime >= oneHourMs;
}

/**
 * 记录更新日志获取时间
 */
export function markChangelogFetched(): void {
  localStorage.setItem('changelog_last_fetch', new Date().toISOString());
}

/**
 * 获取缓存的更新日志
 */
export function getCachedChangelog(): ChangelogEntry[] | null {
  const cached = localStorage.getItem('changelog_cache');
  if (cached) {
    try {
      return JSON.parse(cached);
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * 缓存更新日志
 */
export function cacheChangelog(entries: ChangelogEntry[]): void {
  localStorage.setItem('changelog_cache', JSON.stringify(entries));
}

/**
 * 清除更新日志缓存
 * 用于强制刷新数据
 */
export function clearChangelogCache(): void {
  localStorage.removeItem('changelog_cache');
  localStorage.removeItem('changelog_last_fetch');
}