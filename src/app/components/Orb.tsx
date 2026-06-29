import { OrbState } from '../types';

interface OrbProps {
  state: OrbState;
  active: boolean;
}

export function Orb({ state, active }: OrbProps) {
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
    </div>
  );
}
