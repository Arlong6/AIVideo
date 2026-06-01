import { AbsoluteFill, Audio, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { crimeTheme } from "../theme";
import { PhotoLayer } from "../PhotoLayer";
import { TextReveal } from "../TextReveal";
import type { Case, CrimeEvent } from "../data";

const EventCard: React.FC<{
  caseId: string;
  idx: number;
  total: number;
  ev: CrimeEvent;
  duration: number;
  audioDur: number;
}> = ({ caseId, idx, total, ev, duration, audioDur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 14, stiffness: 100 } });

  return (
    <AbsoluteFill>
      {ev.image && (
        <PhotoLayer caseId={caseId} src={ev.image} duration={duration} darken={0.5} zoomFrom={1.05} zoomTo={1.18} />
      )}

      <AbsoluteFill
        style={{
          padding: 80,
          justifyContent: "space-between",
          alignItems: "center",
          flexDirection: "column",
          paddingTop: 220,
          paddingBottom: 220,
        }}
      >
        <div
          style={{
            fontFamily: crimeTheme.fontMono,
            color: crimeTheme.tape,
            fontSize: 36,
            letterSpacing: 8,
            opacity: enter,
            padding: "10px 30px",
            border: `2px solid ${crimeTheme.tape}`,
            background: "rgba(0,0,0,0.5)",
          }}
        >
          事件 {String(idx + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </div>

        <div
          style={{
            background: "rgba(0,0,0,0.75)",
            borderLeft: `8px solid ${crimeTheme.accent}`,
            padding: "28px 40px",
            maxWidth: 940,
          }}
        >
          <TextReveal
            text={ev.text}
            audioDur={audioDur}
            delayFrames={15}
            style={{
              color: crimeTheme.text,
              fontFamily: crimeTheme.fontZh,
              fontSize: 58,
              fontWeight: 700,
              lineHeight: 1.5,
              textAlign: "left",
              display: "inline-block",
            }}
          />
        </div>
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          bottom: 120,
          left: 80,
          right: 80,
          height: 6,
          background: "#222",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${((idx + 1) / total) * 100}%`,
            height: "100%",
            background: crimeTheme.accent,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

export const CrimeEvents: React.FC<{ c: Case; beats: number[] }> = ({ c, beats }) => {
  let cursor = 0;
  return (
    <AbsoluteFill>
      {c.events.map((ev, i) => {
        const from = cursor;
        cursor += beats[i];
        return (
          <Sequence key={i} from={from} durationInFrames={beats[i]}>
            <Audio src={staticFile(`crime/${c.id}/event-${i + 1}.mp3`)} />
            <EventCard
              caseId={c.id}
              idx={i}
              total={c.events.length}
              ev={ev}
              duration={beats[i]}
              audioDur={c.timings.events[i]}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
