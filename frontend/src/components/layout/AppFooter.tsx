import { useState, useEffect } from 'react';
import { Typography, Space, Divider, Badge, Grid, theme } from 'antd';
import { GithubOutlined, CopyrightOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { VERSION_INFO, getVersionString } from '../../config/version';
import { checkLatestVersion } from '../../services/versionService';
import { sx } from '../../styles/sx';

const { Text, Link } = Typography;
const { useBreakpoint } = Grid;

interface AppFooterProps {
  sidebarWidth?: number;
}

export default function AppFooter({ sidebarWidth = 0 }: AppFooterProps) {
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  const [hasUpdate, setHasUpdate] = useState(false);
  const [latestVersion, setLatestVersion] = useState('');
  const [releaseUrl, setReleaseUrl] = useState('');
  const { token } = theme.useToken();
  const alphaColor = (color: string, alpha: number) => `color-mix(in srgb, ${color} ${(alpha * 100).toFixed(0)}%, transparent)`;

  useEffect(() => {
    // 检查版本更新（每次都重新检查）
    const checkVersion = async () => {
      try {
        const result = await checkLatestVersion();
        setHasUpdate(result.hasUpdate);
        setLatestVersion(result.latestVersion);
        setReleaseUrl(result.releaseUrl);
      } catch {
        // 静默失败
      }
    };

    // 延迟3秒后检查，避免影响首次加载
    const timer = setTimeout(checkVersion, 3000);
    return () => clearTimeout(timer);
  }, []);

  // 点击版本号查看更新
  const handleVersionClick = () => {
    if (hasUpdate && releaseUrl) {
      window.open(releaseUrl, '_blank');
    }
  };

  // 计算左边距：桌面端有侧边栏时需要偏移
  const leftOffset = isMobile ? 0 : sidebarWidth;

  return (
    <div
      className={sx({
        position: 'fixed',
        bottom: 0,
        left: leftOffset,
        right: 0,
        backdropFilter: 'blur(20px) saturate(180%)',
        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        borderTop: `1px solid ${token.colorBorder}`,
        padding: isMobile ? '8px 12px' : '10px 16px',
        zIndex: 100,
        boxShadow: `0 -2px 16px ${alphaColor(token.colorText, 0.08)}`,
        backgroundColor: alphaColor(token.colorBgContainer, 0.82), // 半透明背景以支持 backdrop-filter
        transition: 'left 0.3s ease', // 平滑过渡
      })}
    >
      <div
        className="u-7n8eab"
      >
        {isMobile ? (
          // 移动端：紧凑单行布局
          <div className="u-h90r5b">
            <Badge dot={hasUpdate} offset={[-8, 2]}>
              <Text
                onClick={handleVersionClick}
                className={sx({
                  fontSize: 11,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  color: token.colorPrimary,
                  cursor: hasUpdate ? 'pointer' : 'default',
                })}
                title={hasUpdate ? `发现新版本 v${latestVersion}，点击查看` : '当前版本'}
              >
                <strong className={sx({ color: token.colorText })}>{VERSION_INFO.projectName}</strong>
                <span>{getVersionString()}</span>
              </Text>
            </Badge>
            {VERSION_INFO.githubUrl && (
              <Link href={VERSION_INFO.githubUrl} target="_blank" rel="noopener noreferrer">
                <GithubOutlined className="u-1pw6xki" />
              </Link>
            )}
            <Text
              className={sx({
                fontSize: 10,
                color: token.colorTextTertiary,
              })}
            >
              <ClockCircleOutlined className="u-je5jx" />
              {VERSION_INFO.buildTime}
            </Text>
          </div>
        ) : (
          // PC端：完整布局
          <Space
            direction="horizontal"
            size={12}
            split={<Divider type="vertical" className={sx({ borderColor: token.colorBorder })} />}
            className="u-3yxbbt"
          >
            {/* 版本信息 */}
            <Badge dot={hasUpdate} offset={[-8, 2]}>
              <Text
                onClick={handleVersionClick}
                className={sx(hasUpdate && 'footer-version-update', {
                  fontSize: 12,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  color: token.colorTextSecondary,
                  textShadow: 'none',
                  cursor: hasUpdate ? 'pointer' : 'default',
                  transition: 'all 0.3s',
                })}
                title={hasUpdate ? `发现新版本 v${latestVersion}，点击查看` : '当前版本'}
              >
                <strong className={sx({ color: token.colorText })}>{VERSION_INFO.projectName}</strong>
                <span>{getVersionString()}</span>
              </Text>
            </Badge>

            {VERSION_INFO.githubUrl && (
              <Link href={VERSION_INFO.githubUrl} target="_blank" rel="noopener noreferrer" className={sx({ color: token.colorTextSecondary })}>
                <GithubOutlined className="u-sidwtb" />
                <span>GitHub</span>
              </Link>
            )}
            {VERSION_INFO.linuxDoUrl && (
              <Link href={VERSION_INFO.linuxDoUrl} target="_blank" rel="noopener noreferrer" className={sx({ color: token.colorTextSecondary })}>
                社区
              </Link>
            )}


            {/* 许可证 */}
            <Link
              href={VERSION_INFO.licenseUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={sx({
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                color: token.colorTextSecondary,
              })}
            >
              <CopyrightOutlined className="u-ts7gql" />
              <span>{VERSION_INFO.license}</span>
            </Link>

            {/* 更新时间 */}
            <Text
              className={sx({
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                color: token.colorTextTertiary,
              })}
            >
              <ClockCircleOutlined className="u-1pw6xki" />
              <span>{VERSION_INFO.buildTime}</span>
            </Text>

          </Space>
        )}
      </div>

    </div>
  );
}
