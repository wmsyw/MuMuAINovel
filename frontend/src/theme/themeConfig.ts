import type { ThemeConfig } from 'antd';
import { theme } from 'antd';
import type { ThemeMode } from './themeStorage';
import { themeTokens } from './tokens';

export type ResolvedThemeMode = Exclude<ThemeMode, 'system'>;

const sharedToken: ThemeConfig['token'] = {
  colorPrimary: themeTokens.colorPrimary,
  borderRadius: themeTokens.borderRadius,
  wireframe: false,
  fontFamily: themeTokens.fontFamily,
};

const sharedComponents: ThemeConfig['components'] = {
  Button: {
    borderRadius: themeTokens.borderRadius,
    controlHeight: themeTokens.controlHeight,
  },
  Card: {
    borderRadiusLG: themeTokens.borderRadiusLG,
  },
  Tooltip: {
    colorBgSpotlight: sharedToken.colorPrimary,
  },
};

const lightThemeConfig: ThemeConfig = {
  algorithm: theme.defaultAlgorithm,
  token: {
    ...sharedToken,
    colorBgBase: themeTokens.light.colorBgBase,
    colorTextBase: themeTokens.light.colorTextBase,
    colorBgLayout: themeTokens.light.colorBgBase,
    colorBgContainer: themeTokens.light.colorBgContainer,
  },
  components: {
    ...sharedComponents,
    Layout: {
      bodyBg: themeTokens.light.colorBgBase,
      headerBg: themeTokens.light.colorBgContainer,
      siderBg: themeTokens.light.colorBgContainer,
    },
  },
};

const darkThemeConfig: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    ...sharedToken,
    colorBgBase: themeTokens.dark.colorBgBase,
    colorTextBase: themeTokens.dark.colorTextBase,
    colorBgLayout: themeTokens.dark.colorBgLayout,
    colorBgContainer: themeTokens.dark.colorBgContainer,
  },
  components: {
    ...sharedComponents,
    Layout: {
      bodyBg: themeTokens.dark.colorBgLayout,
      headerBg: themeTokens.dark.colorBgContainer,
      siderBg: themeTokens.dark.colorBgContainer,
    },
  },
};

export const getThemeConfig = (mode: ResolvedThemeMode): ThemeConfig => {
  return mode === 'dark' ? darkThemeConfig : lightThemeConfig;
};
