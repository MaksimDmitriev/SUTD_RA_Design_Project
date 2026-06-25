import {
  ArrowRight,
  Bot,
  Camera,
  CircleStop,
  Gauge,
  LayoutDashboard,
  Loader2,
  Recycle,
  Save,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import heroImage from "./assets/sortibot-hero.png";

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
  const [view, setView] = useState("project");

  return (
    <main className="page">
      {view === "project" ? (
        <ProjectPage onOpenDashboard={() => setView("dashboard")} />
      ) : (
        <Dashboard onOpenProject={() => setView("project")} />
      )}
    </main>
  );
}

function Nav({ active, onOpenProject, onOpenDashboard }) {
  return (
    <nav className="nav-tabs" aria-label="Main views">
      <button
        className={active === "project" ? "active" : ""}
        onClick={onOpenProject}
        type="button"
      >
        <Bot size={17} />
        Project
      </button>
      <button
        className={active === "dashboard" ? "active" : ""}
        onClick={onOpenDashboard}
        type="button"
      >
        <LayoutDashboard size={17} />
        Dashboard
      </button>
    </nav>
  );
}

function ProjectPage({ onOpenDashboard }) {
  return (
    <>
      <header className="site-header">
        <div>
          <p className="eyebrow">SUTD RA design project</p>
          <h1>SortiBot</h1>
        </div>
        <Nav active="project" onOpenProject={() => {}} onOpenDashboard={onOpenDashboard} />
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="section-kicker">Robot-assisted object sorting</p>
          <h2>Teaching a small robot to see, decide, and sort everyday objects.</h2>
          <p>
            SortiBot is a MasterPi-based research prototype for camera-guided object
            classification. The project combines a live robot dashboard, image capture
            workflow, and CLIP-style inference to separate items into trash, keep, or
            ignore categories.
          </p>
          <div className="hero-actions">
            <button className="primary" onClick={onOpenDashboard} type="button">
              <LayoutDashboard size={18} />
              Open dashboard
            </button>
            <a className="text-link" href="#overview">
              View overview
              <ArrowRight size={16} />
            </a>
          </div>
        </div>
        <div className="hero-visual">
          <img src={heroImage} alt="SortiBot robot sorting objects on a lab bench" />
        </div>
      </section>

      <section className="overview" id="overview" aria-labelledby="overview-title">
        <div className="section-heading">
          <p className="section-kicker">Project goal</p>
          <h2 id="overview-title">A small end-to-end system for practical robot perception.</h2>
        </div>
        <div className="info-grid">
          <article className="info-card">
            <Recycle size={22} />
            <h3>Sort useful categories</h3>
            <p>
              Capture object images and classify them into operational labels that the
              robot can use for sorting decisions.
            </p>
          </article>
          <article className="info-card">
            <Camera size={22} />
            <h3>Use live visual feedback</h3>
            <p>
              Monitor the robot camera stream, collect training examples, and inspect
              recent predictions from a local web interface.
            </p>
          </article>
          <article className="info-card">
            <Gauge size={22} />
            <h3>Keep deployment lightweight</h3>
            <p>
              Run the dashboard and API on the robot network with a small React frontend
              and FastAPI backend.
            </p>
          </article>
        </div>
      </section>

      <section className="build-note" aria-label="System summary">
        <ShieldCheck size={22} />
        <div>
          <h2>Architecture</h2>
          <p>
            The landing page lives inside the existing dashboard frontend, so the project
            website and robot controls share one build, one deployment path, and one URL.
          </p>
        </div>
      </section>
    </>
  );
}

function Dashboard({ onOpenProject }) {
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
    <>
      <header className="site-header">
        <div>
          <p className="eyebrow">MasterPi local dashboard</p>
          <h1>SortiBot</h1>
        </div>
        <div className="header-actions">
          <Nav active="dashboard" onOpenProject={onOpenProject} onOpenDashboard={() => {}} />
          <div className={`state state-${(status?.robot_state || "idle").toLowerCase()}`}>
            {status?.robot_state || "CONNECTING"}
          </div>
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
    </>
  );
}
