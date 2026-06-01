import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { CSSProperties } from "react";

/**
 * Character-by-character text reveal synced to audio duration.
 *
 * Renders all characters immediately (preserving layout), but sets
 * opacity 0 on unrevealed ones so the text block doesn't reflow.
 *
 * @param text        The full text string
 * @param audioDur    Audio duration in seconds (from timings)
 * @param delayFrames Frames to wait before the reveal starts (default 0)
 * @param style       Optional CSS overrides for the outer span
 */
export const TextReveal: React.FC<{
  text: string;
  audioDur: number;
  delayFrames?: number;
  style?: CSSProperties;
}> = ({ text, audioDur, delayFrames = 0, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const chars = Array.from(text);
  const totalChars = chars.length;
  if (totalChars === 0) return null;

  // Total frames available for the reveal (= audio duration in frames)
  const revealFrames = audioDur * fps;

  // Frames per character — spread evenly across the audio duration
  const fpc = revealFrames / totalChars;

  return (
    <span style={style}>
      {chars.map((ch, i) => {
        const appearAt = delayFrames + i * fpc;
        // 3-frame ramp from 0 → 1 for a crisp but not instant pop
        const opacity = interpolate(frame, [appearAt, appearAt + 3], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <span key={i} style={{ opacity }}>
            {ch}
          </span>
        );
      })}
    </span>
  );
};
