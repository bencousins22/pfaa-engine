import { describe, it, expect } from 'vitest';
import {
  Phase,
  PhaseTransition,
  AgentRole,
  EventType,
  MemoryLayer,
  TaskStatus,
  Permission,
} from './types.js';

describe('Phase enum', () => {
  it('has VAPOR value', () => {
    expect(Phase.VAPOR).toBe('VAPOR');
  });

  it('has LIQUID value', () => {
    expect(Phase.LIQUID).toBe('LIQUID');
  });

  it('has SOLID value', () => {
    expect(Phase.SOLID).toBe('SOLID');
  });

  it('has exactly 3 members', () => {
    const values = Object.values(Phase);
    expect(values).toHaveLength(3);
  });
});

describe('PhaseTransition enum', () => {
  it('has CONDENSE (VAPOR -> LIQUID)', () => {
    expect(PhaseTransition.CONDENSE).toBe('condense');
  });

  it('has EVAPORATE (LIQUID -> VAPOR)', () => {
    expect(PhaseTransition.EVAPORATE).toBe('evaporate');
  });

  it('has FREEZE (LIQUID -> SOLID)', () => {
    expect(PhaseTransition.FREEZE).toBe('freeze');
  });

  it('has MELT (SOLID -> LIQUID)', () => {
    expect(PhaseTransition.MELT).toBe('melt');
  });

  it('has SUBLIMATE (VAPOR -> SOLID)', () => {
    expect(PhaseTransition.SUBLIMATE).toBe('sublimate');
  });

  it('has DEPOSIT (SOLID -> VAPOR)', () => {
    expect(PhaseTransition.DEPOSIT).toBe('deposit');
  });

  it('has exactly 6 members', () => {
    const values = Object.values(PhaseTransition);
    expect(values).toHaveLength(6);
  });
});

describe('AgentRole enum', () => {
  it('has ANALYZER', () => {
    expect(AgentRole.ANALYZER).toBe('analyzer');
  });

  it('has REFACTORER', () => {
    expect(AgentRole.REFACTORER).toBe('refactorer');
  });

  it('has TESTER', () => {
    expect(AgentRole.TESTER).toBe('tester');
  });

  it('has DEPLOYER', () => {
    expect(AgentRole.DEPLOYER).toBe('deployer');
  });

  it('has RESEARCHER', () => {
    expect(AgentRole.RESEARCHER).toBe('researcher');
  });

  it('has ORCHESTRATOR', () => {
    expect(AgentRole.ORCHESTRATOR).toBe('orchestrator');
  });

  it('has REVIEWER', () => {
    expect(AgentRole.REVIEWER).toBe('reviewer');
  });

  it('has BUILDER', () => {
    expect(AgentRole.BUILDER).toBe('builder');
  });

  it('has exactly 8 members', () => {
    const values = Object.values(AgentRole);
    expect(values).toHaveLength(8);
  });
});

describe('EventType enum', () => {
  it('has AGENT_SPAWNED', () => {
    expect(EventType.AGENT_SPAWNED).toBe('agent:spawned');
  });

  it('has AGENT_PHASE_CHANGE', () => {
    expect(EventType.AGENT_PHASE_CHANGE).toBe('agent:phase_change');
  });

  it('has AGENT_COMPLETED', () => {
    expect(EventType.AGENT_COMPLETED).toBe('agent:completed');
  });

  it('has AGENT_FAILED', () => {
    expect(EventType.AGENT_FAILED).toBe('agent:failed');
  });

  it('has TOOL_STARTED', () => {
    expect(EventType.TOOL_STARTED).toBe('tool:started');
  });

  it('has TOOL_COMPLETED', () => {
    expect(EventType.TOOL_COMPLETED).toBe('tool:completed');
  });

  it('has MEMORY_UPDATED', () => {
    expect(EventType.MEMORY_UPDATED).toBe('memory:updated');
  });

  it('has PIPELINE_STARTED', () => {
    expect(EventType.PIPELINE_STARTED).toBe('pipeline:started');
  });

  it('has PIPELINE_COMPLETED', () => {
    expect(EventType.PIPELINE_COMPLETED).toBe('pipeline:completed');
  });

  it('has TOKEN_STREAM', () => {
    expect(EventType.TOKEN_STREAM).toBe('token:stream');
  });

  it('has SYSTEM_STATUS', () => {
    expect(EventType.SYSTEM_STATUS).toBe('system:status');
  });

  it('has exactly 11 members', () => {
    const values = Object.values(EventType);
    expect(values).toHaveLength(11);
  });
});

describe('MemoryLayer enum', () => {
  it('has L1 through L5', () => {
    expect(MemoryLayer.L1_EPISODIC).toBe(1);
    expect(MemoryLayer.L2_SEMANTIC).toBe(2);
    expect(MemoryLayer.L3_STRATEGIC).toBe(3);
    expect(MemoryLayer.L4_META_LEARNING).toBe(4);
    expect(MemoryLayer.L5_EMERGENT).toBe(5);
  });
});

describe('TaskStatus enum', () => {
  it('has all status values', () => {
    expect(TaskStatus.PENDING).toBe('pending');
    expect(TaskStatus.RUNNING).toBe('running');
    expect(TaskStatus.COMPLETED).toBe('completed');
    expect(TaskStatus.FAILED).toBe('failed');
    expect(TaskStatus.RETRYING).toBe('retrying');
    expect(TaskStatus.CANCELLED).toBe('cancelled');
  });
});

describe('Permission enum', () => {
  it('has all permission values', () => {
    expect(Permission.READ).toBe('read');
    expect(Permission.WRITE).toBe('write');
    expect(Permission.EXECUTE).toBe('execute');
    expect(Permission.DEPLOY).toBe('deploy');
    expect(Permission.ADMIN).toBe('admin');
  });
});
