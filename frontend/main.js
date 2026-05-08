// Jarvis V2 — Frontend
const orb    = document.getElementById('orb');
const status = document.getElementById('status');

let ws;
let audioQueue    = [];
let isPlaying     = false;
let audioCtx      = null;
let greeted       = false;
let currentSource = null;

function stopAudio() {
    audioQueue = [];
    isPlaying  = false;
    if (currentSource) { try { currentSource.stop(); } catch(e) {} currentSource = null; }
    setOrbState('listening');
}

function getAudioContext() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
}

function unlockAndGreet() {
    const ctx = getAudioContext();
    ctx.resume().then(() => {
        if (!greeted) {
            greeted = true;
            setOrbState('thinking');
            if (ws && ws.readyState === WebSocket.OPEN)
                ws.send(JSON.stringify({ text: "Jarvis activate" }));
        }
    });
}

// Unlock audio + greet on ANY interaction
document.addEventListener('click',   unlockAndGreet, { once: true });
document.addEventListener('keydown', unlockAndGreet, { once: true });

function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
        setOrbState('idle');
        status.textContent = '';
    };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'stop')  { stopAudio(); return; }
        if (data.type === 'response' && data.audio && data.audio.length > 0) {
            queueAudio(data.audio);
        } else if (data.type === 'response') {
            setOrbState('listening');
        }
    };
    ws.onclose = () => setTimeout(connect, 3000);
}

function queueAudio(b64) {
    audioQueue.push(b64);
    if (!isPlaying) playNext();
}

function playNext() {
    if (audioQueue.length === 0) {
        isPlaying = false;
        setOrbState('listening');
        return;
    }
    isPlaying = true;
    setOrbState('speaking');
    const bytes = Uint8Array.from(atob(audioQueue.shift()), c => c.charCodeAt(0)).buffer;
    const ctx   = getAudioContext();
    ctx.resume().then(() => {
        ctx.decodeAudioData(bytes, (buffer) => {
            const src = ctx.createBufferSource();
            src.buffer  = buffer;
            src.connect(ctx.destination);
            currentSource = src;
            src.onended = () => {
                if (ws && ws.readyState === WebSocket.OPEN)
                    ws.send(JSON.stringify({ type: "audio_end" }));
                playNext();
            };
            src.start(0);
        }, () => playNext());
    });
}

function setOrbState(state) { orb.className = state; }

connect();
