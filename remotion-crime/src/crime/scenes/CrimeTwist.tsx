import { AbsoluteFill, Audio, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { crimeTheme } from "../theme";
import { PhotoLayer } from "../PhotoLayer";
import { TextReveal } from "../TextReveal";
import type { Case } from "../data";

export const CrimeTwist: React.FC<{ c: Case; duration: number }> = ({ c, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const stampScale = spring({ frame, fps, config: { damping: 10, stiffness: 80 } });
  const flashOpacity = interpolate(frame, [0, 8, 20], [0, 0.55, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      <Audio src={staticFile(`crime/${c.id}/twist.mp3`)} />
      {c.twistImage && (
        <PhotoLayer caseId={c.id} src={c.twistImage} duration={duration} darken={0.72} zoomFrom={1.15} zoomTo={1.3} />
      )}

      <AbsoluteFill style={{ background: crimeTheme.accent, opacity: flashOpacity, pointerEvents: "none" }} />

      <AbsoluteFill
        style={{
          padding: 80,
          paddingTop: 280,
          alignItems: "center",
          flexDirection: "column",
          gap: 60,
        }}
      >
        <div
          style={{
            transform: `scale(${stampScale}) rotate(-6deg)`,
            border: `8px solid ${crimeTheme.accent}`,
            color: crimeTheme.accent,
            fontFamily: crimeTheme.fontMono,
            fontSize: 80,
            fontWeight: 900,
            padding: "22px 56px",
            letterSpacing: 12,
            background: "rgba(0,0,0,0.5)",
            textShadow: "0 4px 20px rgba(200,16,46,0.8)",
          }}
        >
          真 相
        </div>

        <TextReveal
          text={c.twist}
          audioDur={c.timings.twist}
          delayFrames={50}
          style={{
            color: crimeTheme.text,
            fontFamily: crimeTheme.fontZh,
            fontSize: 52,
            fontWeight: 600,
            lineHeight: 1.6,
            textAlign: "center",
            maxWidth: 920,
            textShadow: "0 4px 16px rgba(0,0,0,0.9)",
            display: "inline-block",
          }}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
