/**
 * PFAA AltScreen — Alternate screen buffer for full-screen TUI
 *
 * Enters the terminal's alternate screen buffer on mount and restores
 * the original buffer on unmount. This gives us a clean full-screen
 * canvas that doesn't pollute the user's scrollback history.
 *
 * Handles:
 *   - Alternate screen buffer (ESC[?1049h / ESC[?1049l)
 *   - Cursor visibility (ESC[?25l hide / ESC[?25h show)
 *   - Graceful cleanup on SIGINT, SIGTERM, uncaughtException
 *   - Mouse reporting disable on exit
 */

import React, { useEffect, type ReactNode } from 'react';
import { Box } from 'ink';

// ── ANSI escape sequences ────────────────────────────────────────────

const ESC = '\x1b';

/** Enter alternate screen buffer */
const ALT_SCREEN_ENTER = `${ESC}[?1049h`;

/** Exit alternate screen buffer */
const ALT_SCREEN_EXIT = `${ESC}[?1049l`;

/** Hide cursor */
const CURSOR_HIDE = `${ESC}[?25l`;

/** Show cursor */
const CURSOR_SHOW = `${ESC}[?25h`;

/** Move cursor to top-left */
const CURSOR_HOME = `${ESC}[H`;

/** Clear entire screen */
const CLEAR_SCREEN = `${ESC}[2J`;

/** Disable mouse tracking (in case it was enabled) */
const MOUSE_OFF = `${ESC}[?1000l${ESC}[?1003l${ESC}[?1006l`;

/** Reset terminal attributes */
const RESET_ATTRS = `${ESC}[0m`;

// ── Cleanup logic ────────────────────────────────────────────────────

function enterAltScreen(): void {
  if (!process.stdout.isTTY) return;
  process.stdout.write(ALT_SCREEN_ENTER + CURSOR_HIDE + CURSOR_HOME + CLEAR_SCREEN);
}

function exitAltScreen(): void {
  if (!process.stdout.isTTY) return;
  process.stdout.write(
    MOUSE_OFF + RESET_ATTRS + CURSOR_SHOW + ALT_SCREEN_EXIT
  );
}

/**
 * Install global signal handlers that ensure we leave the alt screen
 * even if the process crashes or is interrupted. Each handler cleans
 * up the terminal, then re-raises the signal so Node's default
 * handler can do its thing (exit, dump core, etc.).
 */
function installCleanupHandlers(): () => void {
  let cleaned = false;

  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    exitAltScreen();
  };

  const onSignal = (sig: NodeJS.Signals) => {
    cleanup();
    // Re-raise so the default handler fires
    process.removeListener(sig, onSignal as (...args: unknown[]) => void);
    process.kill(process.pid, sig);
  };

  const onError = (err: Error) => {
    cleanup();
    // Print the error to the restored screen
    process.stderr.write(`\nFatal error: ${err.message}\n${err.stack ?? ''}\n`);
    process.exit(1);
  };

  const onExit = () => {
    cleanup();
  };

  process.on('SIGINT', onSignal);
  process.on('SIGTERM', onSignal);
  process.on('SIGHUP', onSignal);
  process.on('uncaughtException', onError);
  process.on('exit', onExit);

  return () => {
    cleanup();
    process.removeListener('SIGINT', onSignal);
    process.removeListener('SIGTERM', onSignal);
    process.removeListener('SIGHUP', onSignal);
    process.removeListener('uncaughtException', onError);
    process.removeListener('exit', onExit);
  };
}

// ── Component ────────────────────────────────────────────────────────

interface AltScreenProps {
  /** Content to render inside the alternate screen */
  children: ReactNode;

  /**
   * When false, the alternate screen is not entered and the component
   * simply renders its children. Useful for piped/non-TTY output.
   * Defaults to `process.stdout.isTTY`.
   */
  enabled?: boolean;
}

/**
 * Wraps children in a terminal alternate screen buffer.
 *
 * Usage:
 * ```tsx
 * <AltScreen>
 *   <MyApp />
 * </AltScreen>
 * ```
 */
export function AltScreen({ children, enabled }: AltScreenProps) {
  const isEnabled = enabled ?? !!process.stdout.isTTY;

  useEffect(() => {
    if (!isEnabled) return;

    enterAltScreen();
    const removeHandlers = installCleanupHandlers();

    return () => {
      removeHandlers();
    };
  }, [isEnabled]);

  return (
    <Box flexDirection="column" width="100%" height="100%">
      {children}
    </Box>
  );
}

export default AltScreen;
