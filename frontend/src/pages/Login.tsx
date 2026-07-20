import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  Layout,
  Row,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
  message,
  theme,
} from 'antd';
import {
  BookOutlined,
  LockOutlined,
  MailOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { authApi } from '../services/api';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AnnouncementModal from '../components/modal/AnnouncementModal';
import ThemeSwitch from '../components/common/ThemeSwitch';
import { sx } from '../styles/sx';

const { Title, Paragraph, Text } = Typography;

interface AuthConfig {
  local_auth_enabled: boolean;
  linuxdo_enabled: boolean;
  email_auth_enabled: boolean;
  email_register_enabled: boolean;
}

interface LocalLoginValues {
  username: string;
  password: string;
}

interface EmailLoginValues {
  email: string;
  code: string;
}

interface EmailRegisterValues {
  email: string;
  code: string;
  password: string;
  confirmPassword: string;
  display_name?: string;
}

interface ResetPasswordValues {
  email: string;
  code: string;
  new_password: string;
  confirmNewPassword: string;
}

export default function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);
  const [authConfig, setAuthConfig] = useState<AuthConfig>({
    local_auth_enabled: false,
    linuxdo_enabled: false,
    email_auth_enabled: false,
    email_register_enabled: false,
  });
  const [localForm] = Form.useForm<LocalLoginValues>();
  const [emailLoginForm] = Form.useForm<EmailLoginValues>();
  const [emailRegisterForm] = Form.useForm<EmailRegisterValues>();
  const [resetPasswordForm] = Form.useForm<ResetPasswordValues>();
  const { token } = theme.useToken();
  const alphaColor = (color: string, alpha: number) => `color-mix(in srgb, ${color} ${(alpha * 100).toFixed(0)}%, transparent)`;
  const primaryButtonShadow = `0 8px 20px ${alphaColor(token.colorPrimary, 0.28)}`;
  const hoverButtonShadow = `0 12px 28px ${alphaColor(token.colorPrimary, 0.36)}`;
  const [showAnnouncement, setShowAnnouncement] = useState(false);
  const [loginCodeSending, setLoginCodeSending] = useState(false);
  const [registerCodeSending, setRegisterCodeSending] = useState(false);
  const [resetCodeSending, setResetCodeSending] = useState(false);
  const [loginCountdown, setLoginCountdown] = useState(0);
  const [registerCountdown, setRegisterCountdown] = useState(0);
  const [resetCountdown, setResetCountdown] = useState(0);
  const [showResetPassword, setShowResetPassword] = useState(false);

  const localAuthEnabled = authConfig.local_auth_enabled;
  const linuxdoEnabled = authConfig.linuxdo_enabled;
  const emailAuthEnabled = authConfig.email_auth_enabled;
  const emailRegisterEnabled = authConfig.email_register_enabled;

  useEffect(() => {
    const timers = [
      { value: loginCountdown, setter: setLoginCountdown },
      { value: registerCountdown, setter: setRegisterCountdown },
      { value: resetCountdown, setter: setResetCountdown },
    ].map(({ value, setter }) => {
      if (value <= 0) {
        return null;
      }

      return window.setInterval(() => {
        setter((prev) => {
          if (prev <= 1) {
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    });

    return () => {
      timers.forEach((timer) => {
        if (timer) {
          window.clearInterval(timer);
        }
      });
    };
  }, [loginCountdown, registerCountdown, resetCountdown]);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        await authApi.getCurrentUser();
        const redirect = searchParams.get('redirect') || '/';
        navigate(redirect);
      } catch {
        try {
          const config = await authApi.getAuthConfig();
          setAuthConfig(config);
        } catch (error) {
          console.error('获取认证配置失败:', error);
          setAuthConfig({
            local_auth_enabled: false,
            linuxdo_enabled: true,
            email_auth_enabled: false,
            email_register_enabled: false,
          });
        }
        setChecking(false);
      }
    };
    checkAuth();
  }, [navigate, searchParams]);

  const handleLoginSuccess = () => {
    message.success('登录成功！');

    const hideForever = localStorage.getItem('announcement_hide_forever');
    const hideToday = localStorage.getItem('announcement_hide_today');
    const today = new Date().toDateString();

    if (hideForever === 'true' || hideToday === today) {
      const redirect = searchParams.get('redirect') || '/';
      navigate(redirect);
    } else {
      setShowAnnouncement(true);
    }
  };

  const handleLocalLogin = async (values: LocalLoginValues) => {
    try {
      setLoading(true);
      const response = await authApi.localLogin(values.username, values.password);
      if (response.success) {
        handleLoginSuccess();
      }
    } catch (error) {
      console.error('本地登录失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleEmailLogin = async (values: EmailLoginValues) => {
    try {
      setLoading(true);
      const response = await authApi.emailLogin({
        email: values.email,
        code: values.code,
      });
      if (response.success) {
        handleLoginSuccess();
      }
    } catch (error) {
      console.error('邮箱验证码登录失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const sendLoginCode = async () => {
    try {
      const values = await emailLoginForm.validateFields(['email']);
      setLoginCodeSending(true);
      const result = await authApi.sendEmailCode({ email: values.email, scene: 'login' });
      message.success(result.message || '验证码已发送');
      setLoginCountdown(result.resend_interval_seconds || 60);
    } catch (error) {
      console.error('发送 login 验证码失败:', error);
    } finally {
      setLoginCodeSending(false);
    }
  };

  const sendRegisterCode = async () => {
    try {
      const values = await emailRegisterForm.validateFields(['email']);
      setRegisterCodeSending(true);
      const result = await authApi.sendEmailCode({ email: values.email, scene: 'register' });
      message.success(result.message || '验证码已发送');
      setRegisterCountdown(result.resend_interval_seconds || 60);
    } catch (error) {
      console.error('发送 register 验证码失败:', error);
    } finally {
      setRegisterCodeSending(false);
    }
  };

  const sendResetCode = async () => {
    try {
      const values = await resetPasswordForm.validateFields(['email']);
      setResetCodeSending(true);
      const result = await authApi.sendEmailCode({ email: values.email, scene: 'reset_password' });
      message.success(result.message || '验证码已发送');
      setResetCountdown(result.resend_interval_seconds || 60);
    } catch (error) {
      console.error('发送 reset_password 验证码失败:', error);
    } finally {
      setResetCodeSending(false);
    }
  };

  const handleEmailRegister = async (values: EmailRegisterValues) => {
    try {
      setLoading(true);
      const response = await authApi.emailRegister({
        email: values.email,
        code: values.code,
        password: values.password,
        display_name: values.display_name?.trim() || undefined,
      });
      if (response.success) {
        message.success('注册成功，已自动登录');
        emailRegisterForm.resetFields(['code', 'password', 'confirmPassword']);
        setRegisterCountdown(0);
        handleLoginSuccess();
      }
    } catch (error) {
      console.error('邮箱注册失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (values: ResetPasswordValues) => {
    try {
      setLoading(true);
      const result = await authApi.resetEmailPassword({
        email: values.email,
        code: values.code,
        new_password: values.new_password,
      });
      message.success(result.message || '密码重置成功');
      resetPasswordForm.resetFields(['code', 'new_password', 'confirmNewPassword']);
      setResetCountdown(0);
      setShowResetPassword(false);
    } catch (error) {
      console.error('重置密码失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLinuxDOLogin = async () => {
    try {
      setLoading(true);
      const response = await authApi.getLinuxDOAuthUrl();

      const redirect = searchParams.get('redirect');
      if (redirect) {
        sessionStorage.setItem('login_redirect', redirect);
      }

      window.location.href = response.auth_url;
    } catch (error) {
      console.error('获取授权地址失败:', error);
      message.error('获取授权地址失败，请稍后重试');
      setLoading(false);
    }
  };

  const handleAnnouncementClose = () => {
    setShowAnnouncement(false);
    const redirect = searchParams.get('redirect') || '/';
    navigate(redirect);
  };

  const handleDoNotShowToday = () => {
    const today = new Date().toDateString();
    localStorage.setItem('announcement_hide_today', today);
  };

  const handleNeverShow = () => {
    localStorage.setItem('announcement_hide_forever', 'true');
  };

  const loginTips = useMemo(() => {
    const tips = [
      '首次 LinuxDO 登录会自动创建账号。',
    ];

    if (localAuthEnabled) {
      tips.unshift('请使用管理员配置的本地账号登录。');
    }

    if (emailAuthEnabled) {
      tips.push('邮箱注册用户支持通过邮箱验证码重置密码。');
    }

    return tips;
  }, [emailAuthEnabled, localAuthEnabled]);

  const featureItems = [
    {
      icon: <RobotOutlined />,
      title: '多 AI 模型协同',
      description: '支持 OpenAI、Gemini、Claude 等主流模型，按场景灵活切换。',
    },
    {
      icon: <ThunderboltOutlined />,
      title: '智能向导驱动',
      description: '自动生成大纲、角色与世界观，快速搭建完整故事骨架。',
    },
    {
      icon: <TeamOutlined />,
      title: '角色组织管理',
      description: '人物关系、组织架构可视化管理，复杂设定也能清晰掌控。',
    },
    {
      icon: <BookOutlined />,
      title: '章节创作闭环',
      description: '支持章节生成、编辑、重写与润色，持续提升内容质量。',
    },
  ];

  const renderLocalLogin = () => (
    <>
      <Form
        form={localForm}
        layout="vertical"
        onFinish={handleLocalLogin}
        size="large"
        className="u-1ir3dsh"
      >
        <Form.Item
          name="username"
          label="管理账号"
          rules={[{ required: true, message: '请输入管理账号/邮箱' }]}
        >
          <Input
            prefix={<UserOutlined className={sx({ color: token.colorTextTertiary })} />}
            placeholder="请输入管理账号/邮箱"
            autoComplete="username"
            className="u-1xo9d8x"
          />
        </Form.Item>
        <Form.Item
          name="password"
          label="访问密钥"
          rules={[{ required: true, message: '请输入访问密钥' }]}
        >
          <Input.Password
            prefix={<LockOutlined className={sx({ color: token.colorTextTertiary })} />}
            placeholder="请输入访问密钥"
            autoComplete="current-password"
            className="u-1xo9d8x"
          />
        </Form.Item>
        <Form.Item className="u-nq9ky0">
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            block
            className={sx({
              height: 46,
              fontSize: 16,
              fontWeight: 600,
              background: `linear-gradient(90deg, ${token.colorPrimary} 0%, ${alphaColor(token.colorPrimary, 0.86)} 100%)`,
              border: 'none',
              borderRadius: '12px',
              boxShadow: primaryButtonShadow,
            })}
          >
            登录系统
          </Button>
        </Form.Item>
      </Form>

      {linuxdoEnabled ? (
        <>
          <Divider className="u-1io0ppg">第三方登录</Divider>
          {renderLinuxDOLogin()}
        </>
      ) : null}
    </>
  );

  const renderEmailLogin = () => {
    if (showResetPassword) {
      return (
        <div className="u-1ir3dsh">
          <Space direction="vertical" size={12} className="u-1f3r3s">
            <Space className="u-1qos3j5">
              <Title level={5} className="u-avalr8">忘记密码 / 重置密码</Title>
              <Button type="link" className="u-1kt81a5" onClick={() => setShowResetPassword(false)}>
                返回验证码登录
              </Button>
            </Space>

            <Card size="small" bordered={false} className={sx({ borderRadius: 12, background: token.colorFillAlter })}>
              <Form
                form={resetPasswordForm}
                layout="vertical"
                onFinish={handleResetPassword}
                size="middle"
              >
                <Form.Item
                  name="email"
                  label="注册邮箱"
                  rules={[
                    { required: true, message: '请输入注册邮箱' },
                    { type: 'email', message: '请输入有效的邮箱地址' },
                  ]}
                >
                  <Input prefix={<MailOutlined />} placeholder="请输入注册邮箱" />
                </Form.Item>
                <Form.Item label="重置验证码" required className="u-1qz2mrl">
                  <Space.Compact className="u-1f3r3s">
                    <Form.Item
                      name="code"
                      noStyle
                      rules={[
                        { required: true, message: '请输入重置验证码' },
                        { len: 6, message: '验证码长度为 6 位' },
                      ]}
                    >
                      <Input placeholder="请输入重置验证码" maxLength={6} />
                    </Form.Item>
                    <Button
                      onClick={sendResetCode}
                      loading={resetCodeSending}
                      disabled={resetCountdown > 0}
                    >
                      {resetCountdown > 0 ? `${resetCountdown}s 后重发` : '发送验证码'}
                    </Button>
                  </Space.Compact>
                </Form.Item>
                <Form.Item
                  name="new_password"
                  label="新密码"
                  rules={[
                    { required: true, message: '请输入新密码' },
                    { min: 6, message: '密码长度至少为 6 个字符' },
                  ]}
                >
                  <Input.Password prefix={<LockOutlined />} placeholder="请输入新密码" />
                </Form.Item>
                <Form.Item
                  name="confirmNewPassword"
                  label="确认新密码"
                  dependencies={['new_password']}
                  rules={[
                    { required: true, message: '请再次输入新密码' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (!value || getFieldValue('new_password') === value) {
                          return Promise.resolve();
                        }
                        return Promise.reject(new Error('两次输入的新密码不一致'));
                      },
                    }),
                  ]}
                >
                  <Input.Password prefix={<LockOutlined />} placeholder="请再次输入新密码" />
                </Form.Item>
                <Button type="default" htmlType="submit" loading={loading} block>
                  重置密码
                </Button>
              </Form>
            </Card>
          </Space>
        </div>
      );
    }

    return (
      <Form
        form={emailLoginForm}
        layout="vertical"
        onFinish={handleEmailLogin}
        size="large"
        className="u-1ir3dsh"
      >
        <Form.Item
          name="email"
          label="邮箱地址"
          rules={[
            { required: true, message: '请输入邮箱地址' },
            { type: 'email', message: '请输入有效的邮箱地址' },
          ]}
        >
          <Input
            prefix={<MailOutlined className={sx({ color: token.colorTextTertiary })} />}
            placeholder="请输入已注册邮箱"
            autoComplete="email"
            className="u-1xo9d8x"
          />
        </Form.Item>

        <Form.Item label="登录验证码" required className="u-19d88e2">
          <Space.Compact className="u-1f3r3s">
            <Form.Item
              name="code"
              noStyle
              rules={[
                { required: true, message: '请输入登录验证码' },
                { len: 6, message: '验证码长度为 6 位' },
              ]}
            >
              <Input
                prefix={<SafetyCertificateOutlined className={sx({ color: token.colorTextTertiary })} />}
                placeholder="请输入 6 位登录验证码"
                maxLength={6}
                className="u-1gtlon8"
              />
            </Form.Item>
            <Button
              className="u-wz6xsh"
              onClick={sendLoginCode}
              loading={loginCodeSending}
              disabled={loginCountdown > 0}
            >
              {loginCountdown > 0 ? `${loginCountdown}s 后重发` : '发送验证码'}
            </Button>
          </Space.Compact>
        </Form.Item>

        <Form.Item className="u-nq9ky0">
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            block
            className={sx({
              height: 46,
              fontSize: 16,
              fontWeight: 600,
              background: `linear-gradient(90deg, ${token.colorPrimary} 0%, ${alphaColor(token.colorPrimary, 0.86)} 100%)`,
              border: 'none',
              borderRadius: '12px',
              boxShadow: primaryButtonShadow,
            })}
          >
            验证码登录
          </Button>
        </Form.Item>

        <div className="u-1386e4">
          <Button type="link" className="u-1kt81a5" onClick={() => setShowResetPassword(true)}>
            忘记密码？点击重置
          </Button>
        </div>
      </Form>
    );
  };

  const renderEmailRegister = () => (
    <Form
      form={emailRegisterForm}
      layout="vertical"
      onFinish={handleEmailRegister}
      size="large"
      className="u-1ir3dsh"
    >
      <Form.Item
        name="email"
        label="注册邮箱"
        rules={[
          { required: true, message: '请输入注册邮箱' },
          { type: 'email', message: '请输入有效的邮箱地址' },
        ]}
      >
        <Input
          prefix={<MailOutlined className={sx({ color: token.colorTextTertiary })} />}
          placeholder="请输入注册邮箱"
          autoComplete="email"
          className="u-1xo9d8x"
        />
      </Form.Item>

      <Form.Item label="邮箱验证码" required className="u-1qz2mrl">
        <Space.Compact className="u-1f3r3s">
          <Form.Item
            name="code"
            noStyle
            rules={[
              { required: true, message: '请输入邮箱验证码' },
              { len: 6, message: '验证码长度为 6 位' },
            ]}
          >
            <Input
              prefix={<SafetyCertificateOutlined className={sx({ color: token.colorTextTertiary })} />}
              placeholder="请输入 6 位验证码"
              maxLength={6}
              className="u-1gtlon8"
            />
          </Form.Item>
          <Button
            className="u-wz6xsh"
            onClick={sendRegisterCode}
            loading={registerCodeSending}
            disabled={registerCountdown > 0}
          >
            {registerCountdown > 0 ? `${registerCountdown}s 后重发` : '发送验证码'}
          </Button>
        </Space.Compact>
      </Form.Item>

      <Form.Item
        name="display_name"
        label="昵称"
        rules={[{ max: 50, message: '昵称长度不能超过 50 个字符' }]}
      >
        <Input
          prefix={<UserOutlined className={sx({ color: token.colorTextTertiary })} />}
          placeholder="选填，默认使用邮箱前缀"
          autoComplete="nickname"
          className="u-1xo9d8x"
        />
      </Form.Item>

      <Form.Item
        name="password"
        label="登录密码"
        rules={[
          { required: true, message: '请输入登录密码' },
          { min: 6, message: '密码长度至少为 6 个字符' },
        ]}
      >
        <Input.Password
          prefix={<LockOutlined className={sx({ color: token.colorTextTertiary })} />}
          placeholder="请输入登录密码"
          autoComplete="new-password"
          className="u-1xo9d8x"
        />
      </Form.Item>

      <Form.Item
        name="confirmPassword"
        label="确认密码"
        dependencies={['password']}
        rules={[
          { required: true, message: '请再次输入登录密码' },
          ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue('password') === value) {
                return Promise.resolve();
              }
              return Promise.reject(new Error('两次输入的密码不一致'));
            },
          }),
        ]}
      >
        <Input.Password
          prefix={<LockOutlined className={sx({ color: token.colorTextTertiary })} />}
          placeholder="请再次输入登录密码"
          autoComplete="new-password"
          className="u-1xo9d8x"
        />
      </Form.Item>

      <Form.Item className="u-nq9ky0">
        <Button
          type="primary"
          htmlType="submit"
          loading={loading}
          block
          className={sx({
            height: 46,
            fontSize: 16,
            fontWeight: 600,
            background: `linear-gradient(90deg, ${token.colorPrimary} 0%, ${alphaColor(token.colorPrimary, 0.86)} 100%)`,
            border: 'none',
            borderRadius: '12px',
            boxShadow: primaryButtonShadow,
          })}
        >
          注册并登录
        </Button>
      </Form.Item>

      <Text type="secondary" className="u-lzddg6">
        验证码将发送到你填写的邮箱，若未收到请检查垃圾箱或稍后重试。注册后可通过邮箱验证码登录，也支持邮箱重置密码。
      </Text>
    </Form>
  );

  const renderLinuxDOLogin = () => (
    <div>
      <Button
        type="primary"
        size="large"
        icon={(
          <img
            src="/favicon.ico"
            alt="LinuxDO"
            className="u-1ijczq1"
          />
        )}
        loading={loading}
        onClick={handleLinuxDOLogin}
        block
        className={sx('login-oauth-button', {
          height: 46,
          fontSize: 16,
          fontWeight: 600,
          background: `linear-gradient(90deg, ${token.colorPrimary} 0%, ${alphaColor(token.colorPrimary, 0.86)} 100%)`,
          border: 'none',
          borderRadius: '12px',
          boxShadow: primaryButtonShadow,
          transition: 'all 0.3s ease',
          '--login-hover-shadow': hoverButtonShadow,
        })}
      >
        使用 LinuxDO OAuth 登录
      </Button>
    </div>
  );

  const authTabs = [
    ...(localAuthEnabled
      ? [
          {
            key: 'local-login',
            label: '本地登录',
            children: renderLocalLogin(),
          },
        ]
      : []),
    ...(emailAuthEnabled
      ? [
          {
            key: 'email-login',
            label: '邮箱登录',
            children: renderEmailLogin(),
          },
        ]
      : []),
    ...(emailAuthEnabled && emailRegisterEnabled
      ? [
          {
            key: 'email-register',
            label: '邮箱注册',
            children: renderEmailRegister(),
          },
        ]
      : []),
  ];

  if (checking) {
    return (
      <div
        className={sx({
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          background: token.colorBgLayout,
        })}
      >
        <Spin size="large" className={sx({ color: token.colorPrimary })} />
      </div>
    );
  }

  return (
    <>
      <AnnouncementModal
        visible={showAnnouncement}
        onClose={handleAnnouncementClose}
        onDoNotShowToday={handleDoNotShowToday}
        onNeverShow={handleNeverShow}
      />
      <Layout className={sx({ minHeight: '100vh', background: token.colorBgLayout })}>
        <div
          className={sx({
            position: 'fixed',
            top: 20,
            right: 20,
            zIndex: 10,
            padding: '8px 10px',
            borderRadius: 12,
            background: alphaColor(token.colorBgContainer, 0.9),
            border: `1px solid ${token.colorBorderSecondary}`,
            backdropFilter: 'blur(6px)',
          })}
        >
          <ThemeSwitch size="small" />
        </div>
        <Row className="u-1u8nmfx">
          <Col xs={0} lg={11}>
            <section
              className={sx({
                height: '100%',
                padding: '44px 64px 88px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                position: 'relative',
                overflow: 'hidden',
                backgroundColor: alphaColor(token.colorBgContainer, 0.78),
                backgroundImage: `linear-gradient(${alphaColor(token.colorTextSecondary, 0.06)} 1px, transparent 1px), linear-gradient(90deg, ${alphaColor(token.colorTextSecondary, 0.06)} 1px, transparent 1px)`,
                backgroundSize: '68px 68px',
              })}
            >
              <div
                className={sx({
                  position: 'absolute',
                  inset: 0,
                  background: `radial-gradient(circle at 25% 20%, ${alphaColor(token.colorPrimary, 0.12)} 0%, transparent 50%)`,
                  pointerEvents: 'none',
                })}
              />

              <div
                className="u-epu4id"
              >
                <Space align="center" size={14}>
                  <div
                    className={sx({
                      width: 46,
                      height: 46,
                      borderRadius: 14,
                      background: `linear-gradient(135deg, ${token.colorPrimary} 0%, ${alphaColor(token.colorPrimary, 0.7)} 100%)`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: primaryButtonShadow,
                    })}
                  >
                    <img
                      src="/logo.svg"
                      alt="AI Novel Studio"
                      className="u-1gkk5k9"
                    />
                  </div>
                  <Title level={3} className={sx({ margin: 0, color: token.colorText })}>
                    AI Novel Studio
                  </Title>
                </Space>

                <Space direction="vertical" size={32} className="u-1f3r3s">
                  <div className="u-dlycg4">
                    <Title
                      level={1}
                      className={sx({
                        marginBottom: 22,
                        color: token.colorText,
                        lineHeight: 1.12,
                        fontWeight: 800,
                        fontSize: 'clamp(52px, 3vw, 78px)',
                      })}
                    >
                      基于 AI 的
                      <br />
                      <span
                        className={sx({
                          backgroundImage: `linear-gradient(90deg, ${token.colorPrimary} 0%, #d946ef 100%)`,
                          WebkitBackgroundClip: 'text',
                          backgroundClip: 'text',
                          WebkitTextFillColor: 'transparent',
                          color: token.colorPrimary,
                        })}
                      >
                        智能小说创作助手
                      </span>
                    </Title>
                    <Paragraph
                      className={sx({
                        fontSize: 'clamp(18px, 1vw, 22px)',
                        lineHeight: 1.85,
                        color: token.colorTextSecondary,
                        marginBottom: 0,
                        maxWidth: 800,
                      })}
                    >
                      从灵感到成稿，围绕「多模型协同、创作流程自动化、角色关系管理、章节精修」构建一体化创作工作台。
                    </Paragraph>
                  </div>

                  <Row gutter={[20, 20]} className="u-1qsbsi7">
                    {featureItems.map((item) => (
                      <Col span={12} key={item.title}>
                        <Card
                          size="small"
                          bordered={false}
                          className={sx({
                            height: '100%',
                            minHeight: 120,
                            borderRadius: 16,
                            background: alphaColor(token.colorBgContainer, 0.9),
                          })}
                          bodyStyle={{ padding: 16 }}
                        >
                          <Space direction="vertical" size={8}>
                            <Space size={10} className={sx({ color: token.colorPrimary, fontWeight: 700, fontSize: 15 })}>
                              {item.icon}
                              <span>{item.title}</span>
                            </Space>
                            <Paragraph className={sx({ marginBottom: 0, color: token.colorTextSecondary, fontSize: 14, lineHeight: 1.65 })}>
                              {item.description}
                            </Paragraph>
                          </Space>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                </Space>

                <Space size={[10, 14]} wrap className="u-dlycg4">
                  <Tag color="blue">OpenAI</Tag>
                  <Tag color="geekblue">Gemini</Tag>
                  <Tag color="purple">Claude</Tag>
                  <Tag color="cyan">LinuxDO OAuth</Tag>
                  <Tag color="green">Docker Compose</Tag>
                  <Tag color="gold">PostgreSQL</Tag>
                </Space>
              </div>

              <Paragraph
                className={sx({
                  marginBottom: 0,
                  fontSize: 12,
                  color: token.colorTextTertiary,
                  position: 'relative',
                  zIndex: 1,
                  letterSpacing: 0.4,
                })}
              >
                © 2026 AI Novel Studio · GPLv3 License
              </Paragraph>
            </section>
          </Col>

          <Col xs={24} lg={13}>
            <section
              className={sx({
                minHeight: '100vh',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '48px min(7vw, 72px)',
                background: token.colorBgLayout,
              })}
            >
              <div className="u-h90s1e">
                <Space direction="vertical" size={4}>
                  <Title level={2} className={sx({ marginBottom: 0, fontWeight: 700, color: token.colorText })}>
                    欢迎回来
                  </Title>
                  <Paragraph className={sx({ marginBottom: 0, color: token.colorTextSecondary })}>
                    登录 AI Novel Studio，继续你的小说创作项目。
                  </Paragraph>
                </Space>

                <div className="u-1si7ivs">
                  {authTabs.length > 0 ? (
                    <Tabs defaultActiveKey={authTabs[0].key} items={authTabs} />
                  ) : null}

                  {!localAuthEnabled && !linuxdoEnabled && !emailAuthEnabled ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="当前未启用可用登录方式"
                      description="请联系管理员在系统配置中启用本地登录、邮箱认证或 LinuxDO OAuth 登录。"
                    />
                  ) : null}

                  {emailAuthEnabled && !emailRegisterEnabled ? (
                    <Alert
                      type="info"
                      showIcon
                      className="u-1huwgz9"
                      message="邮箱注册暂未开放"
                      description="当前仅开放邮箱验证码登录与找回密码，如需注册请联系管理员。"
                    />
                  ) : null}

                  <Divider className="u-152vf29" />
                  <Alert
                    type="info"
                    showIcon
                    icon={<SafetyCertificateOutlined />}
                    className={sx({ background: alphaColor(token.colorPrimary, 0.06), borderRadius: 12 })}
                    message="登录说明"
                    description={(
                      <ul className="u-tjojz2">
                        {loginTips.map((tip) => (
                          <li key={tip} className="u-ohn8hu">
                            {tip}
                          </li>
                        ))}
                      </ul>
                    )}
                  />
                </div>
              </div>
            </section>
          </Col>
        </Row>
      </Layout>
    </>
  );
}
