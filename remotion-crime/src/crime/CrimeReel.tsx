import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { CRIME_FPS, sceneFrames, totalFrames } from "./theme";
import { CrimeHook } from "./scenes/CrimeHook";
import { CrimeSetup } from "./scenes/CrimeSetup";
import { CrimeEvents } from "./scenes/CrimeEvents";
import { CrimeTwist } from "./scenes/CrimeTwist";
import { CrimeAftermath } from "./scenes/CrimeAftermath";
import { CrimeCTA } from "./scenes/CrimeCTA";
import { LocationBadge } from "./LocationBadge";
import { ProgressBar } from "./ProgressBar";
import type { Case } from "./data";

export type CrimeReelProps = { c: Case };

export const CrimeReel: React.FC<CrimeReelProps> = ({ c }) => {
  const s = sceneFrames(c.timings);
  const total = totalFrames(c.timings);

  let cursor = 0;
  const at = (d: number) => {
    const from = cursor;
    cursor += d;
    return from;
  };

  return (
    <AbsoluteFill>
      <Audio
        src={staticFile("music/crime-bgm.mp3")}
        volume={(f) => {
          // Dynamic ducking: quieter during speech, louder during breath pads.
          // Scene transitions happen at cumulative offsets; each has a 1.2s
          // (36-frame) breath pad where no narration plays — let BGM breathe.
          const fadeIn = Math.min(1, f / (CRIME_FPS * 1.5));
          const fadeOut = Math.min(1, (total - f) / (CRIME_FPS * 1.5));
          const envelope = Math.min(fadeIn, fadeOut);

          // Build transition boundaries from scene frame lengths
          const scenes = [s.hook, s.setup, ...s.events, s.twist, s.aftermath, s.cta];
          let acc = 0;
          let inBreath = false;
          const breathFrames = Math.round(CRIME_FPS * 1.2); // 1.2s pad
          for (const dur of scenes) {
            const speechEnd = acc + dur - breathFrames;
            if (f >= speechEnd && f < acc + dur) {
              inBreath = true;
              break;
            }
            acc += dur;
          }

          // Speech: 12% volume. Breath pad: 35% (let BGM fill the gap).
          const baseVol = inBreath ? 0.35 : 0.12;
          return baseVol * envelope;
        }}
      />
      {/* Location badge spans Hook + Setup scenes */}
      <Sequence from={0} durationInFrames={s.hook + s.setup}>
        <LocationBadge location={c.location} date={c.date} delayFrames={20} />
      </Sequence>

      {/* Progress bar spans entire video */}
      <ProgressBar totalFrames={total} />

      <Sequence from={at(s.hook)} durationInFrames={s.hook}>
        <CrimeHook c={c} duration={s.hook} />
      </Sequence>
      <Sequence from={at(s.setup)} durationInFrames={s.setup}>
        <CrimeSetup c={c} duration={s.setup} />
      </Sequence>
      <Sequence
        from={at(s.events.reduce((a, b) => a + b, 0))}
        durationInFrames={s.events.reduce((a, b) => a + b, 0)}
      >
        <CrimeEvents c={c} beats={s.events} />
      </Sequence>
      <Sequence from={at(s.twist)} durationInFrames={s.twist}>
        <CrimeTwist c={c} duration={s.twist} />
      </Sequence>
      <Sequence from={at(s.aftermath)} durationInFrames={s.aftermath}>
        <CrimeAftermath c={c} duration={s.aftermath} />
      </Sequence>
      <Sequence from={at(s.cta)} durationInFrames={s.cta}>
        <CrimeCTA c={c} />
      </Sequence>
    </AbsoluteFill>
  );
};
