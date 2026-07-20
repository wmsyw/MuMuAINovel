import React, { useState, useEffect, useRef } from 'react';
import { Card, Input, Button, Tag, List, Typography, Space, Spin, message, Tooltip, Tabs, theme } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, ThunderboltOutlined } from '@ant-design/icons';
import axios from 'axios';
import { sx } from '../styles/sx';
// 使用简单的文本渲染替代 react-markdown
const MarkdownRender: React.FC<{ content: string }> = ({ content }) => {
  return <div className="u-f7yezs">{content}</div>;
};

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

interface Skill {
  template_key: string;
  template_name: string;
  category: string;
  description: string;
  triggers: string[];
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface SkillChatStreamEvent {
  type?: 'chunk' | 'error';
  content?: string;
  error?: string;
}

const SkillChat: React.FC = () => {
  const { token } = theme.useToken();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [skillsLoading, setSkillsLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchSkills();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const fetchSkills = async () => {
    try {
      const response = await axios.get('/api/skills/list');
      setSkills(response.data);
      if (response.data.length > 0) {
        setActiveCategory((prev) => prev || response.data[0].category);
      }
    } catch {
      message.error('加载 Skill 列表失败');
    } finally {
      setSkillsLoading(false);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSkillSelect = (skill: Skill) => {
    setSelectedSkill(skill);
    setMessages([]);
  };

  const handleSend = async () => {
    if (!inputValue.trim() || !selectedSkill || loading) return;

    const userMessage = inputValue.trim();
    setInputValue('');
    const newMessages: ChatMessage[] = [...messages, { role: 'user', content: userMessage }];
    setMessages(newMessages);
    setLoading(true);

    // 添加空的助手消息占位
    const assistantMsg: ChatMessage = { role: 'assistant', content: '' };
    setMessages([...newMessages, assistantMsg]);

    try {
      abortControllerRef.current = new AbortController();
      const response = await fetch('/api/skills/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_key: selectedSkill.template_key,
          message: userMessage,
          history: messages.map(m => ({ role: m.role, content: m.content })),
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) throw new Error('请求失败');

      const reader = response.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');

      const decoder = new TextDecoder();
      let accumulated = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        const lines = text.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data: SkillChatStreamEvent = JSON.parse(line.slice(6));
              if (data.type === 'chunk') {
                accumulated += data.content ?? '';
                setMessages(prev => {
                  const updated = [...prev];
                  updated[updated.length - 1] = { role: 'assistant', content: accumulated };
                  return updated;
                });
              } else if (data.type === 'error') {
                message.error(data.error || '生成失败');
              }
            } catch (parseError) {
              if (parseError instanceof SyntaxError) {
                if (import.meta.env.DEV) {
                  console.debug('忽略无法解析的 Skill 流数据:', parseError);
                }
              } else {
                throw parseError;
              }
            }
          }
        }
      }
    } catch (error: unknown) {
      const isAbortError =
        (error instanceof DOMException || error instanceof Error) && error.name === 'AbortError';
      if (!isAbortError) {
        message.error('请求失败，请检查 AI 配置');
        setMessages(prev => {
          const updated = [...prev];
          if (updated.length > 0 && updated[updated.length - 1].role === 'assistant' && !updated[updated.length - 1].content) {
            updated.pop();
          }
          return updated;
        });
      }
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  };

  // 按 category 分组
  const groupedSkills = skills.reduce<Record<string, Skill[]>>((acc, skill) => {
    const cat = skill.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(skill);
    return acc;
  }, {});
  const categories = Object.keys(groupedSkills);
  const currentCategory = activeCategory && groupedSkills[activeCategory] ? activeCategory : categories[0];
  const currentSkills = currentCategory ? groupedSkills[currentCategory] : [];

  const categoryColors: Record<string, string> = {
    'Skill·长篇': token.colorPrimary,
    'Skill·短篇': token.colorSuccess,
    'Skill·润色': token.colorWarning,
    'Skill·工具': token.colorInfo,
  };

  if (selectedSkill) {
    return (
      <div className="u-94b7qf">
        {/* 顶部栏 */}
        <div className="u-1ahdsyw">
          <Button size="small" onClick={() => { setSelectedSkill(null); setMessages([]); }}>← 返回</Button>
          <ThunderboltOutlined className="u-rvm8v6" />
          <Text strong>{selectedSkill.template_name}</Text>
          <Tag color={categoryColors[selectedSkill.category] || 'default'} className="u-54p264">{selectedSkill.category}</Tag>
          <Tooltip title={selectedSkill.description} placement="bottom">
            <Text
              type="secondary"
              className="u-2wro1e"
              ellipsis
            >
              {selectedSkill.description}
            </Text>
          </Tooltip>
        </div>

        {/* 消息区域 */}
        <div className="u-1j1a641">
          {messages.length === 0 && (
            <div className="u-4damkg">
              <RobotOutlined className="u-snh6ye" />
              <div className="u-1mpy5og">{'已选择「'}{selectedSkill.template_name}{'」'}</div>
              <div>输入你的需求开始对话，或直接使用触发词：{selectedSkill.triggers.join('、')}</div>
            </div>
          )}
          {messages.map((msg, idx) => (
            <div key={idx} className={sx({
              display: 'flex', gap: 12, marginBottom: 16,
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
            })}>
              <div className={sx({
                width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: msg.role === 'user' ? token.colorPrimary : token.colorFillSecondary,
                color: msg.role === 'user' ? token.colorWhite : token.colorText,
                flexShrink: 0,
              })}>
                {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
              </div>
              <div className={sx({
                maxWidth: '75%', padding: '10px 16px', borderRadius: 12,
                background: msg.role === 'user' ? token.colorPrimary : token.colorFillTertiary,
                color: msg.role === 'user' ? token.colorWhite : token.colorText,
              })}>
                {msg.role === 'assistant' ? (
                  <div  className={sx("markdown-body", 'u-im08ra')}>
                    <MarkdownRender content={msg.content || '...'} />
                  </div>
                ) : (
                  <div className="u-k2miy8">{msg.content}</div>
                )}
              </div>
            </div>
          ))}
          {loading && messages[messages.length - 1]?.content === '' && (
            <div className="u-n916u2"><Spin size="small" /> 思考中...</div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="u-1eoh3pc">
          <TextArea
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="输入你的需求..."
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={loading}
          />
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading} />
        </div>
      </div>
    );
  }

  const renderSkillList = (items: Skill[]) => (
    <List
      grid={{ gutter: 16, xs: 1, sm: 2, md: 3, lg: 4, xl: 4, xxl: 4 }}
      dataSource={items}
      renderItem={(skill) => (
        <List.Item className="u-6srbul">
          <Card
            hoverable
            onClick={() => handleSkillSelect(skill)}
            styles={{ body: { height: '100%', padding: 16 } }}
            className={sx({
              cursor: 'pointer',
              height: '100%',
              aspectRatio: '4 / 3',
              minHeight: 210,
              maxHeight: 260,
              borderRadius: 14,
              overflow: 'hidden',
              border: `1px solid ${token.colorBorderSecondary}`,
              boxShadow: token.boxShadowTertiary,
            })}
          >
            <div className="u-1c8mex0">
              <div className="u-8a87fq">
                <div
                  className={sx({
                    width: 40,
                    height: 40,
                    borderRadius: 12,
                    flexShrink: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#fff',
                    background: `linear-gradient(135deg, ${categoryColors[skill.category] || '#1890ff'}, #8ec5ff)`,
                    boxShadow: '0 6px 14px rgba(24, 144, 255, 0.22)',
                  })}
                >
                  <ThunderboltOutlined />
                </div>
                <div className="u-niv4z9">
                  <Tooltip title={skill.template_name}>
                    <Text
                      strong
                      className="u-1v16fyq"
                    >
                      {skill.template_name}
                    </Text>
                  </Tooltip>
                  <Tag
                    color={categoryColors[skill.category] || '#default'}
                    className="u-153shb9"
                  >
                    {skill.category}
                  </Tag>
                </div>
              </div>

              <Tooltip title={skill.description} placement="bottom">
                <Paragraph
                  type="secondary"
                  ellipsis={{ rows: 3 }}
                  className="u-f9on9i"
                >
                  {skill.description}
                </Paragraph>
              </Tooltip>

              <div
                className={sx({
                  minHeight: 30,
                  paddingTop: 10,
                  borderTop: `1px solid ${token.colorBorderSecondary}`,
                  overflow: 'hidden',
                })}
              >
                <Space size={[4, 4]} wrap>
                  {skill.triggers.slice(0, 3).map(t => (
                    <Tooltip key={t} title={t}>
                      <Tag
                        className="u-1fqqxbd"
                      >
                        {t}
                      </Tag>
                    </Tooltip>
                  ))}
                  {skill.triggers.length > 3 && (
                    <Tooltip title={skill.triggers.slice(3).join('、')}>
                      <Tag className="u-1kcop03">+{skill.triggers.length - 3}</Tag>
                    </Tooltip>
                  )}
                </Space>
              </div>
            </div>
          </Card>
        </List.Item>
      )}
    />
  );

  // Skill 选择页
  return (
    <div className="u-1u82j5m">
      <div className="u-1sxdsld">
        <Title level={4} className="u-1jeouum"><ThunderboltOutlined /> Skill 工具箱</Title>
        <Paragraph type="secondary" className="u-1sezbee">选择一个 Skill 开始创作对话。每个 Skill 都有专业的写作工作流和知识库。</Paragraph>
      </div>

      {skillsLoading ? (
        <div className="u-128xsrr">
          <Spin />
        </div>
      ) : (
        <>
          <Tabs
            activeKey={currentCategory}
            onChange={setActiveCategory}
            items={categories.map((category) => ({
              key: category,
              label: (
                <span>
                  <Tag color={categoryColors[category] || '#default'}>{category}</Tag>
                  {groupedSkills[category].length} 个 Skill
                </span>
              ),
            }))}
            className="u-gbeb7n"
            tabBarStyle={{ marginBottom: 16 }}
          />

          <div
            className="u-182b3xy"
          >
            {renderSkillList(currentSkills)}
          </div>
        </>
      )}
    </div>
  );
};

export default SkillChat;
