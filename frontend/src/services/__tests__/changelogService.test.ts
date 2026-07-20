import { beforeEach, describe, expect, it, vi } from 'vitest'

import api from '../api'
import {
  convertCommitsToChangelog,
  fetchGitHubCommits,
  isChangelogConfigured,
} from '../changelogService'

vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
  },
}))

const mockedApiGet = vi.mocked(api.get)

describe('changelog backend API adapter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads commits through the configured backend API', async () => {
    mockedApiGet.mockResolvedValue({
      commits: [],
      cached: true,
      cache_time: null,
    })

    await expect(fetchGitHubCommits(2, 7)).resolves.toEqual([])
    expect(mockedApiGet).toHaveBeenCalledWith('/changelog', {
      params: { page: 2, per_page: 7 },
    })
  })

  it('rejects malformed backend responses instead of showing a false empty log', async () => {
    mockedApiGet.mockResolvedValue({ cached: false })

    await expect(fetchGitHubCommits()).rejects.toThrow('更新日志响应格式无效')
  })

  it('preserves commit conversion for the backend response shape', () => {
    const entries = convertCommitsToChangelog([{
      sha: 'abc123',
      commit: {
        author: {
          name: 'Author',
          email: 'author@example.test',
          date: '2026-07-20T12:00:00Z',
        },
        message: 'fix(settings): normalize legacy defaults',
      },
      html_url: 'https://github.com/example/repo/commit/abc123',
      author: {
        login: 'author',
        avatar_url: 'https://example.test/avatar.png',
      },
    }])

    expect(entries[0]).toMatchObject({
      id: 'abc123',
      type: 'fix',
      scope: 'settings',
      message: 'normalize legacy defaults',
    })
  })

  it('exposes repository metadata availability for the floating control', () => {
    expect(typeof isChangelogConfigured()).toBe('boolean')
  })
})
