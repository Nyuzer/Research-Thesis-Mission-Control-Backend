import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Home } from "lucide-react";

function RacingCar() {
  return (
    <div className="w-full max-w-[700px] h-44 sm:h-80 relative overflow-hidden mx-auto mb-8">
      {/* Road */}
      <div className="absolute bottom-0 left-0 right-0 h-12 sm:h-20">
        {/* Top road edge */}
        <div className="absolute top-0 left-0 right-0 h-[1.5px] bg-primary/25" />
        {/* Center dashes - between the two solid lines */}
        <svg className="absolute top-[22px] sm:top-[38px] left-0 w-[200%] h-4" aria-hidden>
          <line
            x1="0" y1="2" x2="100%" y2="2"
            stroke="currentColor"
            className="text-primary"
            strokeWidth="2.5"
            strokeDasharray="24 18"
            strokeOpacity="0.35"
          >
            <animate attributeName="stroke-dashoffset" from="0" to="-42" dur="0.3s" repeatCount="indefinite" />
          </line>
        </svg>
        {/* Bottom road edge */}
        <div className="absolute bottom-0 left-0 right-0 h-[1.5px] bg-primary/25" />
      </div>

      {/* Wind streaks - straight lines flowing right to left past car */}
      <svg className="absolute left-[15px] sm:left-[50px] bottom-[28px] sm:bottom-[50px] w-[120px] sm:w-[260px] h-[55px] sm:h-[110px] text-primary overflow-visible" aria-hidden>
        {[
          { y: 8,  len: 58, w: 1.5, dur: 0.9,  begin: 0 },
          { y: 22, len: 72, w: 1.8, dur: 0.7,  begin: 0.3 },
          { y: 38, len: 46, w: 1.5, dur: 1.0,  begin: 0.15 },
          { y: 52, len: 65, w: 1.8, dur: 0.65, begin: 0.5 },
          { y: 66, len: 40, w: 1.2, dur: 0.85, begin: 0.7 },
          { y: 78, len: 60, w: 1.5, dur: 0.75, begin: 0.2 },
          { y: 92, len: 52, w: 1.3, dur: 0.9,  begin: 0.45 },
          { y: 16, len: 36, w: 1.2, dur: 0.8,  begin: 0.6 },
          { y: 60, len: 38, w: 1.5, dur: 0.7,  begin: 0.1 },
        ].map((l, i) => (
          <line key={i} x1="0" y1={l.y} x2={l.len} y2={l.y} strokeWidth={l.w} stroke="currentColor" strokeLinecap="round">
            <animateTransform attributeName="transform" type="translate" values={`230,0;${-l.len - 20},0`} dur={`${l.dur}s`} begin={`${l.begin}s`} repeatCount="indefinite" />
            <animate attributeName="opacity" values="0;0.45;0.45;0" keyTimes="0;0.15;0.7;1" dur={`${l.dur}s`} begin={`${l.begin}s`} repeatCount="indefinite" />
          </line>
        ))}
      </svg>

      {/* F1 Car */}
      <div className="absolute left-1/2 -translate-x-[38%] bottom-[8px] sm:bottom-[16px]">
        <svg
          viewBox="0 0 98.751 70"
          className="text-primary w-40 sm:w-80 h-auto"
          fill="currentColor"
          style={{ transform: "scaleX(-1)" }}
        >
          <animateTransform
            attributeName="transform"
            type="translate"
            values="0 0; 0 -1.2; 0 0"
            dur="0.35s"
            repeatCount="indefinite"
          />
          <g>
            {/* Car body */}
            <path d="M78.029,53.801c0-3.049,1.638-5.717,4.072-7.19l-16.177-7.166H55.775c-0.604,0-1.094,0.49-1.094,1.095v1.438
              c0,0.604,0.489,1.095,1.094,1.095h0.72v0.997h-1.841c-0.579,0-1.096,0.371-1.277,0.921L53.23,45.43
              c-3.351-0.271-4.945,2.294-6.62,2.294l-1.131-1.361c-0.674-0.813-1.706-1.241-2.758-1.144c-0.32,0.03-0.661,0.094-1.008,0.211
              l-0.635,2.294c0,0-5.759-0.335-13.245-0.066c1.648,1.537,2.687,3.72,2.687,6.146c0,0.24,0.039,5.32,0.039,5.32h49.383
              c-0.976-1.188-1.637-2.648-1.84-4.266C78.055,54.485,78.029,54.135,78.029,53.801z"/>
            {/* Rear section */}
            <path d="M13.695,53.801c0-1.928,0.659-3.699,1.753-5.12C9.664,49.487,4.044,50.83,0,53.047c0,1.176,5.168,0.019,5.168,2.448H1.181
              c-0.402,0-0.728,0.325-0.728,0.728v2.172c0,0.402,0.325,0.729,0.728,0.729h9.969c0.403,0,0.729-0.326,0.729-0.729v-3.354h1.922
              c-0.009-0.062-0.024-0.121-0.032-0.185C13.72,54.485,13.695,54.135,13.695,53.801z"/>
            {/* Front nose */}
            <path d="M96.938,38.084H86.284c-1.003,0-1.815,0.812-1.815,1.814v2.376c0,0.48,0.191,0.942,0.531,1.282l1.855,1.854
              c4.446,0.218,8,3.893,8,8.391c0,0.111-0.012,0.224-0.017,0.334h3.912V39.899C98.752,38.896,97.939,38.084,96.938,38.084z"/>
            {/* Rear wheel rim */}
            <circle cx="22.106" cy="53.801" r="6.866" />
            {/* Front wheel rim */}
            <circle cx="86.74" cy="53.801" r="6.866" />

            {/* Number 404 on body - mirrored so it reads correctly */}
            <g transform="scale(-1,1) translate(-98.751,0)">
              <text
                x="49.5"
                y="55"
                fill="currentColor"
                fontSize="6.5"
                fontWeight="bold"
                fontFamily="monospace"
                textAnchor="middle"
                className="text-background"
                style={{ fill: "var(--background)" }}
              >
                404
              </text>
            </g>
          </g>

          {/* Rear wheel spokes - spinning, background color on top of filled wheel */}
          <g>
            <animateTransform attributeName="transform" type="rotate" from="0 22.106 53.801" to="360 22.106 53.801" dur="0.8s" repeatCount="indefinite" />
            <line x1="22.106" y1="47.4" x2="22.106" y2="60.2" style={{ stroke: "var(--background)" }} strokeWidth="1.2" />
            <line x1="16.56" y1="50.58" x2="27.65" y2="57.02" style={{ stroke: "var(--background)" }} strokeWidth="1.2" />
            <line x1="16.56" y1="57.02" x2="27.65" y2="50.58" style={{ stroke: "var(--background)" }} strokeWidth="1.2" />
            <circle cx="22.106" cy="53.801" r="2.2" style={{ fill: "var(--background)" }} />
          </g>

          {/* Front wheel spokes - spinning, background color on top of filled wheel */}
          <g>
            <animateTransform attributeName="transform" type="rotate" from="0 86.74 53.801" to="360 86.74 53.801" dur="0.8s" repeatCount="indefinite" />
            <line x1="86.74" y1="47.4" x2="86.74" y2="60.2" style={{ stroke: "var(--background)" }} strokeWidth="1.2" />
            <line x1="81.2" y1="50.58" x2="92.28" y2="57.02" style={{ stroke: "var(--background)" }} strokeWidth="1.2" />
            <line x1="81.2" y1="57.02" x2="92.28" y2="50.58" style={{ stroke: "var(--background)" }} strokeWidth="1.2" />
            <circle cx="86.74" cy="53.801" r="2.2" style={{ fill: "var(--background)" }} />
          </g>
        </svg>
      </div>
    </div>
  );
}

export default function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 text-center">
      <RacingCar />
      <p className="text-lg text-muted-foreground mb-1">Page not found</p>
      <p className="text-sm text-muted-foreground/70 mb-6">
        This route doesn't exist. The robot drove past it.
      </p>
      <Link to="/">
        <Button variant="outline" className="gap-2">
          <Home className="h-4 w-4" />
          Back to Dashboard
        </Button>
      </Link>
    </div>
  );
}
