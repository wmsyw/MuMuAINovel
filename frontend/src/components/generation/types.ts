import type { InspirationGenerationContext } from '../../types';

export interface GenerationConfig {
  title: string;
  description: string;
  theme: string;
  genre: string | string[];
  narrative_perspective: string;
  target_words: number;
  chapter_count: number;
  character_count: number;
  outline_mode?: 'one-to-one' | 'one-to-many';
  inspiration_context?: InspirationGenerationContext;
}
