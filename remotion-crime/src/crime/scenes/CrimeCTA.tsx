import { AbsoluteFill, Audio, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { crimeTheme } from "../theme";
import { TextReveal } from "../TextReveal";
import type { Case } from "../data";

// Parse "1：冤枉 2：活該 你選？" → { opt1: "冤枉", opt2: "活該", question: "你選？" }
function parseBinaryCTA(cta: string): { opt1: string; opt2: string; question: string } | null {
  // Tolerant matcher: 1[:：.] X 2[:：.] Y rest
  const m = cta.match(/1\s*[：:．.]\s*([^12]{1,12}?)\s*2\s*[：:．.]\s*([^?？]{1,12}?)(?:\s*[?？].*)?\s*$/);
  if (!m) return null;
  const opt1 = m[1].trim();
  const opt2 = m[2].trim();
  // Trailing question: anything after second option
  const tailMatch = cta.match(/2\s*[：:．.]\s*[^?？]+?(.*)$/);
  const question = tailMatch && tailMatch[1] ? tailMatch[1].replace(/^[\s?？]+/, "").trim() : "";
  if (!opt1 || !opt2) return null;
  return { opt1, opt2, question };
}

export const CrimeCTA: React.FC<{ c: Case }> = ({ c }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({ frame, fps, config: { damping: 12, stiffness: 110 } });
  const pulse = 1 + Math.sin(frame / 6) * 0.03;

  const binary = parseBinaryCTA(c.cta);

  return (
    <AbsoluteFill
      style={{
        background: crimeTheme.bgGradient,
        justifyContent: "center",
        alignItems: "center",
        padding: 60,
        gap: 40,
      }}
    >
      <Audio src={staticFile(`crime/${c.id}/cta.mp3`)} />

      <div
        style={{
          transform: `scale(${scale * pulse})`,
          color: crimeTheme.tape,
          fontFamily: crimeTheme.fontMono,
          fontSize: 44,
          letterSpacing: 4,
        }}
      >
        留言 1 或 2
      </div>

      {binary ? (
        <>
          {/* Option 1 card */}
          <div
            style={{
              transform: `scale(${scale})`,
              background: "rgba(212, 165, 116, 0.18)",
              border: `4px solid ${crimeTheme.tape}`,
              borderRadius: 20,
              padding: "32px 60px",
              display: "flex",
              alignItems: "center",
              gap: 36,
              minWidth: 720,
              justifyContent: "flex-start",
            }}
          >
            <div
              style={{
                fontFamily: crimeTheme.fontMono,
                fontSize: 140,
                fontWeight: 900,
                color: crimeTheme.tape,
                lineHeight: 1,
              }}
            >
              1
            </div>
            <div
              style={{
                fontFamily: crimeTheme.fontZh,
                fontSize: 88,
                fontWeight: 900,
                color: crimeTheme.text,
                flex: 1,
              }}
            >
              {binary.opt1}
            </div>
          </div>

          {/* Option 2 card */}
          <div
            style={{
              transform: `scale(${scale})`,
              background: "rgba(212, 165, 116, 0.18)",
              border: `4px solid ${crimeTheme.tape}`,
              borderRadius: 20,
              padding: "32px 60px",
              display: "flex",
              alignItems: "center",
              gap: 36,
              minWidth: 720,
              justifyContent: "flex-start",
            }}
          >
            <div
              style={{
                fontFamily: crimeTheme.fontMono,
                fontSize: 140,
                fontWeight: 900,
                color: crimeTheme.tape,
                lineHeight: 1,
              }}
            >
              2
            </div>
            <div
              style={{
                fontFamily: crimeTheme.fontZh,
                fontSize: 88,
                fontWeight: 900,
                color: crimeTheme.text,
                flex: 1,
              }}
            >
              {binary.opt2}
            </div>
          </div>

          {binary.question && (
            <div
              style={{
                fontFamily: crimeTheme.fontZh,
                fontSize: 56,
                fontWeight: 800,
                color: crimeTheme.tape,
                marginTop: 20,
                opacity: interpolate(frame, [20, 40], [0, 1], { extrapolateRight: "clamp" }),
              }}
            >
              {binary.question}
            </div>
          )}
        </>
      ) : (
        <TextReveal
          text={c.cta}
          audioDur={c.timings.cta}
          delayFrames={10}
          style={{
            color: crimeTheme.text,
            fontFamily: crimeTheme.fontZh,
            fontSize: 76,
            fontWeight: 900,
            textAlign: "center",
            transform: `scale(${scale})`,
            display: "inline-block",
          }}
        />
      )}

      {c.has_longform && (
        <div
          style={{
            marginTop: binary ? 10 : 30,
            color: crimeTheme.tape,
            fontFamily: crimeTheme.fontZh,
            fontSize: 44,
            fontWeight: 800,
            letterSpacing: 1,
            background: "rgba(0,0,0,0.55)",
            padding: "14px 40px",
            borderRadius: 12,
            opacity: interpolate(frame, [40, 70], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          🔗 主頁看完整版
        </div>
      )}

      {c.credits && (
        <div
          style={{
            position: "absolute",
            bottom: 40,
            color: crimeTheme.muted,
            fontFamily: crimeTheme.fontMono,
            fontSize: 22,
            letterSpacing: 2,
            opacity: interpolate(frame, [30, 60], [0, 0.7], { extrapolateRight: "clamp" }),
          }}
        >
          {c.credits}
        </div>
      )}
    </AbsoluteFill>
  );
};
