import timings300m from "./timings/300m-yen.json";

export type CrimeEvent = { text: string; icon?: string; image?: string };

export type CaseTimings = {
  hook: number;
  setup: number;
  events: number[];
  twist: number;
  aftermath: number;
  cta: number;
};

export type Case = {
  id: string;
  title: string;
  titleZh: string;
  date: string;
  location: string;
  status: "unsolved" | "solved";
  statusLabel: string;
  hook: string;
  hookImage?: string;
  setup: string;
  setupImage?: string;
  events: CrimeEvent[];
  twist: string;
  twistImage?: string;
  aftermath: string;
  aftermathImage?: string;
  cta: string;
  has_longform?: boolean;
  credits?: string;
  timings: CaseTimings;
};

export const cases: Case[] = [
  {
    id: "300m-yen",
    title: "三億円事件",
    titleZh: "三億日圓搶案",
    date: "1968年12月10日",
    location: "東京都府中市",
    status: "unsolved",
    statusLabel: "未偵破",
    hook: "日本史上最離奇的劫案——警方追了七年，連一個嫌犯都找不到。他們到底怎麼做到的？",
    hookImage: "images/tokyo_1960s.jpg",
    setup: "1968年12月，東京府中。運鈔車上的四人，不知道即將遇到什麼。",
    setupImage: "images/fuchu.jpg",
    events: [
      { text: "一名騎白色警用摩托車的警察，突然攔下運鈔車。", image: "images/police.jpg" },
      { text: "「車上被裝了炸彈，快下車！」警察大喊，鑽到車底檢查。", image: "images/cedric.jpg" },
      { text: "突然一陣白煙冒出——「要爆炸了，快逃！」", image: "images/smoke.jpg" },
      { text: "四人躲遠，回頭一看。運鈔車不見了。", image: "images/cedric.jpg" },
    ],
    twist: "白煙是煙霧彈。摩托車是噴漆的假貨。警察，是假扮的。三億日圓，在光天化日下蒸發。",
    twistImage: "images/yen.jpg",
    aftermath: "警方公開嫌犯的蒙太奇畫像，動員全國追查七年。1975年公訴時效到期，1988年連民事追訴都結束。那七年的追查，化為一場空。嫌犯的真實身份，至今成謎。",
    aftermathImage: "images/fuchu.jpg",
    cta: "追蹤看更多真實懸案",
    credits: "照片來源：Wikimedia Commons",
    timings: timings300m,
  },
];
