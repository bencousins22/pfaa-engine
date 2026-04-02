/**
 * PFAA TUI Context — Shared state for all components
 */

import React, { createContext, useContext, useState, useCallback, useRef, useSyncExternalStore } from 'react';
import type { PFAABridge } from '../bridge/pfaa-bridge.js';
import type { AgentOrchestrator } from '../agents/orchestrator.js';
import type { JMEMClient } from '../memory/jmem-client.js';
import type { StreamEvent } from '../types.js';

// ── Message types ──────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool';

export interface ToolCall {
  id: string;
  name: string;
  phase: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  args?: string;
  result?: string;
  elapsedMs?: number;
  startedAt: number;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  toolCalls?: ToolCall[];
  streaming?: boolean;
  agentId?: string;
  agentRole?: string;
}

// ── Streaming tool use ────────────────────────────────────────────

export interface StreamingToolUse {
  index: number;
  id: string;
  name: string;
  unparsedInput: string;
  status: 'streaming' | 'executing' | 'completed' | 'failed';
  result?: string;
  startedAt: number;
  elapsedMs?: number;
}

// ── App state ──────────────────────────────────────────────────────

export interface AppState {
  messages: Message[];
  isProcessing: boolean;
  currentPhase: string;
  model: string;
  tokensUsed: number;
  elapsedMs: number;
  toolCount: number;
  memoryCount: number;
  isLive: boolean;
  events: StreamEvent[];
  streamingText: string | null;
  streamingToolUses: StreamingToolUse[];
  streamingMode: 'idle' | 'requesting' | 'thinking' | 'responding' | 'tool-input' | 'tool-use';
  totalCost: number;
  turnCount: number;
}

export interface AppContextType {
  state: AppState;
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => string;
  updateMessage: (id: string, update: Partial<Message>) => void;
  appendToMessage: (id: string, text: string) => void;
  setProcessing: (v: boolean) => void;
  setPhase: (p: string) => void;
  updateStats: (s: Partial<Pick<AppState, 'tokensUsed' | 'elapsedMs' | 'toolCount' | 'memoryCount'>>) => void;
  addEvent: (e: StreamEvent) => void;
  setStreamingText: (text: string | null) => void;
  updateStreamingText: (fn: (current: string | null) => string | null) => void;
  setStreamingMode: (mode: AppState['streamingMode']) => void;
  setStreamingToolUses: (fn: (current: StreamingToolUse[]) => StreamingToolUse[]) => void;
  addCost: (cost: number) => void;
  incrementTurn: () => void;
  bridge: PFAABridge;
  orchestrator: AgentOrchestrator;
  memory: JMEMClient;
}

const AppContext = createContext<AppContextType | null>(null);

export function useApp(): AppContextType {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}

let _msgId = 0;
function nextId(): string { return `msg_${++_msgId}`; }

interface AppProviderProps {
  bridge: PFAABridge;
  orchestrator: AgentOrchestrator;
  memory: JMEMClient;
  isLive: boolean;
  model: string;
  children: React.ReactNode;
}

export function AppProvider({ bridge, orchestrator, memory, isLive, model, children }: AppProviderProps) {
  const [state, setState] = useState<AppState>({
    messages: [],
    isProcessing: false,
    currentPhase: 'VAPOR',
    model,
    tokensUsed: 0,
    elapsedMs: 0,
    toolCount: 0,
    memoryCount: 0,
    isLive,
    events: [],
    streamingText: null,
    streamingToolUses: [],
    streamingMode: 'idle',
    totalCost: 0,
    turnCount: 0,
  });

  // Use ref to avoid stale closures in callbacks
  const stateRef = useRef(state);
  stateRef.current = state;

  const addMessage = useCallback((msg: Omit<Message, 'id' | 'timestamp'>): string => {
    const id = nextId();
    const full: Message = { ...msg, id, timestamp: Date.now() };
    setState(s => ({ ...s, messages: [...s.messages, full] }));
    return id;
  }, []);

  const updateMessage = useCallback((id: string, update: Partial<Message>) => {
    setState(s => ({
      ...s,
      messages: s.messages.map(m => m.id === id ? { ...m, ...update } : m),
    }));
  }, []);

  const appendToMessage = useCallback((id: string, text: string) => {
    setState(s => ({
      ...s,
      messages: s.messages.map(m => m.id === id ? { ...m, content: m.content + text } : m),
    }));
  }, []);

  const setProcessing = useCallback((isProcessing: boolean) => {
    setState(s => ({ ...s, isProcessing }));
  }, []);

  const setPhase = useCallback((currentPhase: string) => {
    setState(s => ({ ...s, currentPhase }));
  }, []);

  const updateStats = useCallback((stats: Partial<Pick<AppState, 'tokensUsed' | 'elapsedMs' | 'toolCount' | 'memoryCount'>>) => {
    setState(s => ({ ...s, ...stats }));
  }, []);

  const addEvent = useCallback((e: StreamEvent) => {
    setState(s => ({ ...s, events: [...s.events.slice(-50), e] }));
  }, []);

  const setStreamingText = useCallback((text: string | null) => {
    setState(s => ({ ...s, streamingText: text }));
  }, []);

  const updateStreamingText = useCallback((fn: (current: string | null) => string | null) => {
    setState(s => ({ ...s, streamingText: fn(s.streamingText) }));
  }, []);

  const setStreamingMode = useCallback((streamingMode: AppState['streamingMode']) => {
    setState(s => ({ ...s, streamingMode }));
  }, []);

  const setStreamingToolUses = useCallback((fn: (current: StreamingToolUse[]) => StreamingToolUse[]) => {
    setState(s => ({ ...s, streamingToolUses: fn(s.streamingToolUses) }));
  }, []);

  const addCost = useCallback((cost: number) => {
    setState(s => ({ ...s, totalCost: s.totalCost + cost }));
  }, []);

  const incrementTurn = useCallback(() => {
    setState(s => ({ ...s, turnCount: s.turnCount + 1 }));
  }, []);

  return (
    <AppContext.Provider value={{
      state,
      addMessage,
      updateMessage,
      appendToMessage,
      setProcessing,
      setPhase,
      updateStats,
      addEvent,
      setStreamingText,
      updateStreamingText,
      setStreamingMode,
      setStreamingToolUses,
      addCost,
      incrementTurn,
      bridge,
      orchestrator,
      memory,
    }}>
      {children}
    </AppContext.Provider>
  );
}
