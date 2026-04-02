/**
 * PFAA ScrollView — Scrollable viewport with virtual list support
 *
 * Components:
 *   ScrollView   — wraps children in a scrollable, keyboard-navigable viewport
 *   VirtualList  — renders only visible items from a large list (+ overscan buffer)
 *
 * Hooks:
 *   useScrollHandle() — imperative scroll control ref
 */

import React, {
  type ReactNode,
  type ReactElement,
  type Ref,
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
  useImperativeHandle,
  forwardRef,
  createRef,
} from 'react';
import { Box, Text, useInput, useStdout } from 'ink';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ScrollHandle {
  /** Scroll to an absolute Y offset (clamped to valid range). */
  scrollTo(y: number): void;
  /** Scroll by a relative delta (positive = down). */
  scrollBy(dy: number): void;
  /** Jump to the very bottom. */
  scrollToBottom(): void;
  /** Returns true when the viewport is at (or within 1 row of) the bottom. */
  isAtBottom(): boolean;
  /** Current scroll offset from the top. */
  getScrollTop(): number;
  /** Total content height (rows). */
  getScrollHeight(): number;
}

export interface ScrollViewProps {
  /** Fixed viewport height in rows. Defaults to `stdout.rows - 4` (room for header + footer). */
  height?: number;
  /** When true (default), new content automatically scrolls the viewport to the bottom. */
  stickyScroll?: boolean;
  /** Disable keyboard input handling (arrow keys, page up/down). */
  disableInput?: boolean;
  /** Number of rows to scroll per arrow-key press. Default: 1. */
  scrollStep?: number;
  /** Number of rows to scroll per page-up / page-down press. Default: half viewport. */
  pageStep?: number;
  /** Show a scrollbar gutter on the right edge. Default: true. */
  showScrollbar?: boolean;
  children: ReactNode;
}

export interface VirtualListProps<T> {
  /** The full data array. */
  items: readonly T[];
  /** Fixed height of each item in rows. */
  itemHeight: number;
  /** Render a single item. `index` is the position in `items`. */
  renderItem: (item: T, index: number) => ReactElement;
  /** Extra items to render above and below the visible window. Default: 3. */
  overscan?: number;
  /** Viewport height override (defaults to terminal height - 4). */
  height?: number;
  /** Auto-scroll to bottom when items change. Default: true. */
  stickyScroll?: boolean;
  /** Show scrollbar. Default: true. */
  showScrollbar?: boolean;
  /** Ref for imperative scroll control. */
  scrollRef?: Ref<ScrollHandle>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function useTerminalHeight(): number {
  const { stdout } = useStdout();
  return stdout?.rows ?? 24;
}

// ---------------------------------------------------------------------------
// Scrollbar renderer
// ---------------------------------------------------------------------------

function Scrollbar({
  viewportHeight,
  contentHeight,
  scrollTop,
}: {
  viewportHeight: number;
  contentHeight: number;
  scrollTop: number;
}) {
  if (contentHeight <= viewportHeight) {
    // No scrollbar needed — fill with spaces.
    const lines = Array.from({ length: viewportHeight }, () => ' ');
    return (
      <Box flexDirection="column" width={1}>
        {lines.map((_, i) => (
          <Text key={i}> </Text>
        ))}
      </Box>
    );
  }

  const trackHeight = viewportHeight;
  const thumbHeight = Math.max(1, Math.round((viewportHeight / contentHeight) * trackHeight));
  const maxScroll = contentHeight - viewportHeight;
  const thumbOffset = maxScroll > 0
    ? Math.round((scrollTop / maxScroll) * (trackHeight - thumbHeight))
    : 0;

  const lines: string[] = [];
  for (let i = 0; i < trackHeight; i++) {
    if (i >= thumbOffset && i < thumbOffset + thumbHeight) {
      lines.push('\u2588'); // full block
    } else {
      lines.push('\u2502'); // light vertical
    }
  }

  return (
    <Box flexDirection="column" width={1}>
      {lines.map((ch, i) => (
        <Text key={i} color={ch === '\u2588' ? '#E8D5B7' : '#48484A'}>{ch}</Text>
      ))}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// ScrollView
// ---------------------------------------------------------------------------

/**
 * `ScrollView` wraps arbitrary children in a fixed-height viewport that can be
 * scrolled with arrow keys, page up/down, home/end.
 *
 * Content is rendered into an off-screen Ink `<Box>` and then sliced to the
 * visible window via Ink's `overflow="hidden"` + offset.
 *
 * Use `useScrollHandle()` to obtain an imperative ref for programmatic control.
 */
export const ScrollView = forwardRef<ScrollHandle, ScrollViewProps>(
  function ScrollView(props, ref) {
    const {
      height: heightProp,
      stickyScroll = true,
      disableInput = false,
      scrollStep = 1,
      pageStep: pageStepProp,
      showScrollbar = true,
      children,
    } = props;

    const termRows = useTerminalHeight();
    const viewportHeight = heightProp ?? Math.max(4, termRows - 4);
    const pageStep = pageStepProp ?? Math.max(1, Math.floor(viewportHeight / 2));

    // We track content height via a ref updated by the content wrapper.
    // For Ink, we estimate content height from React children count.
    const [scrollTop, setScrollTop] = useState(0);
    const [contentHeight, setContentHeight] = useState(0);
    const wasAtBottomRef = useRef(true);
    const prevChildCountRef = useRef(0);

    // Estimate content height from child count (each child = 1 row minimum).
    // A more precise approach would measure rendered output, but in a terminal
    // context row-counting from children is pragmatic and fast.
    const childArray = React.Children.toArray(children);
    const estimatedHeight = childArray.length;

    useEffect(() => {
      setContentHeight(estimatedHeight);
    }, [estimatedHeight]);

    const maxScroll = Math.max(0, contentHeight - viewportHeight);

    // Sticky scroll: when content grows and we were at the bottom, stay there.
    useEffect(() => {
      if (stickyScroll && wasAtBottomRef.current) {
        setScrollTop(maxScroll);
      }
    }, [contentHeight, maxScroll, stickyScroll]);

    // Track whether we are at the bottom after every scroll change.
    useEffect(() => {
      wasAtBottomRef.current = scrollTop >= maxScroll - 1;
    }, [scrollTop, maxScroll]);

    // Clamp scrollTop when maxScroll shrinks.
    useEffect(() => {
      setScrollTop((prev) => clamp(prev, 0, maxScroll));
    }, [maxScroll]);

    // Imperative handle ---------------------------------------------------

    const scrollTo = useCallback(
      (y: number) => setScrollTop(clamp(y, 0, maxScroll)),
      [maxScroll],
    );

    const scrollBy = useCallback(
      (dy: number) => setScrollTop((prev) => clamp(prev + dy, 0, maxScroll)),
      [maxScroll],
    );

    const scrollToBottom = useCallback(
      () => setScrollTop(maxScroll),
      [maxScroll],
    );

    const isAtBottom = useCallback(
      () => scrollTop >= maxScroll - 1,
      [scrollTop, maxScroll],
    );

    const getScrollTop = useCallback(() => scrollTop, [scrollTop]);
    const getScrollHeight = useCallback(() => contentHeight, [contentHeight]);

    useImperativeHandle(ref, () => ({
      scrollTo,
      scrollBy,
      scrollToBottom,
      isAtBottom,
      getScrollTop,
      getScrollHeight,
    }), [scrollTo, scrollBy, scrollToBottom, isAtBottom, getScrollTop, getScrollHeight]);

    // Keyboard input ------------------------------------------------------

    useInput(
      (input, key) => {
        if (key.upArrow) {
          scrollBy(-scrollStep);
        } else if (key.downArrow) {
          scrollBy(scrollStep);
        } else if (key.pageUp || (key.meta && key.upArrow)) {
          scrollBy(-pageStep);
        } else if (key.pageDown || (key.meta && key.downArrow)) {
          scrollBy(pageStep);
        } else if (input === 'g' && key.shift) {
          // Shift+G = end (vim-style)
          scrollToBottom();
        } else if (input === 'g') {
          // gg = home — single g approximation
          scrollTo(0);
        }
      },
      { isActive: !disableInput },
    );

    // Render --------------------------------------------------------------

    // Slice children to the visible window.
    const visibleChildren = childArray.slice(scrollTop, scrollTop + viewportHeight);

    // Pad if content is shorter than viewport.
    const padRows = viewportHeight - visibleChildren.length;

    return (
      <Box flexDirection="row" height={viewportHeight}>
        <Box flexDirection="column" flexGrow={1} overflow="hidden">
          {visibleChildren.map((child, i) => (
            <Box key={scrollTop + i} flexShrink={0}>
              {child}
            </Box>
          ))}
          {padRows > 0 &&
            Array.from({ length: padRows }, (_, i) => (
              <Text key={`pad-${i}`}> </Text>
            ))}
        </Box>
        {showScrollbar && (
          <Scrollbar
            viewportHeight={viewportHeight}
            contentHeight={contentHeight}
            scrollTop={scrollTop}
          />
        )}
      </Box>
    );
  },
);

// ---------------------------------------------------------------------------
// useScrollHandle — convenience hook to create + consume a ScrollHandle ref
// ---------------------------------------------------------------------------

/**
 * Returns a `React.RefObject<ScrollHandle>` that can be passed to
 * `<ScrollView ref={...}>` or `<VirtualList scrollRef={...}>`.
 *
 * ```tsx
 * const handle = useScrollHandle();
 * <ScrollView ref={handle}>...</ScrollView>
 * // later:
 * handle.current?.scrollToBottom();
 * ```
 */
export function useScrollHandle(): React.RefObject<ScrollHandle> {
  return useRef<ScrollHandle>(null!);
}

// ---------------------------------------------------------------------------
// VirtualList
// ---------------------------------------------------------------------------

/**
 * `VirtualList` efficiently renders a large homogeneous list by mounting only
 * the items visible within the viewport plus an overscan buffer.
 *
 * Each item must have a fixed `itemHeight` (in terminal rows). The component
 * handles keyboard scrolling and an optional scrollbar.
 */
export function VirtualList<T>(props: VirtualListProps<T>): ReactElement {
  const {
    items,
    itemHeight,
    renderItem,
    overscan = 3,
    height: heightProp,
    stickyScroll = true,
    showScrollbar = true,
    scrollRef: externalRef,
  } = props;

  const termRows = useTerminalHeight();
  const viewportHeight = heightProp ?? Math.max(4, termRows - 4);
  const pageStep = Math.max(1, Math.floor(viewportHeight / 2));

  const totalHeight = items.length * itemHeight;
  const maxScroll = Math.max(0, totalHeight - viewportHeight);

  const [scrollTop, setScrollTop] = useState(0);
  const wasAtBottomRef = useRef(true);
  const prevItemCountRef = useRef(items.length);

  // Sticky scroll on new items.
  useEffect(() => {
    if (stickyScroll && items.length > prevItemCountRef.current && wasAtBottomRef.current) {
      setScrollTop(maxScroll);
    }
    prevItemCountRef.current = items.length;
  }, [items.length, maxScroll, stickyScroll]);

  useEffect(() => {
    wasAtBottomRef.current = scrollTop >= maxScroll - 1;
  }, [scrollTop, maxScroll]);

  useEffect(() => {
    setScrollTop((prev) => clamp(prev, 0, maxScroll));
  }, [maxScroll]);

  // Imperative API --------------------------------------------------------

  const scrollTo = useCallback(
    (y: number) => setScrollTop(clamp(y, 0, maxScroll)),
    [maxScroll],
  );

  const scrollBy = useCallback(
    (dy: number) => setScrollTop((prev) => clamp(prev + dy, 0, maxScroll)),
    [maxScroll],
  );

  const scrollToBottom = useCallback(() => setScrollTop(maxScroll), [maxScroll]);

  const isAtBottom = useCallback(() => scrollTop >= maxScroll - 1, [scrollTop, maxScroll]);
  const getScrollTop = useCallback(() => scrollTop, [scrollTop]);
  const getScrollHeight = useCallback(() => totalHeight, [totalHeight]);

  // Expose handle via the passed-in ref.
  const internalRef = useRef<ScrollHandle>(null!);
  useImperativeHandle(
    externalRef ?? internalRef,
    () => ({
      scrollTo,
      scrollBy,
      scrollToBottom,
      isAtBottom,
      getScrollTop,
      getScrollHeight,
    }),
    [scrollTo, scrollBy, scrollToBottom, isAtBottom, getScrollTop, getScrollHeight],
  );

  // Keyboard input --------------------------------------------------------

  useInput((input, key) => {
    if (key.upArrow) {
      scrollBy(-itemHeight);
    } else if (key.downArrow) {
      scrollBy(itemHeight);
    } else if (key.pageUp || (key.meta && key.upArrow)) {
      scrollBy(-pageStep);
    } else if (key.pageDown || (key.meta && key.downArrow)) {
      scrollBy(pageStep);
    } else if (input === 'g' && key.shift) {
      scrollToBottom();
    } else if (input === 'g') {
      scrollTo(0);
    }
  });

  // Compute visible slice -------------------------------------------------

  const { startIndex, endIndex, topPad, bottomPad } = useMemo(() => {
    const firstVisible = Math.floor(scrollTop / itemHeight);
    const lastVisible = Math.ceil((scrollTop + viewportHeight) / itemHeight) - 1;

    const start = Math.max(0, firstVisible - overscan);
    const end = Math.min(items.length - 1, lastVisible + overscan);

    return {
      startIndex: start,
      endIndex: end,
      topPad: start * itemHeight,
      bottomPad: Math.max(0, (items.length - 1 - end) * itemHeight),
    };
  }, [scrollTop, viewportHeight, itemHeight, overscan, items.length]);

  // Render ----------------------------------------------------------------

  const visibleItems = items.slice(startIndex, endIndex + 1);

  return (
    <Box flexDirection="row" height={viewportHeight}>
      <Box flexDirection="column" flexGrow={1} overflow="hidden">
        {/* Top spacer — accounts for items above the rendered window */}
        {topPad > 0 && <Box height={topPad} />}

        {visibleItems.map((item, i) => {
          const index = startIndex + i;
          return (
            <Box key={index} height={itemHeight} flexShrink={0}>
              {renderItem(item, index)}
            </Box>
          );
        })}

        {/* Bottom spacer */}
        {bottomPad > 0 && <Box height={bottomPad} />}
      </Box>
      {showScrollbar && (
        <Scrollbar
          viewportHeight={viewportHeight}
          contentHeight={totalHeight}
          scrollTop={scrollTop}
        />
      )}
    </Box>
  );
}
