'use client';

/**
 * [INPUT]
 * - ./NewTaskWorkContextCard (POS: Unified workspace context card)
 *
 * [OUTPUT]
 * - UnifiedWorkContextCard: Alias export for NewTaskWorkContextCard aligning with roadmap terminology
 *
 * [POS]
 * Thin export wrapper ensuring seamless imports under both UnifiedWorkContextCard and NewTaskWorkContextCard.
 */

export { NewTaskWorkContextCard as default, NewTaskWorkContextCard, UnifiedWorkContextCard } from './NewTaskWorkContextCard';
export type { NewTaskMode } from './NewTaskWorkContextCard';
