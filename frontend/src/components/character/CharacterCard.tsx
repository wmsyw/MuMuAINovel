import { Card, Space, Tag, Typography, Popconfirm, theme } from 'antd';
import { EditOutlined, DeleteOutlined, UserOutlined, BankOutlined, ExportOutlined } from '@ant-design/icons';
import { characterCardStyles } from '../common/CardStyles';
import type { Character } from '../../types';
import { getOrganizationPurpose, getOrganizationType, isOrganizationEntity } from '../../utils/entityCompatibility';
import { sx } from '../../styles/sx';

const { Text, Paragraph } = Typography;

interface CharacterCardProps {
  character: Character;
  onEdit?: (character: Character) => void;
  onDelete: (id: string) => void;
  onExport?: () => void;
}

export const CharacterCard: React.FC<CharacterCardProps> = ({ character, onEdit, onDelete, onExport }) => {
  const { token } = theme.useToken();

  const getRoleTypeColor = (roleType?: string) => {
    const roleColors: Record<string, string> = {
      'protagonist': 'blue',
      'heroine': 'magenta',
      'supporting': 'green',
      'antagonist': 'red',
    };
    return roleColors[roleType || ''] || 'default';
  };

  const getRoleTypeLabel = (roleType?: string) => {
    const roleLabels: Record<string, string> = {
      'protagonist': '男主/主角',
      'heroine': '女主',
      'supporting': '配角',
      'antagonist': '反派',
    };
    return roleLabels[roleType || ''] || '其他';
  };

  const isOrganization = isOrganizationEntity(character);
  const organizationType = getOrganizationType(character);
  const organizationPurpose = getOrganizationPurpose(character);
  const charStatus = character.status || 'active';
  const isInactive = charStatus !== 'active';
  const writingFields = [
    { label: '写作备注', value: character.writing_notes },
    { label: '说话习惯', value: character.speech_patterns },
    { label: '核心动机', value: character.motivations },
    { label: '人物弧光', value: character.arc_summary },
  ].filter((item) => item.value);

  const getStatusTag = () => {
    const statusConfig: Record<string, { color: string; label: string }> = {
      deceased: { color: token.colorTextBase, label: '💀 已死亡' },
      missing: { color: token.colorWarning, label: '❓ 已失踪' },
      retired: { color: token.colorTextTertiary, label: '📤 已退场' },
      destroyed: { color: token.colorTextBase, label: '💀 已覆灭' },
    };
    const config = statusConfig[charStatus];
    if (!config) return null;
    return <Tag color={config.color} className="u-54p264">{config.label}</Tag>;
  };

  return (
    <Card
      hoverable
      className={sx({
        ...(isOrganization ? characterCardStyles.organizationCard : characterCardStyles.characterCard),
        ...(isInactive ? { opacity: 0.6, filter: 'grayscale(40%)' } : {}),
      })}
      styles={{
        body: {
          flex: 1,
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column'
        },
        actions: {
          borderRadius: '0 0 12px 12px'
        }
      }}
      actions={[
        ...(onEdit ? [<EditOutlined key="edit" onClick={() => onEdit(character)} />] : []),
        ...(onExport ? [<ExportOutlined key="export" onClick={onExport} />] : []),
        <Popconfirm
          key="delete"
          title={`确定删除这个${isOrganization ? '组织' : '角色'}吗？`}
          onConfirm={() => onDelete(character.id)}
          okText="确定"
          cancelText="取消"
        >
          <DeleteOutlined />
        </Popconfirm>,
      ]}
    >
      <Card.Meta
        avatar={
          isOrganization ? (
            <BankOutlined className={sx({ fontSize: 32, color: token.colorSuccess })} />
          ) : (
            <UserOutlined className={sx({ fontSize: 32, color: token.colorPrimary })} />
          )
        }
        title={
          <Space>
            <span className={sx(characterCardStyles.nameEllipsis)}>{character.name}</span>
            {isOrganization ? (
              <Tag color="green">组织</Tag>
            ) : (
              character.role_type && (
                <Tag color={getRoleTypeColor(character.role_type)}>
                  {getRoleTypeLabel(character.role_type)}
                </Tag>
              )
            )}
            {getStatusTag()}
          </Space>
        }
        description={
          <div className={sx(characterCardStyles.descriptionBlock)}>
            {/* 角色特有字段 */}
            {!isOrganization && (
              <>
                {character.age && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">年龄：</Text>
                    <Text className="u-e4rq7y">{character.age}</Text>
                  </div>
                )}
                {character.gender && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">性别：</Text>
                    <Text className="u-e4rq7y">{character.gender}</Text>
                  </div>
                )}
                {character.personality && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">性格：</Text>
                    <Text
                      className="u-niv4z9"
                      ellipsis={{ tooltip: character.personality }}
                    >
                      {character.personality}
                    </Text>
                  </div>
                )}
                {character.relationships && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">关系：</Text>
                    <Text
                      className="u-niv4z9"
                      ellipsis={{ tooltip: character.relationships }}
                    >
                      {character.relationships}
                    </Text>
                  </div>
                )}
                {writingFields.length > 0 && (
                  <div
                    className={sx({
                      marginTop: 10,
                      paddingTop: 10,
                      borderTop: `1px dashed ${token.colorBorderSecondary}`,
                    })}
                  >
                    <div className="u-1fb5q26">
                      <Text type="secondary" className="u-1pw6xki">写作卡片</Text>
                      <Tag color="blue">v{character.card_version || 1}</Tag>
                    </div>
                    {writingFields.map((item) => (
                      <div key={item.label} className="u-b5f58h">
                        <Text type="secondary" className="u-xj35t1">{item.label}：</Text>
                        <Text
                          className="u-niv4z9"
                          ellipsis={{ tooltip: item.value }}
                        >
                          {item.value}
                        </Text>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}

            {/* 组织特有字段 */}
            {isOrganization && (
              <>
                {organizationType && (
                  <div className="u-1d1vsb6">
                    <Text type="secondary" className="u-xj35t1">类型：</Text>
                    <Tag color="cyan">{organizationType}</Tag>
                  </div>
                )}
                {character.power_level !== undefined && character.power_level !== null && (
                  <div className="u-1d1vsb6">
                    <Text type="secondary" className="u-xj35t1">势力等级：</Text>
                    <Tag color={character.power_level >= 70 ? 'red' : character.power_level >= 50 ? 'orange' : 'default'}>
                      {character.power_level}
                    </Tag>
                  </div>
                )}
                {character.location && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">所在地：</Text>
                    <Text
                      className="u-niv4z9"
                      ellipsis={{ tooltip: character.location }}
                    >
                      {character.location}
                    </Text>
                  </div>
                )}
                {character.color && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">代表颜色：</Text>
                    <Text className="u-niv4z9">{character.color}</Text>
                  </div>
                )}
                {character.motto && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">格言：</Text>
                    <Text
                      className="u-niv4z9"
                      ellipsis={{ tooltip: character.motto }}
                    >
                      {character.motto}
                    </Text>
                  </div>
                )}
                {organizationPurpose && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">目的：</Text>
                    <Text
                      className="u-niv4z9"
                      ellipsis={{ tooltip: organizationPurpose }}
                    >
                      {organizationPurpose}
                    </Text>
                  </div>
                )}
                {character.organization_members && (
                  <div className="u-qddwav">
                    <Text type="secondary" className="u-xj35t1">成员：</Text>
                    <Text className="u-1gxsf4d">
                      {typeof character.organization_members === 'string'
                        ? character.organization_members
                        : JSON.stringify(character.organization_members)}
                    </Text>
                  </div>
                )}
              </>
            )}

            {/* 通用字段 - 背景信息截断显示 */}
            {character.background && (
              <div className="u-nj5fkd">
                <Paragraph
                  type="secondary"
                  className="u-k4wxjw"
                  ellipsis={{ tooltip: character.background, rows: 3 }}
                >
                  {character.background}
                </Paragraph>
              </div>
            )}
          </div>
        }
      />
    </Card>
  );
};
