import { useCallback, useEffect, useRef, useState } from 'react';
import { Badge, Button, Card, Checkbox, Empty, List, Modal, Popconfirm, Space, Tag, Typography, message } from 'antd';
import { CheckOutlined, CloseOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { extractionApi } from '../../services/api';
import { getProjectTasks } from '../../services/backgroundTaskService';
import type { ExtractionCandidate, ExtractionCandidateType } from '../../types';

const { Paragraph, Text } = Typography;

const TYPE_LABELS: Record<ExtractionCandidateType, string> = {
  character: '角色',
  organization: '组织',
  profession: '职业',
  relationship: '关系',
  goldfinger: '金手指',
  organization_affiliation: '组织归属',
  profession_assignment: '职业变更',
  world_fact: '世界事实',
  character_state: '角色状态',
};

interface ChapterExtractionReviewPanelProps {
  projectId: string;
}

export default function ChapterExtractionReviewPanel({ projectId }: ChapterExtractionReviewPanelProps) {
  const [visible, setVisible] = useState(false);
  const [candidates, setCandidates] = useState<ExtractionCandidate[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const notifiedTaskIds = useRef(new Set<string>());
  const taskBaselineProjectId = useRef<string | null>(null);

  const loadCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const response = await extractionApi.listCandidates({ project_id: projectId, status: 'pending', limit: 500 });
      setCandidates(response.items);
      setSelectedIds(previous => previous.filter(id => response.items.some(candidate => candidate.id === id)));
    } catch (error) {
      console.error('加载实体提取候选失败:', error);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const pollExtractionTasks = useCallback(async () => {
    try {
      const response = await getProjectTasks(projectId, 'chapter_entity_extraction', 10);
      if (taskBaselineProjectId.current !== projectId) {
        taskBaselineProjectId.current = projectId;
        notifiedTaskIds.current.clear();
        for (const task of response.items) {
          if (task.status === 'completed' || task.status === 'failed') {
            notifiedTaskIds.current.add(task.id);
          }
        }
        return;
      }
      for (const task of response.items) {
        if (notifiedTaskIds.current.has(task.id)) continue;
        if (task.status === 'completed') {
          notifiedTaskIds.current.add(task.id);
          message.success(task.status_message || '章节实体提取已完成');
          await loadCandidates();
        } else if (task.status === 'failed') {
          notifiedTaskIds.current.add(task.id);
          message.error(task.status_message || '章节实体提取失败');
        }
      }
    } catch (error) {
      console.error('轮询实体提取任务失败:', error);
    }
  }, [loadCandidates, projectId]);

  useEffect(() => {
    void loadCandidates();
    void pollExtractionTasks();
    const timer = window.setInterval(() => void pollExtractionTasks(), 5000);
    return () => window.clearInterval(timer);
  }, [loadCandidates, pollExtractionTasks]);

  const review = async (action: 'accept' | 'reject', ids: string[]) => {
    if (ids.length === 0) {
      message.warning('请先选择待审核候选');
      return;
    }
    setReviewing(true);
    try {
      const response = action === 'accept'
        ? await extractionApi.batchAcceptCandidates(ids)
        : await extractionApi.batchRejectCandidates(ids, '在章节实体审核面板批量拒绝');
      if (response.changed > 0) {
        message.success(`${action === 'accept' ? '已接受' : '已拒绝'} ${response.changed} 条候选`);
      }
      if (response.failures.length > 0) {
        message.warning(`${response.failures.length} 条候选需要逐项处理`);
      }
      await loadCandidates();
    } catch (error) {
      console.error('批量审核实体候选失败:', error);
      message.error('审核失败，请重试');
    } finally {
      setReviewing(false);
    }
  };

  const toggleCandidate = (candidateId: string, checked: boolean) => {
    setSelectedIds(previous => checked
      ? Array.from(new Set([...previous, candidateId]))
      : previous.filter(id => id !== candidateId));
  };

  return (
    <>
      <Badge count={candidates.length} overflowCount={99}>
        <Button icon={<RobotOutlined />} onClick={() => setVisible(true)}>
          实体提取审核
        </Button>
      </Badge>
      <Modal
        title="章节实体提取审核"
        open={visible}
        width={900}
        centered
        onCancel={() => setVisible(false)}
        footer={(
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void loadCandidates()} loading={loading}>刷新</Button>
            <Button onClick={() => setSelectedIds(candidates.map(candidate => candidate.id))}>全选</Button>
            <Button danger icon={<CloseOutlined />} loading={reviewing} onClick={() => void review('reject', selectedIds)}>拒绝所选</Button>
            <Popconfirm title="接受所选候选并写入规范实体/关系？" onConfirm={() => void review('accept', selectedIds)}>
              <Button type="primary" icon={<CheckOutlined />} loading={reviewing}>接受所选</Button>
            </Popconfirm>
          </Space>
        )}
      >
        {candidates.length === 0 && !loading ? (
          <Empty description="暂无待审核实体；章节标记完成后会自动提取" />
        ) : (
          <List
            loading={loading}
            dataSource={candidates}
            renderItem={candidate => (
              <List.Item
                actions={[
                  <Button key="accept" type="link" onClick={() => void review('accept', [candidate.id])}>接受</Button>,
                  <Button key="reject" type="link" danger onClick={() => void review('reject', [candidate.id])}>拒绝</Button>,
                ]}
              >
                <List.Item.Meta
                  avatar={<Checkbox checked={selectedIds.includes(candidate.id)} onChange={event => toggleCandidate(candidate.id, event.target.checked)} />}
                  title={(
                    <Space wrap>
                      <Text strong>{candidate.display_name || '未命名候选'}</Text>
                      <Tag>{TYPE_LABELS[candidate.candidate_type]}</Tag>
                      <Tag color={candidate.confidence >= 0.92 ? 'green' : candidate.confidence >= 0.8 ? 'blue' : 'orange'}>
                        置信度 {Math.round(candidate.confidence * 100)}%
                      </Tag>
                      {candidate.canonical_target_id && <Tag color="purple">建议合并已有实体</Tag>}
                    </Space>
                  )}
                  description={(
                    <Card size="small">
                      <Paragraph className="u-ohn8hu">{candidate.evidence_text}</Paragraph>
                      {candidate.review_required_reason && <Text type="secondary">匹配说明：{candidate.review_required_reason}</Text>}
                    </Card>
                  )}
                />
              </List.Item>
            )}
          />
        )}
      </Modal>
    </>
  );
}
