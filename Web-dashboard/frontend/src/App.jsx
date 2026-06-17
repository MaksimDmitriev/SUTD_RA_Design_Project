import { Camera, CircleStop, Loader2, Save, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function api(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

export default function App() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState("");

  const streamUrl = useMemo(() => `${API_BASE}/api/stream.mjpg`, []);

  async function refreshStatus() {
    const next = await api("/api/status");
    setStatus(next);
  }

  useEffect(() => {
    refreshStatus().catch((error) => setMessage(error.message));
    const id = window.setInterval(() => {
      refreshStatus().catch(() => {});
    }, 1500);
    return () => window.clearInterval(id);
  }, []);

  async function capture(label) {
    setBusy(label);
    setMessage("");
    try {
      const result = await api(`/api/capture/${label}`, { method: "POST" });
      setMessage(`Saved ${result.label}: ${result.path}`);
      await refreshStatus();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(null);
    }
  }

  async function predict() {
    setBusy("predict");
    setMessage("");
    try {
      const result = await api("/api/predict", { method: "POST" });
      setMessage(`Prediction: ${result.label} (${Math.round(result.confidence * 100)}%)`);
      await refreshStatus();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(null);
    }
  }

  const prediction = status?.last_prediction;

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">MasterPi local dashboard</p>
          <h1>SortiBot</h1>
        </div>
        <div className={`state state-${(status?.robot_state || "idle").toLowerCase()}`}>
          {status?.robot_state || "CONNECTING"}
        </div>
      </header>

      <section className="workspace">
        <div className="video-panel">
          <div className="panel-title">
            <Camera size={18} />
            <span>Live camera</span>
          </div>
          <img className="video" src={streamUrl} alt="Robot camera stream" />
        </div>

        <aside className="side-panel">
          <section className="card">
            <h2>Capture</h2>
            <div className="button-grid">
              <button onClick={() => capture("trash")} disabled={!!busy}>
                <Save size={17} />
                Trash
              </button>
              <button onClick={() => capture("keep")} disabled={!!busy}>
                <Save size={17} />
                Keep
              </button>
              <button onClick={() => capture("ignore")} disabled={!!busy}>
                <Save size={17} />
                Ignore
              </button>
            </div>
          </section>

          <section className="card">
            <h2>Inference</h2>
            <button className="primary" onClick={predict} disabled={!!busy}>
              {busy === "predict" ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
              Predict current frame
            </button>
            {prediction && (
              <div className="prediction">
                <strong>{prediction.label}</strong>
                <span>{Math.round(prediction.confidence * 100)}%</span>
                <small>{prediction.prompt}</small>
              </div>
            )}
          </section>

          <section className="card">
            <h2>System</h2>
            <dl>
              <div>
                <dt>Classifier</dt>
                <dd>{status?.classifier_available ? "Loaded" : "Not loaded"}</dd>
              </div>
              <div>
                <dt>Last capture</dt>
                <dd>{status?.last_capture || "None"}</dd>
              </div>
              <div>
                <dt>Error</dt>
                <dd>{status?.last_error || status?.classifier_error || "None"}</dd>
              </div>
            </dl>
          </section>

          <section className="message" aria-live="polite">
            <CircleStop size={16} />
            <span>{message || "Ready"}</span>
          </section>
        </aside>
      </section>
    </main>
  );
}
