// A.R.I.A. — Fluid Nebula Visualizer

const orb    = document.getElementById('orb');
const status = document.getElementById('status');
const canvas = document.getElementById('aria-canvas');
const ctx2d  = canvas.getContext('2d');

let ws;
let audioQueue    = [];
let isPlaying     = false;
let audioCtx      = null;
let greeted       = false;
let currentSource = null;

// ── State machine ──────────────────────────────
let ariaState = 'idle'; // idle | listening | thinking | speaking

// ── Nebula renderer ────────────────────────────
const W = canvas.width, H = canvas.height, CX = W/2, CY = H/2;

// Blob nodes that float and merge
const nodes = Array.from({length: 7}, (_, i) => ({
  x: CX + (Math.random()-0.5)*80,
  y: CY + (Math.random()-0.5)*80,
  vx: (Math.random()-0.5)*0.4,
  vy: (Math.random()-0.5)*0.4,
  r: 55 + Math.random()*40,
  phase: Math.random()*Math.PI*2,
}));

// Color palettes per state
const palettes = {
  idle:      [[0,180,255],[80,100,220],[120,60,200]],
  listening: [[0,255,140],[0,200,100],[60,255,180]],
  thinking:  [[255,160,0],[220,80,0],[255,220,60]],
  speaking:  [[200,60,255],[140,0,255],[255,80,220]],
};

let energy    = 0.5;   // 0-1 drives size/brightness
let energyTarget = 0.5;

function lerpColor(a, b, t) {
  return a.map((v,i) => Math.round(v + (b[i]-v)*t));
}

let colorT  = 0;
let lastState = 'idle';

function drawFrame(ts) {
  requestAnimationFrame(drawFrame);

  // Ease energy toward target (slower = smoother)
  energy += (energyTarget - energy) * 0.025;

  // Shift palette when state changes
  if (ariaState !== lastState) { colorT = 0; lastState = ariaState; }
  colorT = Math.min(1, colorT + 0.015);

  const pal    = palettes[ariaState] || palettes.idle;
  const prevPal= palettes[lastState] || palettes.idle;

  ctx2d.clearRect(0, 0, W, H);

  // Move nodes
  nodes.forEach(n => {
    n.phase += 0.008 + energy*0.012;
    // Smooth drift — less randomness, more fluid
    const dx = CX - n.x, dy = CY - n.y;
    n.vx += dx*0.0006 + (Math.random()-0.5)*0.03;
    n.vy += dy*0.0006 + (Math.random()-0.5)*0.03;
    n.vx *= 0.97; n.vy *= 0.97;
    n.x += n.vx; n.y += n.vy;
    // Pulsing radius driven by energy
    n.r = (50 + 8*Math.sin(n.phase*0.7)) * (0.8 + energy*0.8) * (1 + 0.12*Math.sin(n.phase));
  });

  // Compositing: blend blobs together
  ctx2d.save();
  ctx2d.globalCompositeOperation = 'source-over';

  nodes.forEach((n, i) => {
    const col = lerpColor(prevPal[i % prevPal.length], pal[i % pal.length], colorT);
    const alpha = 0.12 + energy * 0.12;
    const grad = ctx2d.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 1.8);
    grad.addColorStop(0,   `rgba(${col},${alpha + 0.15})`);
    grad.addColorStop(0.4, `rgba(${col},${alpha})`);
    grad.addColorStop(1,   `rgba(${col},0)`);
    ctx2d.beginPath();
    ctx2d.arc(n.x, n.y, n.r * 1.8, 0, Math.PI*2);
    ctx2d.fillStyle = grad;
    ctx2d.fill();
  });

  // Bright inner core
  const coreR = 40 + energy * 55;
  const coreCol = lerpColor(prevPal[0], pal[0], colorT);
  const core = ctx2d.createRadialGradient(CX, CY, 0, CX, CY, coreR);
  core.addColorStop(0,   `rgba(${coreCol},${0.55 + energy*0.35})`);
  core.addColorStop(0.5, `rgba(${coreCol},${0.2 + energy*0.2})`);
  core.addColorStop(1,   `rgba(${coreCol},0)`);
  ctx2d.beginPath();
  ctx2d.arc(CX, CY, coreR, 0, Math.PI*2);
  ctx2d.fillStyle = core;
  ctx2d.fill();

  // Outer glow ring
  const glowR = 120 + energy * 80;
  const glow  = ctx2d.createRadialGradient(CX, CY, glowR*0.6, CX, CY, glowR);
  glow.addColorStop(0,   `rgba(${coreCol},0)`);
  glow.addColorStop(0.7, `rgba(${coreCol},${0.04 + energy*0.04})`);
  glow.addColorStop(1,   `rgba(${coreCol},0)`);
  ctx2d.beginPath();
  ctx2d.arc(CX, CY, glowR, 0, Math.PI*2);
  ctx2d.fillStyle = glow;
  ctx2d.fill();

  ctx2d.restore();
}

requestAnimationFrame(drawFrame);

// ── Energy modulation per state ────────────────
function setState(s) {
  ariaState = s;
  const targets = {idle:0.35, listening:0.55, thinking:0.7, speaking:0.95};
  energyTarget  = targets[s] ?? 0.35;
}

// Pulse energy while speaking (driven by simulated loudness)
let speakPulse = null;
let speakPhase = 0;
function startSpeakPulse() {
  if (speakPulse) return;
  speakPulse = setInterval(() => {
    speakPhase += 0.18;
    energyTarget = 0.75 + 0.22 * Math.sin(speakPhase);
  }, 60);
}
function stopSpeakPulse() {
  clearInterval(speakPulse); speakPulse = null; speakPhase = 0;
  energyTarget = 0.35;
}

// ── Audio context ──────────────────────────────
function getAudioContext() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  return audioCtx;
}

function stopAudio() {
  audioQueue = []; isPlaying = false;
  if (currentSource) { try { currentSource.stop(); } catch(e){} currentSource = null; }
  stopSpeakPulse();
  setState('listening');
}

function unlockAndGreet() {
  const c = getAudioContext();
  c.resume().then(() => {
    if (!greeted) {
      greeted = true;
      setState('thinking');
      if (ws && ws.readyState === WebSocket.OPEN)
        ws.send(JSON.stringify({ text: "Aria activate" }));
    }
  });
}

document.addEventListener('click',   unlockAndGreet, { once: true });
document.addEventListener('keydown', unlockAndGreet, { once: true });

// ── WebSocket ──────────────────────────────────
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen  = () => setState('idle');
  ws.onclose = () => setTimeout(connect, 3000);
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'stop') { stopAudio(); return; }
    if (data.type === 'response' && data.audio && data.audio.length > 0) {
      setState('thinking');
      queueAudio(data.audio);
    } else if (data.type === 'response') {
      setState('listening');
    }
  };
}

function queueAudio(b64) {
  audioQueue.push(b64);
  if (!isPlaying) playNext();
}

function playNext() {
  if (audioQueue.length === 0) {
    isPlaying = false;
    stopSpeakPulse();
    setState('listening');
    return;
  }
  isPlaying = true;
  setState('speaking');
  startSpeakPulse();

  const bytes = Uint8Array.from(atob(audioQueue.shift()), c => c.charCodeAt(0)).buffer;
  const c     = getAudioContext();
  c.resume().then(() => {
    c.decodeAudioData(bytes, (buffer) => {
      const src     = c.createBufferSource();
      src.buffer    = buffer;
      src.connect(c.destination);
      currentSource = src;
      src.onended   = () => {
        if (ws && ws.readyState === WebSocket.OPEN)
          ws.send(JSON.stringify({ type: "audio_end" }));
        playNext();
      };
      src.start(0);
    }, () => playNext());
  });
}

connect();
