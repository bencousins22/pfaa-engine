/**
 * PFAA Design System — Themed Ink components with light/dark support
 *
 * Provides a ThemeProvider, useTheme hook, and themed wrapper components
 * (ThemedBox, ThemedText) that resolve named color keys against the
 * current light or dark palette. Built for React 19 + Ink 6.
 *
 * Pearl White Glossy palette: luminous whites, soft iridescent accents,
 * silver borders, ultra-smooth aesthetic.
 */

import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { Box, Text } from 'ink';
import type { BoxProps, TextProps } from 'ink';

// ── Color palette types ──────────────────────────────────────────────

/** Named color keys supported by the design system. */
export type ColorKey =
  | 'fg'
  | 'bg'
  | 'accent'
  | 'success'
  | 'error'
  | 'warning'
  | 'info'
  | 'muted'
  | 'border'
  | 'pearl'
  | 'silver'
  | 'shimmer'
  | 'irisRose'
  | 'irisLav';

/** A complete color map for one appearance mode. */
export type ColorMap = Record<ColorKey, string>;

/** The full theme object containing both light and dark palettes. */
export interface Theme {
  light: ColorMap;
  dark: ColorMap;
}

/** User-facing theme preference. 'auto' resolves at runtime. */
export type ThemeMode = 'light' | 'dark' | 'auto';

/** Resolved theme mode (never 'auto'). */
export type ResolvedThemeMode = 'light' | 'dark';

// ── PFAA brand palette ───────────────────────────────────────────────

export const pfaaTheme: Theme = {
  dark: {
    fg:       '#F8F8FF',
    bg:       '#1C1C1E',
    accent:   '#E8D5B7',
    success:  '#A8E6CF',
    error:    '#FFB5B5',
    warning:  '#FFE4B5',
    info:     '#B5D4FF',
    muted:    '#8E8E93',
    border:   '#D4D4D8',
    pearl:    '#F8F8FF',
    silver:   '#C0C0C0',
    shimmer:  '#E8D5B7',
    irisRose: '#FFE4E1',
    irisLav:  '#E6E6FA',
  },
  light: {
    fg:       '#2C2C2E',
    bg:       '#FAFAFA',
    accent:   '#8B7355',
    success:  '#4CAF50',
    error:    '#E57373',
    warning:  '#FFB74D',
    info:     '#64B5F6',
    muted:    '#9E9E9E',
    border:   '#C7C7CC',
    pearl:    '#F5F5F5',
    silver:   '#BDBDBD',
    shimmer:  '#D4C5A9',
    irisRose: '#F8BBD0',
    irisLav:  '#D1C4E9',
  },
};

// ── Terminal background detection ────────────────────────────────────

/**
 * Best-effort detection of terminal background color.
 *
 * Checks COLORFGBG (set by many terminals, e.g. "15;0" means light fg
 * on dark bg), then falls back to common env hints. Returns 'dark' if
 * detection is inconclusive — dark terminals are overwhelmingly more
 * common among developer tools.
 */
function detectTerminalTheme(): ResolvedThemeMode {
  // COLORFGBG: "fg;bg" — bg >= 8 is generally light
  const colorfgbg = process.env['COLORFGBG'];
  if (colorfgbg) {
    const parts = colorfgbg.split(';');
    const bg = parseInt(parts[parts.length - 1], 10);
    if (!Number.isNaN(bg)) {
      return bg >= 8 ? 'light' : 'dark';
    }
  }

  // macOS Terminal.app sets TERM_PROGRAM
  const termProgram = process.env['TERM_PROGRAM'] ?? '';

  // iterm2 can report via a special escape but env is simpler
  if (process.env['ITERM_PROFILE']?.toLowerCase().includes('light')) {
    return 'light';
  }

  // VS Code integrated terminal
  if (termProgram === 'vscode') {
    const vscodeTheme = process.env['VSCODE_THEME_KIND'];
    if (vscodeTheme === 'vscode-light' || vscodeTheme === 'vscode-high-contrast-light') {
      return 'light';
    }
    return 'dark';
  }

  // Default to dark — safest assumption for CLI tools
  return 'dark';
}

// ── resolveColor ─────────────────────────────────────────────────────

/**
 * Resolve a named color key to its hex code for the given theme mode.
 *
 * If the input is already a hex color (starts with '#') or an ANSI
 * color name, it is returned as-is. This allows mixing named keys
 * with raw values in component props.
 */
export function resolveColor(
  colorKeyOrRaw: string | undefined,
  mode: ResolvedThemeMode,
  theme: Theme = pfaaTheme,
): string | undefined {
  if (colorKeyOrRaw === undefined) return undefined;

  // Pass through raw hex, rgb(), and standard CSS/ANSI names
  if (
    colorKeyOrRaw.startsWith('#') ||
    colorKeyOrRaw.startsWith('rgb') ||
    colorKeyOrRaw === 'transparent'
  ) {
    return colorKeyOrRaw;
  }

  const palette = theme[mode];
  if (colorKeyOrRaw in palette) {
    return palette[colorKeyOrRaw as ColorKey];
  }

  // Unknown key — return as-is so Ink can try to interpret it
  return colorKeyOrRaw;
}

// ── Theme context ────────────────────────────────────────────────────

interface ThemeContextValue {
  /** The resolved mode ('light' | 'dark'), never 'auto'. */
  resolvedMode: ResolvedThemeMode;
  /** The user's raw preference, which may be 'auto'. */
  preference: ThemeMode;
  /** Full theme object. */
  theme: Theme;
  /** Update the theme preference. */
  setTheme: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

// ── ThemeProvider ────────────────────────────────────────────────────

export interface ThemeProviderProps {
  /** Initial theme mode. Defaults to 'auto'. */
  mode?: ThemeMode;
  /** Optional custom theme. Defaults to pfaaTheme. */
  theme?: Theme;
  children: React.ReactNode;
}

/**
 * Provides theme context to the component tree.
 *
 * When `mode` is 'auto', the provider detects the terminal background
 * at mount time and resolves to 'light' or 'dark'.
 */
export function ThemeProvider({
  mode: initialMode = 'auto',
  theme = pfaaTheme,
  children,
}: ThemeProviderProps) {
  const [preference, setPreference] = useState<ThemeMode>(initialMode);

  const resolvedMode: ResolvedThemeMode = useMemo(() => {
    if (preference === 'auto') {
      return detectTerminalTheme();
    }
    return preference;
  }, [preference]);

  const setTheme = useCallback((next: ThemeMode) => {
    setPreference(next);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ resolvedMode, preference, theme, setTheme }),
    [resolvedMode, preference, theme, setTheme],
  );

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

// ── useTheme hook ────────────────────────────────────────────────────

/**
 * Access the current theme.
 *
 * Returns a tuple of `[resolvedMode, setTheme]` for the common case,
 * plus the full context value for advanced usage.
 *
 * @example
 * ```tsx
 * const [mode, setTheme] = useTheme();
 * setTheme('dark');
 * ```
 */
export function useTheme(): [ResolvedThemeMode, (mode: ThemeMode) => void] {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme() must be used within a <ThemeProvider>');
  }
  return [ctx.resolvedMode, ctx.setTheme];
}

/**
 * Access the full theme context including the palette and user preference.
 */
export function useThemeContext(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useThemeContext() must be used within a <ThemeProvider>');
  }
  return ctx;
}

// ── Internal: resolve helper with context ────────────────────────────

function useResolvedColor(colorKeyOrRaw: string | undefined): string | undefined {
  const ctx = useContext(ThemeContext);
  if (!ctx) return colorKeyOrRaw;
  return resolveColor(colorKeyOrRaw, ctx.resolvedMode, ctx.theme);
}

// ── ThemedBox ────────────────────────────────────────────────────────

/**
 * Extended Box props that accept named color keys for border and
 * background colors. Keys are resolved against the active palette.
 */
export interface ThemedBoxProps extends Omit<BoxProps, 'borderColor'> {
  /** Named color key or raw hex for border. */
  borderColor?: string;
  /** Named color key or raw hex for background. Mapped to Ink's internal handling. */
  backgroundColor?: string;
  children?: React.ReactNode;
}

/**
 * Ink Box wrapper that resolves PFAA color keys.
 *
 * @example
 * ```tsx
 * <ThemedBox borderStyle="round" borderColor="emerald" backgroundColor="bg">
 *   <ThemedText color="gold">Hello</ThemedText>
 * </ThemedBox>
 * ```
 */
export function ThemedBox({
  borderColor,
  backgroundColor,
  children,
  ...rest
}: ThemedBoxProps) {
  const resolvedBorder = useResolvedColor(borderColor);
  const resolvedBg = useResolvedColor(backgroundColor);

  // Ink's Box doesn't have a direct backgroundColor prop on all versions,
  // but borderColor is well supported. We pass through what we can.
  const boxProps: Record<string, unknown> = { ...rest };
  if (resolvedBorder !== undefined) {
    boxProps.borderColor = resolvedBorder;
  }

  return (
    <Box {...boxProps}>
      {resolvedBg !== undefined ? (
        <Box flexDirection="column" flexGrow={1}>
          {children}
        </Box>
      ) : (
        children
      )}
    </Box>
  );
}

// ── ThemedText ───────────────────────────────────────────────────────

/**
 * Extended Text props that accept named color keys.
 */
export interface ThemedTextProps extends Omit<TextProps, 'color' | 'backgroundColor'> {
  /** Named color key or raw hex for text color. */
  color?: string;
  /** Named color key or raw hex for text background. */
  backgroundColor?: string;
  children?: React.ReactNode;
}

/**
 * Ink Text wrapper that resolves PFAA color keys.
 *
 * @example
 * ```tsx
 * <ThemedText color="success" bold>All checks passed</ThemedText>
 * <ThemedText color="muted">12 seconds ago</ThemedText>
 * ```
 */
export function ThemedText({
  color,
  backgroundColor,
  children,
  ...rest
}: ThemedTextProps) {
  const resolvedColor = useResolvedColor(color);
  const resolvedBg = useResolvedColor(backgroundColor);

  const textProps: TextProps = { ...rest };
  if (resolvedColor !== undefined) {
    (textProps as Record<string, unknown>)['color'] = resolvedColor;
  }
  if (resolvedBg !== undefined) {
    (textProps as Record<string, unknown>)['backgroundColor'] = resolvedBg;
  }

  return <Text {...textProps}>{children}</Text>;
}

// ── Utility: get current palette ─────────────────────────────────────

/**
 * Hook that returns the active color palette for the resolved theme.
 */
export function usePalette(): ColorMap {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    // Fallback to dark palette outside provider
    return pfaaTheme.dark;
  }
  return ctx.theme[ctx.resolvedMode];
}

/**
 * Hook that returns a resolver function bound to the current theme.
 * Useful when you need to resolve many colors in one render.
 */
export function useColorResolver(): (key: string | undefined) => string | undefined {
  const ctx = useContext(ThemeContext);
  return useCallback(
    (key: string | undefined) => {
      if (!ctx) return key;
      return resolveColor(key, ctx.resolvedMode, ctx.theme);
    },
    [ctx],
  );
}
