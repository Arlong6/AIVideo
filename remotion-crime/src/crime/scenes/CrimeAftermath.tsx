import { AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame } from "remotion";
import { crimeTheme } from "../theme";
import { PhotoLayer } from "../PhotoLayer";
import { TextReveal } from "../TextReveal";
import type { Case } from "../data";

export const CrimeAftermath: React.FC<{ c: Case; duration: number }> = ({ c, duration }) => {
  const frame = useCurrentFrame();

  const labelOpacity = interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      <Audio src={staticFile(`crime/${c.id}/aftermath.mp3`)} />
      {c.aftermathImage && (
        <PhotoLayer
          caseId={c.id}
          src={c.aftermathImage}
          duration={duration}
          darken={0.78}
          zoomFrom={1.2}
          zoomTo={1.32}
        />
      )}

      <AbsoluteFill
        style={{
          padding: 80,
          paddingTop: 280,
          alignItems: "center",
          flexDirection: "column",
          gap: 50,
        }}
      >
        <div
          style={{
            fontFamily: crimeTheme.fontMono,
            color: crimeTheme.muted,
            fontSize: 34,
            letterSpacing: 10,
            opacity: labelOpacity,
            padding: "8px 28px",
            border: `1px solid ${crimeTheme.muted}`,
          }}
        >
          AFTERMATH · 後續
        </div>

        <TextReveal
          text={c.aftermath}
          audioDur={c.timings.aftermath}
          delayFrames={40}
          style={{
            color: crimeTheme.text,
            fontFamily: crimeTheme.fontZh,
            fontSize: 46,
            fontWeight: 500,
            lineHeight: 1.65,
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
