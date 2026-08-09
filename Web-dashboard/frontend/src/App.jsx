import {
  ArrowRight,
  Bot,
  Camera,
  CircleStop,
  Gauge,
  Github,
  LayoutDashboard,
  Recycle,
  Save,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import heroImage from "./assets/gripper-extension-oblique.jpg";
import roomTrialImage from "./assets/sortibot-room-trial.jpg";

const FIELD_TRIALS_URL =
  "https://drive.google.com/drive/folders/1aTqLLz3d6wR7lSvsIrgBU444h8DdISaR";

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
  const [view, setView] = useState(() =>
    window.location.hash === "#dashboard" ? "dashboard" : "project",
  );

  useEffect(() => {
    function syncHash() {
      setView(window.location.hash === "#dashboard" ? "dashboard" : "project");
    }

    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  function openProject() {
    window.location.hash = "";
    setView("project");
  }

  return (
    <main className="page">
      {view === "project" ? (
        <ProjectPage />
      ) : (
        <Dashboard onOpenProject={openProject} />
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

function ProjectPage() {
  return (
    <>
      <header className="site-header">
        <div>
          <p className="eyebrow">SUTD RA design project</p>
          <h1>SortiBot</h1>
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="section-kicker">Vision-guided object sorting</p>
          <h2>A mobile robot that sees, approaches, picks, and sorts.</h2>
          <p>
            SortiBot is a MasterPi-based research prototype that uses a custom YOLO11n
            model to detect objects, estimate their position on the floor, approach them,
            and route them to class-specific release positions. The current demonstration
            uses two classes—red useful objects and purple trash—but the neural network
            can be retrained with labelled images of additional objects.
          </p>
          <div className="hero-actions">
            <a className="text-link" href="#how-it-works">
              See how it works
              <ArrowRight size={16} />
            </a>
            <a
              className="text-link"
              href="https://github.com/MaksimDmitriev/SUTD_RA_Design_Project"
              rel="noreferrer"
              target="_blank"
            >
              <Github size={16} />
              View source on GitHub
            </a>
          </div>
        </div>
        <div className="hero-visual">
          <img
            src={heroImage}
            alt="The actual SortiBot with custom PLA gripper extensions approaching demonstration objects"
          />
        </div>
      </section>

      <section className="overview" id="overview" aria-labelledby="overview-title">
        <div className="section-heading">
          <p className="section-kicker">System overview</p>
          <h2 id="overview-title">An end-to-end pipeline from camera frame to sorting action.</h2>
        </div>
        <div className="info-grid">
          <article className="info-card">
            <Camera size={22} />
            <h3>Custom on-robot perception</h3>
            <p>
              A two-class YOLO11n detector recognizes the red useful and purple trash
              demonstration objects. Its NCNN export runs locally on the Raspberry Pi.
            </p>
          </article>
          <article className="info-card">
            <Gauge size={22} />
            <h3>Geometry-guided approach</h3>
            <p>
              Floor projection estimates forward and lateral position. The chassis moves
              conservatively, stops, corrects its heading, and measures again.
            </p>
          </article>
          <article className="info-card">
            <Recycle size={22} />
            <h3>Class-directed sorting</h3>
            <p>
              The arm visually refines the grab position, attempts the pickup, and uses
              the detector label to choose the useful or trash release pose.
            </p>
          </article>
        </div>
      </section>

      <section className="project-section" id="how-it-works" aria-labelledby="workflow-title">
        <div className="section-heading">
          <p className="section-kicker">How SortiBot works</p>
          <h2 id="workflow-title">A measured, repeatable sequence rather than one long move.</h2>
          <p>
            Each stage can be tested independently, which helped separate perception,
            chassis, camera, and arm problems during development.
          </p>
        </div>
        <ol className="workflow-grid">
          <li className="workflow-step">
            <span>01</span>
            <h3>Observe</h3>
            <p>The robot camera captures the latest view of the floor.</p>
          </li>
          <li className="workflow-step">
            <span>02</span>
            <h3>Detect</h3>
            <p>YOLO identifies a red useful or purple trash demonstration object.</p>
          </li>
          <li className="workflow-step">
            <span>03</span>
            <h3>Locate</h3>
            <p>The box bottom-centre is projected onto the floor to estimate position.</p>
          </li>
          <li className="workflow-step">
            <span>04</span>
            <h3>Approach</h3>
            <p>The chassis moves partway, corrects its heading, stops, and remeasures.</p>
          </li>
          <li className="workflow-step">
            <span>05</span>
            <h3>Pick</h3>
            <p>The arm aligns above the target, descends, closes the gripper, and lifts.</p>
          </li>
          <li className="workflow-step">
            <span>06</span>
            <h3>Sort</h3>
            <p>The detected class selects a release pose before the arm returns home.</p>
          </li>
        </ol>
      </section>

      <section className="project-section" aria-labelledby="results-title">
        <div className="section-heading">
          <p className="section-kicker">Verified results</p>
          <h2 id="results-title">Evidence from the implemented and tested system.</h2>
        </div>
        <div className="results-grid">
          <article className="result-card">
            <strong>276</strong>
            <h3>Robot-camera images</h3>
            <p>84 red useful, 102 purple trash, and 90 ignore or hard-negative scenes.</p>
          </article>
          <article className="result-card">
            <strong>NCNN</strong>
            <h3>Embedded deployment</h3>
            <p>The custom YOLO11n model was visually validated, exported, and loaded on the robot.</p>
          </article>
          <article className="result-card">
            <strong>≈11×</strong>
            <h3>Faster model training</h3>
            <p>Apple Silicon MPS took about 0.080 hours versus 0.90 hours on CPU.</p>
          </article>
          <article className="result-card">
            <strong>19 cm/s</strong>
            <h3>Measured forward speed</h3>
            <p>Speed 24 moved the physical robot approximately 38 cm in two seconds.</p>
          </article>
        </div>
        <div className="training-note">
          <ShieldCheck size={22} />
          <div>
            <h3>Designed for retraining</h3>
            <p>
              Preparing the two-class demonstration took a few hours across robot-camera
              image capture, data labelling, and neural-network training. Training on the
              Mac made iteration practical, and the same workflow can add more labelled
              object classes later.
            </p>
          </div>
        </div>
      </section>

      <section className="project-section" aria-labelledby="field-trials-title">
        <div className="section-heading">
          <p className="section-kicker">Field trials</p>
          <h2 id="field-trials-title">Recovery is part of the cleaning loop.</h2>
        </div>
        <div className="field-trial">
          <img
            src={roomTrialImage}
            alt="SortiBot in a multi-object floor trial with its custom gripper and collection basket"
          />
          <div className="field-trial-copy">
            <p>
              Long-form tests include imperfect interactions, such as a missed pickup or
              an object being knocked over. The robot does not treat one unsuccessful
              attempt as the end of the run: it resumes scanning, selects a remaining
              target, and continues the cleaning cycle.
            </p>
            <p>
              The recordings are qualitative evidence of this scan–act–rescan behaviour
              and eventual surface clearing. They are not a measured grasp-success rate.
            </p>
            <a
              className="text-link"
              href={FIELD_TRIALS_URL}
              rel="noreferrer"
              target="_blank"
            >
              View full test recordings
              <ArrowRight size={16} />
            </a>
          </div>
        </div>
      </section>

      <section className="build-note" aria-label="System summary">
        <ShieldCheck size={22} />
        <div>
          <h2>Architecture</h2>
          <p>
            The public project page and robot-local capture dashboard share one React/Vite
            frontend and deployment path. FastAPI serves the built site, camera stream,
            capture endpoints, and robot status on the local network.
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
            <h2>System</h2>
            <dl>
              <div>
                <dt>Last capture</dt>
                <dd>{status?.last_capture || "None"}</dd>
              </div>
              <div>
                <dt>Error</dt>
                <dd>{status?.last_error || "None"}</dd>
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
