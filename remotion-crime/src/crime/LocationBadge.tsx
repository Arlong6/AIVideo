import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { crimeTheme } from "./theme";

/**
 * Location + date badge overlay — shows during Hook/Setup scenes.
 * Pin-drop animation on mount, subtle pulse.
 */
export const LocationBadge: React.FC<{
  location: string;
  date?: string;
  delayFrames?: number;
}> = ({ location, date, delayFrames = 15 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const adjustedFrame = Math.max(0, frame - delayFrames);

  // Pin drop animation
  const drop = spring({
    frame: adjustedFrame,
    fps,
    config: { damping: 12, stiffness: 120, mass: 0.8 },
  });

  // Date fades in slightly after location
  const dateFade = Math.min(1, Math.max(0, (adjustedFrame - 15) / 12));

  if (adjustedFrame <= 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: 80,
        left: 60,
        zIndex: 100,
        transform: `translateY(${(1 - drop) * -40}px)`,
        opacity: drop,
      }}
    >
      {/* Location */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          background: "rgba(0,0,0,0.75)",
          backdropFilter: "blur(8px)",
          borderLeft: `4px solid ${crimeTheme.accent}`,
          padding: "14px 24px",
          borderRadius: "0 8px 8px 0",
        }}
      >
        <span style={{ fontSize: 32 }}>📍</span>
        <span
          style={{
            fontFamily: crimeTheme.fontZh,
            fontSize: 30,
            color: crimeTheme.text,
            fontWeight: 600,
            letterSpacing: 2,
          }}
        >
          {location}
        </span>
      </div>

      {/* Date (below location) */}
      {date && (
        <div
          style={{
            marginTop: 8,
            marginLeft: 4,
            opacity: dateFade,
            display: "flex",
            alignItems: "center",
            gap: 10,
            background: "rgba(0,0,0,0.6)",
            padding: "10px 20px",
            borderRadius: "0 6px 6px 0",
            borderLeft: `3px solid ${crimeTheme.muted}`,
          }}
        >
          <span style={{ fontSize: 24 }}>📅</span>
          <span
            style={{
              fontFamily: crimeTheme.fontMono,
              fontSize: 24,
              color: crimeTheme.muted,
              letterSpacing: 1,
            }}
          >
            {date}
          </span>
        </div>
      )}
    </div>
  );
};
