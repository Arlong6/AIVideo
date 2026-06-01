import type { CaseTimings } from "./data";

export const crimeTheme = {
  bg: "#000000",
  bgGradient: "linear-gradient(180deg, #0a0a0a 0%, #1a0000 100%)",
  text: "#f4f1e8",
  muted: "#8a8578",
  accent: "#c8102e",
  tape: "#ffd500",
  paper: "#e8e2d0",
  ink: "#1a1a1a",
  fontSerif: '"Times New Roman", "PingFang TC", "Songti TC", serif',
  fontMono: '"Courier New", "Menlo", monospace',
  fontZh: '"PingFang TC", "Hiragino Sans TC", "Microsoft JhengHei", sans-serif',
};

export const CRIME_FPS = 30;
export const CRIME_WIDTH = 1080;
export const CRIME_HEIGHT = 1920;

export const CRIME_BREATH_SEC = 1.2; // silence after each sentence
export const CRIME_CTA_BUFFER_SEC = 0.5;

const secToFrames = (sec: number) => Math.ceil(sec * CRIME_FPS);

export const sceneFrames = (t: CaseTimings) => ({
  hook: secToFrames(t.hook + CRIME_BREATH_SEC),
  setup: secToFrames(t.setup + CRIME_BREATH_SEC),
  events: t.events.map((e) => secToFrames(e + CRIME_BREATH_SEC)),
  twist: secToFrames(t.twist + CRIME_BREATH_SEC),
  aftermath: secToFrames(t.aftermath + CRIME_BREATH_SEC),
  cta: secToFrames(t.cta + CRIME_CTA_BUFFER_SEC),
});

export const totalFrames = (t: CaseTimings) => {
  const s = sceneFrames(t);
  return (
    s.hook +
    s.setup +
    s.events.reduce((a, b) => a + b, 0) +
    s.twist +
    s.aftermath +
    s.cta
  );
};
