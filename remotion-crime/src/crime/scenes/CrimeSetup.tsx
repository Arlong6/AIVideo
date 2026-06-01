import { AbsoluteFill, Audio, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { crimeTheme } from "../theme";
import { PhotoLayer } from "../PhotoLayer";
import { TextReveal } from "../TextReveal";
import type { Case } from "../data";

export const CrimeSetup: React.FC<{ c: Case; duration: number }> = ({ c, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const cardScale = spring({ frame, fps, config: { damping: 14, stiffness: 90 } });

  return (
    <AbsoluteFill>
      <Audio src={staticFile(`crime/${c.id}/setup.mp3`)} />
      {c.setupImage && (
        <PhotoLayer caseId={c.id} src={c.setupImage} duration={duration} darken={0.7} />
      )}

      <AbsoluteFill
        style={{
          padding: 80,
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <div
          style={{
            transform: `scale(${cardScale})`,
            background: `${crimeTheme.paper}ee`,
            color: crimeTheme.ink,
            fontFamily: crimeTheme.fontSerif,
            width: "100%",
            maxWidth: 880,
            padding: 60,
            border: `3px solid ${crimeTheme.ink}`,
            boxShadow: "20px 20px 0 rgba(200,16,46,0.5)",
          }}
        >
          <div
            style={{
              fontFamily: crimeTheme.fontMono,
              fontSize: 28,
              color: crimeTheme.accent,
              letterSpacing: 6,
              marginBottom: 16,
            }}
          >
            CASE FILE · 檔案
          </div>
          <div
            style={{
              fontSize: 76,
              fontWeight: 900,
              lineHeight: 1.1,
              marginBottom: 24,
            }}
          >
            {c.title}
          </div>
          <div
            style={{
              fontFamily: crimeTheme.fontZh,
              fontSize: 34,
              color: "#444",
              borderTop: `2px solid ${crimeTheme.ink}`,
              paddingTop: 16,
              marginBottom: 30,
            }}
          >
            {c.titleZh}
          </div>
          <TextReveal
            text={c.setup}
            audioDur={c.timings.setup}
            delayFrames={30}
            style={{
              fontFamily: crimeTheme.fontZh,
              fontSize: 40,
              lineHeight: 1.55,
              display: "inline-block",
            }}
          />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
