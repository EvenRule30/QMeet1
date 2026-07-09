import { AssistantActivity, OrbState } from '../types';

interface OrbProps {
  state: OrbState;
  active: boolean;
  activity?: AssistantActivity | null;
}

export function Orb({ state, active, activity }: OrbProps) {
  return (
    <div className={`orb-container orb-${state} ${active ? 'orb-active' : 'orb-idle-pos'}`}>
      <div className="orb-halo" />
      <div className="orb-sphere">
        <div className="orb-gradient" />
        <div className="orb-gloss" />
      </div>
      <div className="orb-depth" />
      <div className="orb-orbital-wrap">
        <div className="orbit-group orbit-group-1">
          <div className="od" />
          <div className="od" />
          <div className="od" />
        </div>
        <div className="orbit-group orbit-group-2">
          <div className="od" />
          <div className="od" />
          <div className="od" />
        </div>
      </div>

      {activity && (
        <div className={`orb-activity orb-activity-${activity.kind}`}>
          <span className="orb-activity-label">{activity.label}</span>
          <span className="orb-activity-detail">{activity.detail}</span>
        </div>
      )}
    </div>
  );
}
