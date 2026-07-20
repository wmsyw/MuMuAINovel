import { useState, useEffect } from 'react';
import { Dropdown, Avatar, Space, Typography, message, Modal, Form, Input, Button, theme } from 'antd';
import { UserOutlined, LogoutOutlined, TeamOutlined, CrownOutlined, LockOutlined } from '@ant-design/icons';
import { authApi } from '../../services/api';
import type { User } from '../../types';
import type { MenuProps } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useIsMobile } from '../../hooks/useMediaQuery';
import { sx } from '../../styles/sx';

const { Text } = Typography;

interface UserMenuProps {
  /** 是否总是显示完整信息（用于移动端侧边栏） */
  showFullInfo?: boolean;
  /** 紧凑模式（用于折叠侧边栏，仅展示头像） */
  compact?: boolean;
}

export default function UserMenu({ showFullInfo = false, compact = false }: UserMenuProps) {
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [changePasswordForm] = Form.useForm();
  const [changingPassword, setChangingPassword] = useState(false);
  const { token } = theme.useToken();
  const isMobile = useIsMobile();
  const alphaColor = (color: string, alpha: number) => `color-mix(in srgb, ${color} ${(alpha * 100).toFixed(0)}%, transparent)`;

  useEffect(() => {
    loadCurrentUser();
  }, []);

  const loadCurrentUser = async () => {
    try {
      const user = await authApi.getCurrentUser();
      setCurrentUser(user);
    } catch (error) {
      console.error('获取用户信息失败:', error);
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
      message.success('已退出登录');
      window.location.href = '/login';
    } catch (error) {
      console.error('退出登录失败:', error);
      message.error('退出登录失败');
    }
  };

  const handleShowUserManagement = () => {
    if (!currentUser?.is_admin) {
      message.warning('只有管理员可以访问用户管理');
      return;
    }
    navigate('/user-management');
  };

  const handleChangePassword = async (values: { oldPassword: string; newPassword: string }) => {
    try {
      setChangingPassword(true);
      await authApi.setPassword(values.newPassword);
      message.success('密码修改成功');
      setShowChangePassword(false);
      changePasswordForm.resetFields();
    } catch (error: unknown) {
      console.error('修改密码失败:', error);
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || '修改密码失败');
    } finally {
      setChangingPassword(false);
    }
  };

  const menuItems: MenuProps['items'] = [
    {
      key: 'user-info',
      label: (
        <div className="u-15tlmef">
          <Text strong>{currentUser?.display_name || currentUser?.username}</Text>
          <br />
          <Text type="secondary" className="u-1pw6xki">
            Trust Level: {currentUser?.trust_level}
            {currentUser?.is_admin && ' · 管理员'}
          </Text>
        </div>
      ),
      disabled: true,
    },
    {
      type: 'divider',
    },
    ...(currentUser?.is_admin ? [
      {
        key: 'user-management',
        icon: <TeamOutlined />,
        label: '用户管理',
        onClick: handleShowUserManagement,
      },
      {
        type: 'divider' as const,
      }
    ] : []),
    {
      key: 'change-password',
      icon: <LockOutlined />,
      label: '修改密码',
      onClick: () => setShowChangePassword(true),
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  if (!currentUser) {
    return null;
  }

  return (
    <>
      <Dropdown menu={{ items: menuItems }} placement="bottomRight">
        <div
          className={sx('user-menu-trigger', {
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: compact ? 0 : 12,
            padding: compact ? '4px' : '8px 16px',
            background: alphaColor(token.colorBgContainer, 0.65),
            backdropFilter: 'blur(10px)',
            WebkitBackdropFilter: 'blur(10px)',
            borderRadius: compact ? 16 : 24,
            border: `1px solid ${token.colorBorder}`,
            transition: 'all 0.3s ease',
            boxShadow: `0 8px 20px ${alphaColor(token.colorText, 0.08)}`,
          })}
        >
          <div className="u-1dxcc1v">
            <Avatar
              src={currentUser.avatar_url}
              icon={<UserOutlined />}
              size={compact ? 32 : 40}
              className={sx({
                backgroundColor: token.colorPrimary,
                border: `3px solid ${token.colorWhite}`,
                boxShadow: `0 8px 20px ${alphaColor(token.colorText, 0.12)}`,
              })}
            />
            {currentUser.is_admin && (
              <div className={sx({
                position: 'absolute',
                bottom: -2,
                right: -2,
                width: 18,
                height: 18,
                background: `linear-gradient(135deg, ${token.colorWarning} 0%, ${token.colorWarningHover} 100%)`,
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: `2px solid ${token.colorWhite}`,
                boxShadow: `0 2px 4px ${alphaColor(token.colorText, 0.2)}`,
              })}>
                <CrownOutlined className={sx({ fontSize: 9, color: token.colorWhite })} />
              </div>
            )}
          </div>
          <Space direction="vertical" size={0} className={sx({ display: compact || (isMobile && !showFullInfo) ? 'none' : 'flex' })}>
            <Text strong className={sx({
              color: token.colorText,
              fontSize: 14,
              lineHeight: '20px',
            })}>
              {currentUser.display_name || currentUser.username}
            </Text>
            <Text className={sx({
              color: token.colorTextSecondary,
              fontSize: 12,
              lineHeight: '18px',
            })}>
              {currentUser.is_admin ? '👑 管理员' : `🎖️ Trust Level ${currentUser.trust_level}`}
            </Text>
          </Space>
        </div>
      </Dropdown>

      <Modal
        title="修改密码"
        open={showChangePassword}
        onCancel={() => {
          setShowChangePassword(false);
          changePasswordForm.resetFields();
        }}
        footer={null}
        width={480}
        centered
      >
        <Form
          form={changePasswordForm}
          layout="vertical"
          onFinish={handleChangePassword}
          autoComplete="off"
        >
          <Form.Item
            label="新密码"
            name="newPassword"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码至少6个字符' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入新密码（至少6个字符）"
              autoComplete="new-password"
            />
          </Form.Item>

          <Form.Item
            label="确认密码"
            name="confirmPassword"
            dependencies={['newPassword']}
            rules={[
              { required: true, message: '请确认新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('newPassword') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请再次输入新密码"
              autoComplete="new-password"
            />
          </Form.Item>

          <Form.Item className="u-1sezbee">
            <Space className="u-1qyyh4r">
              <Button onClick={() => {
                setShowChangePassword(false);
                changePasswordForm.resetFields();
              }}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={changingPassword}>
                确认修改
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
