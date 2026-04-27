import TimelineReviewPanel from './TimelineReviewPanel';
import type { Career, Character } from '../../types';

interface ProfessionTimelinePanelProps {
  projectId?: string;
  careers: Career[];
  characters: Character[];
}

export default function ProfessionTimelinePanel({ projectId, careers, characters }: ProfessionTimelinePanelProps) {
  return (
    <TimelineReviewPanel
      projectId={projectId}
      title="职业时间线"
      eventTypes={['profession']}
      characters={characters}
      careers={careers}
    />
  );
}
