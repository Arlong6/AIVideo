import { AbsoluteFill } from "remotion";
import { crimeTheme } from "./theme";

export const CrimeTape: React.FC<{ top?: number; text?: string; rotate?: number }> = ({
  top = 80,
  text = "CRIME SCENE · DO NOT CROSS ·",
  rotate = -4,
}) => {
  const repeated = `${text} ${text} ${text} ${text}`;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          top,
          left: -100,
          right: -100,
          background: crimeTheme.tape,
          transform: `rotate(${rotate}deg)`,
          padding: "18px 0",
          color: crimeTheme.ink,
          fontFamily: crimeTheme.fontMono,
          fontSize: 36,
          fontWeight: 900,
          letterSpacing: 4,
          textAlign: "center",
          overflow: "hidden",
          whiteSpace: "nowrap",
          boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
        }}
      >
        {repeated}
      </div>
    </AbsoluteFill>
  );
};
