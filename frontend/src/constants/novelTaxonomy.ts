export interface TagOption {
  id: string;
  label: string;
}

export interface GenreOption extends TagOption {}

export interface ChannelOption {
  id: string;
  label: string;
  genres: GenreOption[];
}

export type Channel = ChannelOption;

export const MAX_TAGS_PER_DIMENSION = 5;

function createTagOption(prefix: 'theme' | 'char' | 'plot', label: string): TagOption {
  return {
    id: `${prefix}_${label}`,
    label,
  };
}

function createGenreOptions(channelId: string, labels: readonly string[]): GenreOption[] {
  return labels.map(label => ({
    id: `genre_${channelId}_${label}`,
    label,
  }));
}

const NAN_GENRE_LABELS = [
  '玄幻',
  '奇幻',
  '武侠',
  '仙侠',
  '都市',
  '军事',
  '历史',
  '游戏',
  '体育',
  '科幻',
  '诸天无限',
  '悬疑',
] as const;

const NV_GENRE_LABELS = [
  '古代言情',
  '仙侠奇缘',
  '现代言情',
  '浪漫青春',
  '玄幻言情',
  '悬疑推理',
  '科幻空间',
  '游戏竞技',
  '短篇',
  '轻小说',
] as const;

const ECY_GENRE_LABELS = [
  '原生幻想',
  '恋爱日常',
  '衍生同人',
  '搞笑吐槽',
] as const;

export const CHANNELS: Channel[] = [
  {
    id: 'nan',
    label: '男频',
    genres: createGenreOptions('nan', NAN_GENRE_LABELS),
  },
  {
    id: 'nv',
    label: '女频',
    genres: createGenreOptions('nv', NV_GENRE_LABELS),
  },
  {
    id: 'erciyuan',
    label: '二次元',
    genres: createGenreOptions('erciyuan', ECY_GENRE_LABELS),
  },
];

const THEME_LABELS = [
  '历史脑洞',
  '都市种田',
  '都市异能',
  '综影视',
  '都市日常',
  '都市高武',
  '历史古代',
  '都市生活',
  '末日求生',
  '灵气复苏',
  '东方仙侠',
  '西方奇幻',
  '悬疑灵异',
  '轻小说',
  '玄幻脑洞',
  '古代',
  '体育',
  '东方玄幻',
  '男频衍生',
  '高武世界',
  '游戏动漫',
  '影视小说',
  '武侠',
  '架空',
  '规则怪谈',
  '异能',
  '综漫',
  '天灾',
  '宝可梦',
  '悬疑脑洞',
  '开局',
  '宋朝',
  '异世大陆',
  '清朝',
  '搞笑轻松',
  '谍战',
  '克苏鲁',
  '赛博朋克',
  '第四天灾',
  '断层',
  '武将',
  '第一人称',
] as const;

const CHARACTER_LABELS = [
  '多女主',
  '单女主',
  '皇帝',
  '天才',
  '学霸',
  '群像',
  '无女主',
  '大佬',
  '神医',
  '奶爸',
  '反派',
  '特种兵',
  '校花',
  '大小姐',
  '游戏主播',
  '宫廷侯爵',
  '扮猪吃虎',
  '神探',
  '全能',
  '赘婿',
  '特工',
  '战神赘婿',
  '女帝',
  '腹黑',
] as const;

const PLOT_LABELS = [
  '漫威',
  '诸天万界',
  '都市修真',
  '无脑爽',
  '大唐',
  '基建',
  '求生',
  '无限流',
  '三国',
  '职场',
  '修仙',
  '海岛',
  '乡村',
  '直播',
  '废土',
  '动漫衍生',
  '穿越',
  '重生',
  '美食',
  '争霸',
  '盗墓',
  '网游',
  '灵异',
  '明朝',
  '穿书',
  '二次元',
  '九叔',
  '科举',
  '风水秘术',
  '电竞',
  '仙侠',
  '星际',
  '空间',
  '破案',
  '火影',
  '奥特同人',
  '红楼衍生',
  '捉鬼',
  '西游衍生',
  '鉴宝',
  '打脸',
  '囤物资',
  '黑道',
  '家庭',
  '升级流',
  '推理',
  '海贼王',
  '外卖',
  '传统玄幻',
  '封神',
  '神奇宝贝',
  '惊悚游戏',
  '奇幻',
  '大秦',
  '海贼',
  '聊天群',
  '剑道',
  '副本',
  '龙珠',
  '卡牌',
  '都市江湖',
  '剑修',
  '无后宫',
  '斩神衍生',
  '钓鱼',
  '黑化',
  '甄嬛衍生',
  '宠物',
  '双系统',
  '1v1',
  '公版衍生',
  '迪化',
  '斩神',
  '双重生',
  '十日衍生',
  '高手下山',
  '山海经',
  '魂穿',
  '灵魂互换',
  '绝地逃生',
  '如懿衍生',
] as const;

export const THEME_TAGS: TagOption[] = THEME_LABELS.map(label => createTagOption('theme', label));
export const CHARACTER_TAGS: TagOption[] = CHARACTER_LABELS.map(label => createTagOption('char', label));
export const PLOT_TAGS: TagOption[] = PLOT_LABELS.map(label => createTagOption('plot', label));

export function getGenresByChannel(channelId: string): GenreOption[] {
  const channel = CHANNELS.find(item => item.id === channelId);
  return channel ? [...channel.genres] : [];
}
