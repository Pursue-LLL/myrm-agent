/**
 * Domain types for Visual Modular Agent Assembler and Capability Composer.
 *
 * [INPUT] None (Standard TypeScript)
 * [OUTPUT] Pure domain models for capability blocks, blueprints, validation, and sandbox dry-run.
 * [POS] src/components/features/agent-assembler/assemblerTypes.ts
 */

export type CapabilityBlockCategory =
  | 'brain'
  | 'persona'
  | 'tools'
  | 'skills'
  | 'memory'
  | 'sandbox';

export interface CapabilityBlock {
  id: string;
  category: CapabilityBlockCategory;
  name: string;
  description: string;
  enabled: boolean;
  config: Record<string, string | number | boolean | string[]>;
}

export interface AssemblyBlueprint {
  name: string;
  description: string;
  blocks: CapabilityBlock[];
}

export interface AssemblyValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  suggestions: string[];
  estimated_token_cost: number;
}

export interface SandboxDryRunRequest {
  blueprint: AssemblyBlueprint;
  prompt: string;
}

export interface SandboxDryRunResult {
  simulated_response: string;
  resolved_system_prompt: string;
  predicted_tool_calls: string[];
  latency_ms: number;
  tokens_used: number;
}

export type PresetTemplateKey = 'architect' | 'analyst' | 'general';
