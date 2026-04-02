/**
 * PFAA InputPrompt — Production-grade terminal input with full cursor navigation,
 * command history, tab completion, multiline editing, and readline-style keybindings.
 *
 * Features:
 *   - Left/Right arrow cursor movement, Home/End, Ctrl+A/E
 *   - Up/Down command history with Ctrl+R reverse search
 *   - Tab completion with inline ghost suggestion
 *   - Shift+Enter multiline, Enter to submit
 *   - Ctrl+U clear line, Ctrl+W delete word, Ctrl+K kill to end
 *   - Ctrl+C context-aware (clear line or exit hint)
 *   - Paste support (multi-character input bursts)
 *   - Visual block cursor (inverse character at position)
 *   - LIVE / SIM mode indicator from app context
 */

import React, { useState, useRef, useCallback, useMemo } from 'react';
import { Box, Text, useInput } from 'ink';
import { Spinner } from './Spinner.js';
import { useApp } from '../context.js';

// ── Constants ─────────────────────────────────────────────────────────

const MAX_HISTORY = 200;

const COMPLETIONS = [
  'run', 'status', 'bench', 'team', 'swarm', 'memory', 'tools', 'exec',
  'learn', 'explore', 'help', 'exit', 'clear', 'self-build', 'warmup',
  'sessions',
] as const;

// ── Types ─────────────────────────────────────────────────────────────

interface InputPromptProps {
  onSubmit: (input: string) => void;
  onExit?: () => void;
}

interface EditorState {
  /** Full buffer text (may contain newlines for multiline) */
  text: string;
  /** Cursor position as character offset into text */
  cursor: number;
}

// ── Helpers ───────────────────────────────────────────────────────────

/** Find the start of the word before `pos` in `text`. */
function wordBoundaryBefore(text: string, pos: number): number {
  if (pos === 0) return 0;
  let i = pos - 1;
  // Skip trailing whitespace
  while (i > 0 && /\s/.test(text[i]!)) i--;
  // Skip word characters
  while (i > 0 && /\S/.test(text[i - 1]!)) i--;
  return Math.max(0, i);
}

/** Return the first COMPLETIONS entry matching a prefix, or null. */
function matchCompletion(input: string): string | null {
  const trimmed = input.trimStart().toLowerCase();
  if (!trimmed) return null;
  // Only complete the first token (command name)
  const firstSpace = trimmed.indexOf(' ');
  if (firstSpace !== -1) return null;
  for (const cmd of COMPLETIONS) {
    if (cmd.startsWith(trimmed) && cmd !== trimmed) return cmd;
  }
  return null;
}

/** Split editor text into visual lines for rendering. */
function splitLines(text: string): string[] {
  const lines = text.split('\n');
  return lines.length === 0 ? [''] : lines;
}

// ── Component ─────────────────────────────────────────────────────────

export function InputPrompt({ onSubmit, onExit }: InputPromptProps) {
  const { state } = useApp();

  // Editor buffer
  const [editor, setEditor] = useState<EditorState>({ text: '', cursor: 0 });

  // Command history
  const historyRef = useRef<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  // Stash the in-progress input when browsing history
  const stashRef = useRef('');

  // Reverse search state
  const [searchMode, setSearchMode] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Exit hint flag (Ctrl+C on empty line)
  const [showExitHint, setShowExitHint] = useState(false);

  // ── Derived values ───────────────────────────────────────────────

  const ghostCompletion = useMemo(
    () => matchCompletion(editor.text),
    [editor.text],
  );

  const modeLabel = state.isLive ? 'LIVE' : 'SIM';
  const modeColor = state.isLive ? '#A8E6CF' : '#F8F8FF';

  // ── History helpers ──────────────────────────────────────────────

  const pushHistory = useCallback((entry: string) => {
    const h = historyRef.current;
    // Deduplicate consecutive
    if (h.length === 0 || h[0] !== entry) {
      historyRef.current = [entry, ...h].slice(0, MAX_HISTORY);
    }
  }, []);

  const navigateHistory = useCallback((direction: 'up' | 'down') => {
    const h = historyRef.current;
    if (h.length === 0) return;

    setHistoryIdx(prev => {
      let next: number;
      if (direction === 'up') {
        if (prev === -1) {
          // Stash current input before entering history
          stashRef.current = editor.text;
        }
        next = Math.min(prev + 1, h.length - 1);
      } else {
        next = prev - 1;
      }

      if (next < 0) {
        // Restore stash
        const restored = stashRef.current;
        setEditor({ text: restored, cursor: restored.length });
        return -1;
      }

      const entry = h[next]!;
      setEditor({ text: entry, cursor: entry.length });
      return next;
    });
  }, [editor.text]);

  // ── Reverse search ──────────────────────────────────────────────

  const reverseSearchResult = useMemo(() => {
    if (!searchMode || !searchQuery) return null;
    const q = searchQuery.toLowerCase();
    return historyRef.current.find(h => h.toLowerCase().includes(q)) ?? null;
  }, [searchMode, searchQuery]);

  // ── Input handler ───────────────────────────────────────────────

  useInput((input, key) => {
    if (state.isProcessing) return;

    // Dismiss exit hint on any key
    if (showExitHint) setShowExitHint(false);

    // ── Reverse search mode ─────────────────────────────────────
    if (searchMode) {
      if (key.escape) {
        setSearchMode(false);
        setSearchQuery('');
        return;
      }
      if (key.return) {
        // Accept search result
        const result = reverseSearchResult ?? '';
        setEditor({ text: result, cursor: result.length });
        setSearchMode(false);
        setSearchQuery('');
        return;
      }
      if (key.backspace || key.delete) {
        setSearchQuery(q => q.slice(0, -1));
        return;
      }
      if (key.ctrl && input === 'r') {
        // Could cycle through matches — for now just keep searching
        return;
      }
      if (key.ctrl && input === 'c') {
        setSearchMode(false);
        setSearchQuery('');
        return;
      }
      // Append to search query
      if (input && !key.ctrl && !key.meta && !key.escape) {
        setSearchQuery(q => q + input);
      }
      return;
    }

    // ── Ctrl+R — enter reverse search ───────────────────────────
    if (key.ctrl && input === 'r') {
      setSearchMode(true);
      setSearchQuery('');
      return;
    }

    // ── Ctrl+C ──────────────────────────────────────────────────
    if (key.ctrl && input === 'c') {
      if (editor.text.length === 0) {
        setShowExitHint(true);
        if (onExit) onExit();
        return;
      }
      // Clear line
      setEditor({ text: '', cursor: 0 });
      setHistoryIdx(-1);
      return;
    }

    // ── Enter / Shift+Enter ─────────────────────────────────────
    if (key.return) {
      if (key.shift) {
        // Insert newline at cursor
        setEditor(prev => {
          const before = prev.text.slice(0, prev.cursor);
          const after = prev.text.slice(prev.cursor);
          return { text: before + '\n' + after, cursor: prev.cursor + 1 };
        });
        return;
      }
      const trimmed = editor.text.trim();
      if (!trimmed) return;
      pushHistory(trimmed);
      setHistoryIdx(-1);
      stashRef.current = '';
      onSubmit(trimmed);
      setEditor({ text: '', cursor: 0 });
      return;
    }

    // ── Tab completion ──────────────────────────────────────────
    if (key.tab) {
      if (ghostCompletion) {
        const leadingSpaces = editor.text.length - editor.text.trimStart().length;
        const completed = editor.text.slice(0, leadingSpaces) + ghostCompletion + ' ';
        setEditor({ text: completed, cursor: completed.length });
      }
      return;
    }

    // ── Backspace ───────────────────────────────────────────────
    if (key.backspace || key.delete) {
      setEditor(prev => {
        if (prev.cursor === 0) return prev;
        const before = prev.text.slice(0, prev.cursor - 1);
        const after = prev.text.slice(prev.cursor);
        return { text: before + after, cursor: prev.cursor - 1 };
      });
      return;
    }

    // ── Arrow keys ──────────────────────────────────────────────
    if (key.leftArrow) {
      if (key.ctrl || key.meta) {
        // Jump word left
        setEditor(prev => ({ ...prev, cursor: wordBoundaryBefore(prev.text, prev.cursor) }));
      } else {
        setEditor(prev => ({ ...prev, cursor: Math.max(0, prev.cursor - 1) }));
      }
      return;
    }

    if (key.rightArrow) {
      if (key.ctrl || key.meta) {
        // Jump word right
        setEditor(prev => {
          const match = prev.text.slice(prev.cursor).match(/^\s*\S+/);
          return { ...prev, cursor: match ? prev.cursor + match[0].length : prev.text.length };
        });
      } else {
        setEditor(prev => ({ ...prev, cursor: Math.min(prev.text.length, prev.cursor + 1) }));
      }
      return;
    }

    if (key.upArrow) {
      navigateHistory('up');
      return;
    }

    if (key.downArrow) {
      navigateHistory('down');
      return;
    }

    // ── Ctrl+A / Home — beginning of line ───────────────────────
    if ((key.ctrl && input === 'a') || key.home) {
      setEditor(prev => ({ ...prev, cursor: 0 }));
      return;
    }

    // ── Ctrl+E / End — end of line ──────────────────────────────
    if ((key.ctrl && input === 'e') || key.end) {
      setEditor(prev => ({ ...prev, cursor: prev.text.length }));
      return;
    }

    // ── Ctrl+U — clear entire line ──────────────────────────────
    if (key.ctrl && input === 'u') {
      setEditor({ text: '', cursor: 0 });
      return;
    }

    // ── Ctrl+K — kill from cursor to end ────────────────────────
    if (key.ctrl && input === 'k') {
      setEditor(prev => ({ text: prev.text.slice(0, prev.cursor), cursor: prev.cursor }));
      return;
    }

    // ── Ctrl+W — delete word backwards ──────────────────────────
    if (key.ctrl && input === 'w') {
      setEditor(prev => {
        const boundary = wordBoundaryBefore(prev.text, prev.cursor);
        const before = prev.text.slice(0, boundary);
        const after = prev.text.slice(prev.cursor);
        return { text: before + after, cursor: boundary };
      });
      return;
    }

    // ── Ctrl+D — delete char at cursor (or exit on empty) ──────
    if (key.ctrl && input === 'd') {
      if (editor.text.length === 0) {
        if (onExit) onExit();
        return;
      }
      setEditor(prev => {
        if (prev.cursor >= prev.text.length) return prev;
        const before = prev.text.slice(0, prev.cursor);
        const after = prev.text.slice(prev.cursor + 1);
        return { text: before + after, cursor: prev.cursor };
      });
      return;
    }

    // ── Ctrl+L — clear screen hint (noop, handled by parent) ───
    if (key.ctrl && input === 'l') return;

    // ── Escape — clear selection / cancel ───────────────────────
    if (key.escape) return;

    // ── Regular character input (including paste bursts) ────────
    if (input && !key.ctrl && !key.meta) {
      setEditor(prev => {
        const before = prev.text.slice(0, prev.cursor);
        const after = prev.text.slice(prev.cursor);
        return { text: before + input + after, cursor: prev.cursor + input.length };
      });
    }
  });

  // ── Render: Processing state ──────────────────────────────────────

  if (state.isProcessing) {
    return (
      <Box paddingX={1} gap={1}>
        <Spinner type="dots" label="Processing..." />
      </Box>
    );
  }

  // ── Render: Reverse search mode ───────────────────────────────────

  if (searchMode) {
    return (
      <Box paddingX={1} flexDirection="column">
        <Box>
          <Text color="#E8D5B7" bold>(reverse-i-search)</Text>
          <Text color="#E8D5B7">{`\`${searchQuery}\`: `}</Text>
          <Text dimColor>{reverseSearchResult ?? ''}</Text>
        </Box>
      </Box>
    );
  }

  // ── Render: Normal input ──────────────────────────────────────────

  const lines = splitLines(editor.text);
  const isMultiline = lines.length > 1;

  // Build rendered text with visual cursor
  const renderLineWithCursor = (
    lineText: string,
    cursorInLine: number | null, // null = cursor not on this line
  ): React.ReactNode[] => {
    const parts: React.ReactNode[] = [];

    if (cursorInLine === null || cursorInLine < 0) {
      // No cursor on this line
      parts.push(<Text key="text">{lineText}</Text>);
      return parts;
    }

    const before = lineText.slice(0, cursorInLine);
    const cursorChar = cursorInLine < lineText.length ? lineText[cursorInLine] : ' ';
    const after = lineText.slice(cursorInLine + 1);

    if (before) parts.push(<Text key="before">{before}</Text>);
    parts.push(<Text key="cursor" color="#F8F8FF" inverse>{cursorChar}</Text>);
    if (after) parts.push(<Text key="after">{after}</Text>);

    // Ghost completion (only on first line, after cursor at end)
    if (
      cursorInLine === lineText.length &&
      !isMultiline &&
      ghostCompletion
    ) {
      const ghost = ghostCompletion.slice(lineText.trimStart().length);
      if (ghost) {
        parts.push(<Text key="ghost" color="#8E8E93">{ghost}</Text>);
      }
    }

    return parts;
  };

  // Map cursor position to (lineIndex, charOffset)
  let cursorLineIdx = 0;
  let cursorCharIdx = editor.cursor;
  {
    let consumed = 0;
    for (let i = 0; i < lines.length; i++) {
      const lineLen = lines[i]!.length;
      if (editor.cursor <= consumed + lineLen) {
        cursorLineIdx = i;
        cursorCharIdx = editor.cursor - consumed;
        break;
      }
      consumed += lineLen + 1; // +1 for newline
    }
  }

  // ── Single-line rendering ─────────────────────────────────────

  if (!isMultiline) {
    return (
      <Box paddingX={1} flexDirection="column">
        <Box>
          <Text color={modeColor} bold>{modeLabel}</Text>
          <Text dimColor> | </Text>
          <Text color="#E8D5B7" bold>pfaa</Text>
          <Text color="#E8D5B7"> {'\u25B8'} </Text>
          {renderLineWithCursor(editor.text, editor.cursor)}
        </Box>
        {showExitHint && (
          <Box marginLeft={2}>
            <Text dimColor>(press Ctrl+C again or type &quot;exit&quot; to quit)</Text>
          </Box>
        )}
      </Box>
    );
  }

  // ── Multiline rendering ───────────────────────────────────────

  return (
    <Box paddingX={1} flexDirection="column">
      {lines.map((line, idx) => (
        <Box key={idx}>
          {idx === 0 ? (
            <>
              <Text color={modeColor} bold>{modeLabel}</Text>
              <Text dimColor> | </Text>
              <Text color="#E8D5B7" bold>pfaa</Text>
              <Text color="#E8D5B7"> {'\u25B8'} </Text>
            </>
          ) : (
            <Text color="#8E8E93">{'     ... '}</Text>
          )}
          {renderLineWithCursor(line, idx === cursorLineIdx ? cursorCharIdx : null)}
        </Box>
      ))}
      {showExitHint && (
        <Box marginLeft={2}>
          <Text dimColor>(press Ctrl+C again or type &quot;exit&quot; to quit)</Text>
        </Box>
      )}
    </Box>
  );
}
