import { AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame } from "remotion";
import { crimeTheme } from "../theme";
import { CrimeTape } from "../CrimeTape";
import { PhotoLayer } from "../PhotoLayer";
import { TextReveal } from "../TextReveal";
import type { Case } from "../data";

export const CrimeHook: React.FC<{ c: Case; duration: number }> = ({ c, duration }) => {
  const frame = useCurrentFrame();

  const dateOpacity = interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" });
  const stampScale = interpolate(frame, [20, 40], [2, 1], { extrapolateRight: "clamp" });
  const stampOpacity = interpolate(frame, [20, 40], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      <Audio src={staticFile(`crime/${c.id}/hook.mp3`)} />
      {c.hookImage && (
        <PhotoLayer caseId={c.id} src={c.hookImage} duration={duration} darken={0.6} />
      )}
      <CrimeTape top={180} />

      <AbsoluteFill
        style={{
          padding: 80,
          paddingTop: 300,
          flexDirection: "column",
          gap: 40,
          alignItems: "center",
        }}
      >
        <div
          style={{
            color: crimeTheme.tape,
            fontFamily: crimeTheme.fontMono,
            fontSize: 40,
            letterSpacing: 4,
            opacity: dateOpacity,
            textAlign: "center",
            marginTop: 40,
            textShadow: "0 4px 12px rgba(0,0,0,0.8)",
          }}
        >
          {c.date} · {c.location}
        </div>

        <div
          style={{
            transform: `scale(${stampScale}) rotate(-8deg)`,
            opacity: stampOpacity * 0.92,
            border: `6px solid ${crimeTheme.accent}`,
            color: crimeTheme.accent,
            fontFamily: crimeTheme.fontMono,
            fontSize: 48,
            fontWeight: 900,
            padding: "14px 40px",
            letterSpacing: 8,
            background: "rgba(0,0,0,0.5)",
          }}
        >
          {c.status === "unsolved" ? "UNSOLVED" : "SOLVED"}
        </div>

        <TextReveal
          text={c.hook}
          audioDur={c.timings.hook}
          delayFrames={45}
          style={{
            color: crimeTheme.text,
            fontFamily: crimeTheme.fontZh,
            fontSize: 62,
            fontWeight: 800,
            lineHeight: 1.45,
            textAlign: "center",
            marginTop: 20,
            maxWidth: 920,
            textShadow: "0 4px 16px rgba(0,0,0,0.9)",
            display: "inline-block",
          }}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
