import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";

export const PhotoLayer: React.FC<{
  caseId: string;
  src: string;
  duration: number;
  darken?: number;
  zoomFrom?: number;
  zoomTo?: number;
  panX?: [number, number];
  panY?: [number, number];
}> = ({ caseId, src, duration, darken = 0.55, zoomFrom = 1.08, zoomTo = 1.22, panX = [0, -4], panY = [0, -2] }) => {
  const frame = useCurrentFrame();
  const t = Math.min(1, frame / duration);
  const scale = interpolate(t, [0, 1], [zoomFrom, zoomTo]);
  const tx = interpolate(t, [0, 1], panX);
  const ty = interpolate(t, [0, 1], panY);

  return (
    <AbsoluteFill style={{ overflow: "hidden", background: "#000" }}>
      <Img
        src={staticFile(`crime/${caseId}/${src}`)}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale}) translate(${tx}%, ${ty}%)`,
          filter: "grayscale(0.35) contrast(1.15) saturate(0.75) sepia(0.08)",
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at center, rgba(0,0,0,${darken - 0.15}) 0%, rgba(0,0,0,${darken + 0.2}) 100%)`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "repeating-linear-gradient(0deg, rgba(255,255,255,0.02) 0 1px, transparent 1px 3px)",
          mixBlendMode: "overlay",
          opacity: 0.5,
        }}
      />
    </AbsoluteFill>
  );
};
