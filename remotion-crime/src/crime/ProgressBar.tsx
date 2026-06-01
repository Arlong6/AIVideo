import { useCurrentFrame, useVideoConfig } from "remotion";
import { crimeTheme } from "./theme";

/**
 * Thin progress bar at the bottom of the video.
 * Fills from left to right across the entire video duration.
 */
export const ProgressBar: React.FC<{ totalFrames: number }> = ({
  totalFrames: total,
}) => {
  const frame = useCurrentFrame();
  const progress = Math.min(1, frame / Math.max(1, total - 1));

  return (
    <div
      style={{
        position: "absolute",
        bottom: 0,
        left: 0,
        width: "100%",
        height: 4,
        background: "rgba(255,255,255,0.1)",
        zIndex: 200,
      }}
    >
      <div
        style={{
          width: `${progress * 100}%`,
          height: "100%",
          background: crimeTheme.accent,
          transition: "none",
        }}
      />
    </div>
  );
};
