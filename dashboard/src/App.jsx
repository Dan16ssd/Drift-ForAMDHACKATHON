import React, { useEffect, useMemo, useRef, useState } from "react";

const POLL_MS = 3000;

function useJson(url, fallback) {
  const [data, setData] = useState(fallback);
  useEffect(() => {
    if (!url) return undefined;
    let alive = true;
    const tick = () =>
      fetch(url)
        .then((r) => (r.ok ? r.json() : fallback))
        .then((d) => alive && setData(d))
        .catch(() => {});
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [url]);
  return data;
}

const fmtTime = (iso) =>
  new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/* ---- charts (inline SVG, 2px lines, recessive grid, hover tooltip) ---- */

function QualityChart({ rows, floor }) {
  const wrapRef = useRef(null);
  const [hover, setHover] = useState(null);
  const W = 900;
  const H = 220;
  const pad = { l: 34, r: 10, t: 10, b: 20 };

  const pts = useMemo(
    () =>
      rows.map((r, i) => ({
        i,
        ts: r.ts,
        q: r.features.quality,
        verdict: r.verdict,
      })),
    [rows]
  );
  if (pts.length < 2) return <div className="empty">waiting for data…</div>;

  const x = (i) => pad.l + (i / (pts.length - 1)) * (W - pad.l - pad.r);
  const y = (q) => pad.t + (1 - q) * (H - pad.t - pad.b);
  const path = pts.map((p, k) => `${k ? "L" : "M"}${x(p.i).toFixed(1)},${y(p.q).toFixed(1)}`).join(" ");

  const onMove = (e) => {
    const box = wrapRef.current.getBoundingClientRect();
    const fx = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((fx - pad.l) / (W - pad.l - pad.r)) * (pts.length - 1));
    if (i >= 0 && i < pts.length) {
      const p = pts[i];
      setHover({ p, left: (x(p.i) / W) * box.width, top: (y(p.q) / H) * box.height });
    }
  };

  return (
    <div ref={wrapRef} style={{ position: "relative" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", display: "block" }} role="img" aria-label="Quality over time">
        {[0.2, 0.4, 0.6, 0.8, 1.0].map((g) => (
          <g key={g}>
            <line x1={pad.l} x2={W - pad.r} y1={y(g)} y2={y(g)} stroke="var(--grid)" strokeWidth="1" />
            <text x={pad.l - 6} y={y(g) + 4} textAnchor="end" fontSize="10" fill="var(--muted)">
              {g.toFixed(1)}
            </text>
          </g>
        ))}
        <line x1={pad.l} x2={W - pad.r} y1={y(floor)} y2={y(floor)} stroke="var(--status-critical)" strokeWidth="1.5" strokeDasharray="6 5" />
        <text x={W - pad.r} y={y(floor) - 5} textAnchor="end" fontSize="10" fill="var(--status-critical)">
          quality floor {floor}
        </text>
        <path d={path} fill="none" stroke="var(--series-1)" strokeWidth="2" strokeLinejoin="round" />
        {hover && (
          <g>
            <line x1={x(hover.p.i)} x2={x(hover.p.i)} y1={pad.t} y2={H - pad.b} stroke="var(--baseline)" strokeWidth="1" />
            <circle cx={x(hover.p.i)} cy={y(hover.p.q)} r="4" fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth="2" />
          </g>
        )}
        <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="var(--baseline)" strokeWidth="1" />
      </svg>
      {hover && (
        <div className="tooltip" style={{ left: hover.left, top: hover.top }}>
          <span className="k">{fmtTime(hover.p.ts)}</span> · quality{" "}
          <b>{hover.p.q.toFixed(2)}</b>
          {hover.p.verdict ? ` · ${hover.p.verdict}` : ""}
        </div>
      )}
    </div>
  );
}

function Sparkline({ rows, feature, name, color, fmt }) {
  const W = 220;
  const H = 46;
  const vals = rows.map((r) => r.features[feature]).filter((v) => v != null);
  if (vals.length < 2) return null;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i) => (i / (vals.length - 1)) * (W - 4) + 2;
  const y = (v) => 4 + (1 - (v - min) / span) * (H - 8);
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = vals[vals.length - 1];
  return (
    <div className="card spark">
      <div className="name">
        {name} · <span className="last">{fmt ? fmt(last) : last.toFixed(2)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", display: "block" }} role="img" aria-label={name}>
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

/* ---- panels ---- */

function CountdownBanner({ event }) {
  if (!event || !event.payload) return null;
  const cd = event.payload.countdown || {};
  const range =
    cd.hours_high != null ? `${cd.hours_low}–${cd.hours_high}h` : `~${cd.hours_best}h`;
  return (
    <div className="card banner">
      <span className="badge ALERT">
        <span className="dot" /> ALERT
      </span>
      <span className="clock">{range} to floor</span>
      <span className="cause">{event.payload.sentence}</span>
      <span className="evidence">
        evidence: {cd.cause_evidence} · n={cd.n} · R²={cd.r2}
      </span>
    </div>
  );
}

function PrecisionTiles({ report, streams, rowsSeen }) {
  const p = report.precision;
  return (
    <div className="grid tiles">
      <div className="card tile">
        <div className="label">Alert precision (self-scored)</div>
        <div className="value">{p == null ? "—" : `${Math.round(p * 100)}%`}</div>
        <div className="hint">
          {report.alerts_confirmed}/{report.alerts_resolved} resolved alerts confirmed
        </div>
      </div>
      <div className="card tile">
        <div className="label">Alerts raised</div>
        <div className="value">{report.alerts_total}</div>
        <div className="hint">each one survived cross-examination</div>
      </div>
      <div className="card tile">
        <div className="label">Responses scored</div>
        <div className="value">{rowsSeen}</div>
        <div className="hint">every response, continuously</div>
      </div>
      <div className="card tile">
        <div className="label">Streams watched</div>
        <div className="value">{streams.length}</div>
        <div className="hint">production AI pipelines</div>
      </div>
    </div>
  );
}

function Transcript({ debate, onClose }) {
  if (!debate) return null;
  return (
    <div className="card transcript">
      <button className="close" onClick={onClose}>
        close
      </button>
      <h3>
        Hearing <span className="badge" style={{ marginLeft: 6 }}>{debate.id.slice(0, 8)}</span>{" "}
        <span className={`badge ${debate.verdict}`}>
          <span className="dot" /> {debate.verdict}
        </span>
      </h3>
      <div className="turn">
        <div className="who">Prosecutor (Qwen3-30B)</div>
        <div className="said">{debate.prosecutor_argument}</div>
      </div>
      <div className="turn">
        <div className="who">Defense (Qwen3-30B)</div>
        <div className="said">{debate.defense_argument}</div>
      </div>
      <div className="turn">
        <div className="who">Judge (Qwen3-235B)</div>
        <div className="said">{debate.reasoning}</div>
      </div>
      <div className="cited">cited ledger rows: {(debate.cited_rows || []).join(", ") || "—"}</div>
      <pre>{JSON.stringify(debate.evidence, null, 2)}</pre>
    </div>
  );
}

function VerdictFeed({ debates, onOpen }) {
  if (!debates.length) return <div className="empty">no hearings yet</div>;
  return (
    <div className="feed">
      {debates.map((d) => (
        <div key={d.id} className="card item" onClick={() => onOpen(d.id)}>
          <span className={`badge ${d.verdict}`}>
            <span className="dot" /> {d.verdict}
          </span>{" "}
          <span className="when">{fmtTime(d.ts)}</span>
          <div className="reason">{d.reasoning}</div>
        </div>
      ))}
    </div>
  );
}

/* ---- app ---- */

export default function App() {
  const health = useJson("/health", {});
  const streams = useJson("/api/streams", []);
  const [streamId, setStreamId] = useState(null);
  const active = streamId || (streams[0] && streams[0].stream_id);

  const rows = useJson(active ? `/api/streams/${active}/window?limit=300` : null, []);
  const debates = useJson(active ? `/api/streams/${active}/debates` : null, []);
  const countdownEv = useJson(active ? `/api/streams/${active}/countdown` : null, {});
  const precisionRep = useJson("/api/precision", {
    alerts_total: 0,
    alerts_resolved: 0,
    alerts_confirmed: 0,
    precision: null,
  });

  const [openDebate, setOpenDebate] = useState(null);
  const debate = useMemo(
    () => debates.find((d) => d.id === openDebate) || null,
    [debates, openDebate]
  );

  const floor = health.quality_floor ?? 0.6;
  const alertActive =
    countdownEv && countdownEv.payload && debates[0] && debates[0].verdict === "ALERT";

  return (
    <div className="shell">
      <header className="top">
        <h1>DRIFT</h1>
        <span className="sub">early-warning for AI quality degradation</span>
        <span className="mode">llm: {health.llm_mode || "…"} · floor {floor}</span>
      </header>

      <PrecisionTiles report={precisionRep} streams={streams} rowsSeen={rows.length} />

      {streams.length > 1 && (
        <div className="streambar" style={{ marginTop: 14 }}>
          {streams.map((s) => (
            <button
              key={s.stream_id}
              className={s.stream_id === active ? "active" : ""}
              onClick={() => setStreamId(s.stream_id)}
            >
              {s.stream_id} ({s.rows})
            </button>
          ))}
        </div>
      )}

      {alertActive && (
        <>
          <div className="section-title">Countdown</div>
          <CountdownBanner event={countdownEv} />
        </>
      )}

      <div className="section-title">Quality — {active || "no stream"}</div>
      <div className="grid two">
        <div className="card">
          <QualityChart rows={rows} floor={floor} />
        </div>
        <div>
          <VerdictFeed debates={debates} onOpen={setOpenDebate} />
        </div>
      </div>

      <div className="section-title">Sensor channels</div>
      <div className="grid sparks">
        <Sparkline rows={rows} feature="retrieval_hit_ratio" name="retrieval hit ratio" color="var(--series-2)" />
        <Sparkline rows={rows} feature="hedge_rate" name="hedging / 100 words" color="var(--series-3)" />
        <Sparkline rows={rows} feature="adherence" name="instruction adherence" color="var(--series-4)" />
        <Sparkline rows={rows} feature="latency_ms" name="latency" color="var(--series-5)" fmt={(v) => `${Math.round(v)}ms`} />
      </div>

      <Transcript debate={debate} onClose={() => setOpenDebate(null)} />
    </div>
  );
}
