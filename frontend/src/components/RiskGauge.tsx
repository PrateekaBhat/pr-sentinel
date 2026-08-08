import type { RiskLevel } from "../types";

interface Props {
  risk: RiskLevel;
  evidenceConfidence?: string;
}

const RISK_FRACTION: Record<RiskLevel, number> = {
  LOW: 0.16,
  MEDIUM: 0.5,
  HIGH: 0.86,
};

const RISK_COLOR: Record<RiskLevel, string> = {
  LOW: "#3DD68C",
  MEDIUM: "#F5A623",
  HIGH: "#E5484D",
};

const CX = 110;
const CY = 108;
const R = 88;

function polarToCartesian(angleDeg: number) {
  const theta = (angleDeg * Math.PI) / 180;
  return { x: CX + R * Math.cos(theta), y: CY - R * Math.sin(theta) };
}

const arcStart = polarToCartesian(180); // left, low-risk end
const arcEnd = polarToCartesian(0); // right, high-risk end
const trackPath = `M ${arcStart.x} ${arcStart.y} A ${R} ${R} 0 1 1 ${arcEnd.x} ${arcEnd.y}`;

export default function RiskGauge({ risk, evidenceConfidence = "MEDIUM" }: Props) {
  const fraction = RISK_FRACTION[risk];
  const needleAngle = 180 - fraction * 180;
  const needleTip = polarToCartesian(needleAngle);
  const color = RISK_COLOR[risk];

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 220 130" className="w-64 max-w-full">
        <path
          d={trackPath}
          fill="none"
          stroke={color}
          strokeWidth={14}
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray="100 100"
          opacity={0.15}
        />
        <path
          d={trackPath}
          fill="none"
          stroke="#22304A"
          strokeWidth={14}
          strokeLinecap="butt"
          pathLength={100}
          strokeDasharray="33 67"
          strokeDashoffset={0}
        />
        <path
          d={trackPath}
          fill="none"
          stroke="#3DD68C"
          strokeWidth={4}
          strokeLinecap="butt"
          pathLength={100}
          strokeDasharray="33 67"
          strokeDashoffset={0}
          opacity={0.55}
        />
        <path
          d={trackPath}
          fill="none"
          stroke="#F5A623"
          strokeWidth={4}
          strokeLinecap="butt"
          pathLength={100}
          strokeDasharray="33 67"
          strokeDashoffset={-33}
          opacity={0.55}
        />
        <path
          d={trackPath}
          fill="none"
          stroke="#E5484D"
          strokeWidth={4}
          strokeLinecap="butt"
          pathLength={100}
          strokeDasharray="34 66"
          strokeDashoffset={-66}
          opacity={0.55}
        />

        {/* needle */}
        <line
          x1={CX}
          y1={CY}
          x2={needleTip.x}
          y2={needleTip.y}
          stroke={color}
          strokeWidth={3}
          strokeLinecap="round"
        />
        <circle cx={CX} cy={CY} r={6} fill={color} />
      </svg>

      <div className="-mt-4 flex flex-col items-center">
        <span
          className="font-display text-2xl font-semibold tracking-tight"
          style={{ color }}
        >
          {risk} Release Risk
        </span>
        <span className="font-mono text-xs text-fog">
          Evidence Confidence: {evidenceConfidence}
        </span>
      </div>
    </div>
  );
}
