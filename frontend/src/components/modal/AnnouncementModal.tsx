import { BulbOutlined, CheckCircleOutlined, FileTextOutlined } from '@ant-design/icons';
import { Button, List, Modal, Space, Typography } from 'antd';

const { Paragraph, Text } = Typography;

interface AnnouncementModalProps {
  visible: boolean;
  onClose: () => void;
  onDoNotShowToday: () => void;
  onNeverShow: () => void;
}

const onboardingTips = [
  { icon: <BulbOutlined />, title: '从灵感开始', description: '先整理题材、主角和核心冲突，再进入项目创建。' },
  { icon: <FileTextOutlined />, title: '逐步完善设定', description: '使用世界设定、角色和大纲工具保持故事一致。' },
  { icon: <CheckCircleOutlined />, title: '保留创作控制权', description: 'AI 生成内容均可编辑、审核和重新生成。' },
];

export default function AnnouncementModal({ visible, onClose, onDoNotShowToday, onNeverShow }: AnnouncementModalProps) {
  const handleDoNotShowToday = () => {
    onDoNotShowToday();
    onClose();
  };

  const handleNeverShow = () => {
    onNeverShow();
    onClose();
  };

  return (
    <Modal
      title="欢迎使用 AI Novel Studio"
      open={visible}
      onCancel={onClose}
      footer={
        <Space>
          <Button onClick={handleDoNotShowToday}>今日内不再展示</Button>
          <Button type="primary" onClick={handleNeverShow}>不再展示</Button>
        </Space>
      }
      width={560}
      centered
    >
      <Paragraph type="secondary">用结构化流程把灵感推进为可持续创作的小说项目。</Paragraph>
      <List
        dataSource={onboardingTips}
        renderItem={(item) => (
          <List.Item>
            <List.Item.Meta
              avatar={item.icon}
              title={<Text strong>{item.title}</Text>}
              description={item.description}
            />
          </List.Item>
        )}
      />
    </Modal>
  );
}
