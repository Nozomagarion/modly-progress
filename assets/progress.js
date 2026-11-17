// Modly Progress: uses the host's existing workflow store; no network requests.
function modlyProgressSeconds(value) {
  const seconds = Math.max(0, Math.floor(value));
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

function modlyProgressView(run, elapsed) {
  const step = String(run.blockStep || "En cours…");
  const diffusion = /Diffusion (\d+)\/(\d+)/.exec(step);
  const decoding = /Décodage|Decoding|Export/i.test(step);
  const loading = /Loading|Submitting|chargement/i.test(step);
  const raw = Number(run.blockProgress);
  const percent = Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : null;
  if (diffusion && Number(diffusion[2]) > 0) {
    const done = Number(diffusion[1]), total = Number(diffusion[2]);
    return { step, percent: Math.min(100, Math.round(100 * done / total)),
      caption: `Étapes de diffusion : ${done}/${total}`,
      eta: elapsed >= 5 && done > 0 && done < total
        ? `Diffusion restante ≈ ${modlyProgressSeconds(elapsed * (total - done) / done)}`
        : "Décodage et export à suivre" };
  }
  return { step, percent: loading || decoding ? null : percent,
    caption: loading || decoding ? "Progression de cette phase inconnue" : "Progression signalée par le modèle (peut être estimée)",
    eta: "Temps restant inconnu" };
}

function modlyProgressUpdateClock(snapshot, clock, now) {
  const active = snapshot.activeNodeId != null && ["running", "paused"].includes(snapshot.runState.status);
  if (!active) {
    clock.running = false;
    return;
  }
  const phase = /Diffusion \d+\/\d+/.test(snapshot.runState.blockStep || "") ? "diffusion" : "other";
  if (!clock.running || clock.nodeId !== snapshot.activeNodeId || clock.workflowId !== snapshot.activeWorkflowId) {
    clock.startedAt = now;
    clock.phaseStartedAt = now;
    clock.phase = phase;
  } else if (clock.phase !== phase) {
    clock.phaseStartedAt = now;
    clock.phase = phase;
  }
  clock.running = true;
  clock.nodeId = snapshot.activeNodeId;
  clock.workflowId = snapshot.activeWorkflowId;
}

// The two UI pages share this clock, so navigating does not reset elapsed time.
const modlyProgressClock = globalThis.__modlyProgressClockV1 ?? (globalThis.__modlyProgressClockV1 = {});
if (!modlyProgressClock.subscribed) {
  modlyProgressUpdateClock(useWorkflowRunStore.getState(), modlyProgressClock, Date.now());
  useWorkflowRunStore.subscribe((snapshot) => modlyProgressUpdateClock(snapshot, modlyProgressClock, Date.now()));
  modlyProgressClock.subscribed = true;
}

function ModlyProgressPanel({ nodeId }) {
  const activeId = useWorkflowRunStore((s) => s.activeNodeId);
  const run = useWorkflowRunStore((s) => s.runState);
  const active = (nodeId === undefined || activeId === nodeId) && activeId != null && (run.status === "running" || run.status === "paused");
  const [seconds, setSeconds] = reactExports.useState(0);
  const phaseKey = /Diffusion \d+\/\d+/.test(run.blockStep || "") ? "diffusion" : "other";
  const [phaseSeconds, setPhaseSeconds] = reactExports.useState(0);
  reactExports.useEffect(() => {
    if (!active) return;
    const start = modlyProgressClock.startedAt ?? Date.now();
    setSeconds((Date.now() - start) / 1000);
    const timer = setInterval(() => setSeconds((Date.now() - start) / 1000), 1000);
    return () => clearInterval(timer);
  }, [active, activeId]);
  reactExports.useEffect(() => {
    if (!active) return;
    const start = modlyProgressClock.phaseStartedAt ?? Date.now();
    setPhaseSeconds((Date.now() - start) / 1000);
    const timer = setInterval(() => setPhaseSeconds((Date.now() - start) / 1000), 1000);
    return () => clearInterval(timer);
  }, [active, activeId, phaseKey]);
  if (!active) return null;
  const view = modlyProgressView(run, phaseSeconds);
  const h = jsxRuntimeExports.jsx, hs = jsxRuntimeExports.jsxs;
  return hs("div", { "data-modly-progress": "1", className: "nodrag nopan", style: {
    flexShrink: 0, padding: "10px 12px", borderTop: "1px solid #3f3f46", background: "#171525",
    color: "#e4e4e7", fontSize: "11px", lineHeight: "1.5", minWidth: 190
  }, children: [
    hs("div", { style: { display: "flex", justifyContent: "space-between", gap: 8 }, children: [
      h("strong", { children: run.status === "paused" ? "En pause" : "En cours" }),
      h("strong", { style: { color: "#c4b5fd", fontVariantNumeric: "tabular-nums" }, children: view.percent == null ? "—" : `${view.percent} %` })
    ] }),
    h("div", { role: "progressbar", "aria-label": view.caption, "aria-valuemin": 0, "aria-valuemax": 100,
      ...(view.percent == null ? {} : { "aria-valuenow": view.percent }),
      style: { height: 6, margin: "6px 0", background: "#3f3f46", borderRadius: 4, overflow: "hidden" },
      children: h("div", { style: { height: "100%", width: `${view.percent ?? 30}%`,
        background: "#a78bfa", borderRadius: 4, transition: "width .3s" }, className: view.percent == null ? "animate-pulse" : "" }) }),
    h("div", { style: { overflowWrap: "anywhere" }, children: view.step }),
    h("div", { style: { color: "#a1a1aa", fontSize: 10 }, children: view.caption }),
    h("div", { style: { marginTop: 4, fontVariantNumeric: "tabular-nums" }, children: `Écoulé : ${modlyProgressSeconds(seconds)}` }),
    h("div", { style: { color: "#a1a1aa", fontSize: 10 }, children: view.eta })
  ] });
}
