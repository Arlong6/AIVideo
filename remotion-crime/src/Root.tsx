import { Composition } from "remotion";
import { CrimeReel } from "./crime/CrimeReel";
import { cases } from "./crime/data";
import { CRIME_FPS, CRIME_HEIGHT, CRIME_WIDTH, totalFrames } from "./crime/theme";

// Standalone crime-only Remotion root. Extracted from the multi-content
// nihongo-reels project so the AIVideo (crime) pipeline owns its renderer and
// no longer depends on the separate nihongo-manabi repo. The `Crime` composition
// is what scripts/render-crime.sh renders, with the real case injected via --props.
export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* Per-case ids — handy in Remotion Studio for previewing baked cases. */}
      {cases.map((c) => (
        <Composition
          key={c.id}
          id={`Crime-${c.id}`}
          component={CrimeReel}
          durationInFrames={totalFrames(c.timings)}
          fps={CRIME_FPS}
          width={CRIME_WIDTH}
          height={CRIME_HEIGHT}
          defaultProps={{ c }}
        />
      ))}
      {/* The render target — duration is recomputed from the injected case. */}
      <Composition
        id="Crime"
        component={CrimeReel}
        fps={CRIME_FPS}
        width={CRIME_WIDTH}
        height={CRIME_HEIGHT}
        durationInFrames={totalFrames(cases[0].timings)}
        defaultProps={{ c: cases[0] }}
        calculateMetadata={({ props }) => ({
          durationInFrames: totalFrames(props.c.timings),
        })}
      />
    </>
  );
};
