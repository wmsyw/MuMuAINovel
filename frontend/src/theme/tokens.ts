export const BREAKPOINTS = {
  xs: 480,
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
} as const;

export const MEDIA_QUERIES = {
  belowXs: `(max-width: ${BREAKPOINTS.xs - 1}px)`,
  belowSm: `(max-width: ${BREAKPOINTS.sm - 1}px)`,
  belowMd: `(max-width: ${BREAKPOINTS.md - 1}px)`,
  belowLg: `(max-width: ${BREAKPOINTS.lg - 1}px)`,
  belowXl: `(max-width: ${BREAKPOINTS.xl - 1}px)`,
} as const;

export const themeTokens = {
  colorPrimary: '#4D8088',
  borderRadius: 8,
  borderRadiusLG: 12,
  controlHeight: 36,
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif",
  light: {
    colorBgBase: '#F8F6F1',
    colorBgContainer: '#FFFFFF',
    colorTextBase: '#2B2B2B',
  },
  dark: {
    colorBgBase: '#141414',
    colorBgLayout: '#0F1115',
    colorBgContainer: '#141414',
    colorTextBase: '#F5F5F5',
  },
} as const;
