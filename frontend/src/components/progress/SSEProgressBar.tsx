import React from 'react';
import { theme } from 'antd';
import { sx } from '../../styles/sx';

interface SSEProgressBarProps {
  loading: boolean;
  progress: number;
  message: string;
}

export const SSEProgressBar: React.FC<SSEProgressBarProps> = ({
  loading,
  progress,
  message
}) => {
  const { token } = theme.useToken();

  if (!loading) return null;

  return (
    <div className="u-1ir3dsh">
      {/* 进度条 */}
      <div className={sx({
        height: 8,
        background: token.colorFillTertiary,
        borderRadius: 4,
        overflow: 'hidden',
        marginBottom: 8
      })}>
        <div className={sx({
          height: '100%',
          background: progress === 100 ? token.colorSuccess : token.colorPrimary,
          width: `${progress}%`,
          transition: 'all 0.3s ease',
          borderRadius: 4
        })} />
      </div>
      
      {/* 进度信息 */}
      <div className="u-3o46rv">
        <span className={sx({ color: token.colorTextSecondary })}>
          {message || '准备生成...'}
        </span>
        <span className={sx({ 
          fontWeight: 'bold',
          color: progress === 100 ? token.colorSuccess : token.colorPrimary
        })}>
          {progress}%
        </span>
      </div>
    </div>
  );
};
