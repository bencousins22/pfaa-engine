/**
 * PFAA TUI Hooks — React hooks for terminal UI rendering
 *
 * Production-quality hooks that follow Ink/React 19 patterns with
 * useSyncExternalStore for tear-free reads from external sources.
 *
 * Hooks:
 *   useAnimationFrame  — Shared global clock for synchronized spinners/animations
 *   useTerminalSize    — Reactive terminal dimensions with resize tracking
 *   useSticky          — Auto-scroll that pauses when user scrolls up
 *   useDebouncedValue  — Debounce state changes to reduce render churn
 *   useKeymap          — Declarative key-combo bindings
 */

import {
  useRef,
  useEffect,
  useState,
  useCallback,
  useSyncExternalStore,
  type MutableRefObject,
} from 'react';
import { useInput, useStdout } from 'ink';

// ── useAnimationFrame ──────────────────────────────────────────────────

/**
 * Shared global animation clock. All subscribers tick together so that
 * every spinner in the UI stays in sync — no per-component setInterval.
 *
 * The clock starts on first subscription and stops when the last one
 * unsubscribes, so it costs zero CPU when nothing is animating.
 */

interface AnimationClock {
  /** Monotonic frame time (ms since clock start) */
  frameTime: number;
  /** Number of ticks since start */
  frameCount: number;
  /** Set of subscriber callbacks */
  listeners: Set<() => void>;
  /** Active interval handle, or null when paused */
  timer: ReturnType<typeof setInterval> | null;
  /** Current interval in ms */
  intervalMs: number;
}

const globalClock: AnimationClock = {
  frameTime: 0,
  frameCount: 0,
  listeners: new Set(),
  timer: null,
  intervalMs: 80,
};

function clockSubscribe(callback: () => void): () => void {
  globalClock.listeners.add(callback);

  // Start the clock on first subscriber
  if (globalClock.listeners.size === 1 && globalClock.timer === null) {
    globalClock.frameTime = 0;
    globalClock.frameCount = 0;
    globalClock.timer = setInterval(() => {
      globalClock.frameTime += globalClock.intervalMs;
      globalClock.frameCount += 1;
      for (const fn of globalClock.listeners) fn();
    }, globalClock.intervalMs);
  }

  return () => {
    globalClock.listeners.delete(callback);

    // Stop when no subscribers remain
    if (globalClock.listeners.size === 0 && globalClock.timer !== null) {
      clearInterval(globalClock.timer);
      globalClock.timer = null;
    }
  };
}

function clockGetSnapshot(): number {
  return globalClock.frameCount;
}

/**
 * Synchronised animation frame hook.
 *
 * All components sharing the same global clock will re-render on the
 * same tick, keeping spinners and progress bars visually aligned.
 *
 * @param intervalMs - Tick interval in milliseconds (default 80).
 *   Changing this after mount re-configures the shared clock.
 * @returns A tuple of `[frameRef, frameTime]` where `frameRef` is a
 *   stable ref holding the current frame count, and `frameTime` is the
 *   elapsed time in ms since the clock started.
 *
 * @example
 * ```tsx
 * const FRAMES = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'];
 * function Spinner() {
 *   const [frameRef, frameTime] = useAnimationFrame(80);
 *   const char = FRAMES[frameRef.current % FRAMES.length];
 *   return <Text>{char}</Text>;
 * }
 * ```
 */
export function useAnimationFrame(
  intervalMs: number = 80,
): [MutableRefObject<number>, number] {
  const frameRef = useRef(0);

  // Reconfigure the global clock interval when requested
  useEffect(() => {
    if (globalClock.intervalMs !== intervalMs && globalClock.timer !== null) {
      clearInterval(globalClock.timer);
      globalClock.intervalMs = intervalMs;
      globalClock.timer = setInterval(() => {
        globalClock.frameTime += globalClock.intervalMs;
        globalClock.frameCount += 1;
        for (const fn of globalClock.listeners) fn();
      }, intervalMs);
    }
    globalClock.intervalMs = intervalMs;
  }, [intervalMs]);

  const frameCount = useSyncExternalStore(clockSubscribe, clockGetSnapshot);

  frameRef.current = frameCount;

  return [frameRef, globalClock.frameTime];
}

// ── useTerminalSize ────────────────────────────────────────────────────

interface TerminalSize {
  /** Terminal width in columns */
  columns: number;
  /** Terminal height in rows */
  rows: number;
}

/**
 * External store for terminal dimensions. Uses `process.stdout` directly
 * so it works even outside an Ink render tree (e.g. in tests with a
 * mock stdout).
 */

let cachedSize: TerminalSize = {
  columns: process.stdout.columns ?? 80,
  rows: process.stdout.rows ?? 24,
};

const sizeListeners = new Set<() => void>();

function handleResize(): void {
  const next: TerminalSize = {
    columns: process.stdout.columns ?? 80,
    rows: process.stdout.rows ?? 24,
  };
  if (next.columns !== cachedSize.columns || next.rows !== cachedSize.rows) {
    cachedSize = next;
    for (const fn of sizeListeners) fn();
  }
}

// Attach once at module load — harmless if stdout is not a TTY
if (process.stdout.isTTY) {
  process.stdout.on('resize', handleResize);
}

function sizeSubscribe(callback: () => void): () => void {
  sizeListeners.add(callback);
  return () => { sizeListeners.delete(callback); };
}

function sizeGetSnapshot(): TerminalSize {
  return cachedSize;
}

/**
 * Tracks terminal width and height reactively.
 *
 * Uses `useSyncExternalStore` so the component re-renders exactly once
 * per resize event with no extra state or effect overhead.
 *
 * @returns An object with `columns` and `rows`.
 *
 * @example
 * ```tsx
 * function Layout() {
 *   const { columns, rows } = useTerminalSize();
 *   return <Text>Terminal is {columns}x{rows}</Text>;
 * }
 * ```
 */
export function useTerminalSize(): TerminalSize {
  return useSyncExternalStore(sizeSubscribe, sizeGetSnapshot);
}

// ── useSticky ──────────────────────────────────────────────────────────

interface StickyState {
  /** Whether auto-scroll is active (user has not scrolled up) */
  isSticky: boolean;
  /** Total content height (set by the consumer) */
  contentHeight: number;
  /** Current scroll offset */
  scrollOffset: number;
}

/**
 * Auto-scroll hook that keeps content pinned to the bottom until the
 * user scrolls up. Scrolling back to the bottom re-enables sticky mode.
 *
 * This is the terminal equivalent of a chat window that follows new
 * messages but lets you scroll back through history.
 *
 * @param contentHeight - Total height of the content in rows.
 * @param viewportRows  - Visible viewport height (defaults to terminal rows).
 * @returns An object with scroll state and control functions.
 *
 * @example
 * ```tsx
 * function MessageLog({ messages }: { messages: string[] }) {
 *   const totalHeight = messages.length;
 *   const sticky = useSticky(totalHeight);
 *
 *   // Render only visible slice
 *   const visible = messages.slice(
 *     sticky.scrollOffset,
 *     sticky.scrollOffset + sticky.viewportRows
 *   );
 *   return <Box flexDirection="column">
 *     {visible.map((m, i) => <Text key={i}>{m}</Text>)}
 *     {!sticky.isSticky && <Text dimColor>-- scroll locked --</Text>}
 *   </Box>;
 * }
 * ```
 */
export function useSticky(
  contentHeight: number,
  viewportRows?: number,
): {
  isSticky: boolean;
  scrollOffset: number;
  viewportRows: number;
  scrollUp: () => void;
  scrollDown: () => void;
  scrollToBottom: () => void;
} {
  const { rows: termRows } = useTerminalSize();
  const effectiveViewport = viewportRows ?? termRows;

  const [state, setState] = useState<StickyState>({
    isSticky: true,
    contentHeight,
    scrollOffset: Math.max(0, contentHeight - effectiveViewport),
  });

  const stateRef = useRef(state);
  stateRef.current = state;

  // When content grows and we are sticky, follow it
  useEffect(() => {
    setState(prev => {
      if (prev.isSticky) {
        const offset = Math.max(0, contentHeight - effectiveViewport);
        return { ...prev, contentHeight, scrollOffset: offset };
      }
      return { ...prev, contentHeight };
    });
  }, [contentHeight, effectiveViewport]);

  const scrollUp = useCallback(() => {
    setState(prev => {
      const next = Math.max(0, prev.scrollOffset - 1);
      const isSticky = next >= Math.max(0, prev.contentHeight - effectiveViewport);
      return { ...prev, scrollOffset: next, isSticky };
    });
  }, [effectiveViewport]);

  const scrollDown = useCallback(() => {
    setState(prev => {
      const maxOffset = Math.max(0, prev.contentHeight - effectiveViewport);
      const next = Math.min(maxOffset, prev.scrollOffset + 1);
      const isSticky = next >= maxOffset;
      return { ...prev, scrollOffset: next, isSticky };
    });
  }, [effectiveViewport]);

  const scrollToBottom = useCallback(() => {
    setState(prev => ({
      ...prev,
      isSticky: true,
      scrollOffset: Math.max(0, prev.contentHeight - effectiveViewport),
    }));
  }, [effectiveViewport]);

  return {
    isSticky: state.isSticky,
    scrollOffset: state.scrollOffset,
    viewportRows: effectiveViewport,
    scrollUp,
    scrollDown,
    scrollToBottom,
  };
}

// ── useDebouncedValue ──────────────────────────────────────────────────

/**
 * Debounces a value so downstream consumers only re-render after the
 * value has settled for `delayMs` milliseconds.
 *
 * Useful for search inputs, streaming text buffers, or any rapidly
 * changing value where you want to throttle expensive re-renders.
 *
 * @param value   - The source value that may change frequently.
 * @param delayMs - Debounce window in milliseconds (default 150).
 * @returns The debounced value.
 *
 * @example
 * ```tsx
 * function Search({ query }: { query: string }) {
 *   const debouncedQuery = useDebouncedValue(query, 200);
 *   // `debouncedQuery` only updates 200ms after the user stops typing
 *   return <Results query={debouncedQuery} />;
 * }
 * ```
 */
export function useDebouncedValue<T>(value: T, delayMs: number = 150): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

// ── useKeymap ──────────────────────────────────────────────────────────

/**
 * Key descriptor for matching keyboard input.
 *
 * Modifier flags are optional and default to false. The `key` field
 * matches the raw character for printable keys, or named keys like
 * 'return', 'escape', 'tab', 'backspace', 'delete', 'upArrow',
 * 'downArrow', 'leftArrow', 'rightArrow'.
 */
export interface KeyCombo {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
}

/** Keybinding map: combo descriptors to handler functions. */
export type KeyBindings = Record<string, {
  combo: KeyCombo;
  handler: () => void;
}>;

/**
 * Parse a human-readable key string into a KeyCombo.
 *
 * Supported formats:
 *   "ctrl+c", "meta+k", "shift+tab", "return", "escape",
 *   "ctrl+shift+z", "upArrow", "a", "?"
 *
 * @internal
 */
function parseKeyString(raw: string): KeyCombo {
  const parts = raw.toLowerCase().split('+');
  const combo: KeyCombo = {
    key: parts[parts.length - 1],
    ctrl: false,
    meta: false,
    shift: false,
  };

  for (let i = 0; i < parts.length - 1; i++) {
    const mod = parts[i];
    if (mod === 'ctrl') combo.ctrl = true;
    else if (mod === 'meta' || mod === 'alt') combo.meta = true;
    else if (mod === 'shift') combo.shift = true;
  }

  return combo;
}

/**
 * Check if an Ink input event matches a KeyCombo descriptor.
 * @internal
 */
function matchesCombo(
  input: string,
  key: {
    upArrow: boolean;
    downArrow: boolean;
    leftArrow: boolean;
    rightArrow: boolean;
    return: boolean;
    escape: boolean;
    tab: boolean;
    backspace: boolean;
    delete: boolean;
    ctrl: boolean;
    meta: boolean;
    shift: boolean;
  },
  combo: KeyCombo,
): boolean {
  // Modifier matching
  if (combo.ctrl && !key.ctrl) return false;
  if (combo.meta && !key.meta) return false;
  if (combo.shift && !key.shift) return false;

  // If modifiers are not requested, don't require them to be absent.
  // This matches Ink's own useInput behavior where Ctrl+C fires with
  // input='c' and key.ctrl=true.

  // Named key matching
  const named = combo.key;
  if (named === 'return' || named === 'enter') return key.return;
  if (named === 'escape' || named === 'esc') return key.escape;
  if (named === 'tab') return key.tab;
  if (named === 'backspace') return key.backspace;
  if (named === 'delete') return key.delete;
  if (named === 'uparrow' || named === 'up') return key.upArrow;
  if (named === 'downarrow' || named === 'down') return key.downArrow;
  if (named === 'leftarrow' || named === 'left') return key.leftArrow;
  if (named === 'rightarrow' || named === 'right') return key.rightArrow;

  // Printable character matching
  return input.toLowerCase() === named;
}

/**
 * Declarative keybinding hook. Maps key combos to handler functions
 * without requiring manual `useInput` plumbing.
 *
 * Handlers are stored in a ref so they can be updated without
 * re-registering the input listener.
 *
 * Accepts either a structured `KeyBindings` object or a simpler
 * `Record<string, () => void>` where the key is a human-readable
 * combo string like `"ctrl+c"` or `"escape"`.
 *
 * @param bindings - Map of key-combo strings or KeyCombo objects to handlers.
 * @param options  - Optional `{ active?: boolean }` to enable/disable.
 *
 * @example
 * ```tsx
 * function App() {
 *   useKeymap({
 *     'ctrl+c':   () => process.exit(0),
 *     'escape':   () => setMode('normal'),
 *     'ctrl+k':   () => clearScreen(),
 *     'upArrow':  () => scrollUp(),
 *     'downArrow':() => scrollDown(),
 *   });
 *   return <Text>Press keys...</Text>;
 * }
 * ```
 */
export function useKeymap(
  bindings: Record<string, (() => void) | { combo: KeyCombo; handler: () => void }>,
  options?: { active?: boolean },
): void {
  const bindingsRef = useRef(bindings);
  bindingsRef.current = bindings;

  const isActive = options?.active ?? true;

  useInput(
    (input, key) => {
      const current = bindingsRef.current;

      for (const [label, entry] of Object.entries(current)) {
        let combo: KeyCombo;
        let handler: () => void;

        if (typeof entry === 'function') {
          combo = parseKeyString(label);
          handler = entry;
        } else {
          combo = entry.combo;
          handler = entry.handler;
        }

        if (matchesCombo(input, key, combo)) {
          handler();
          return; // first match wins
        }
      }
    },
    { isActive },
  );
}
