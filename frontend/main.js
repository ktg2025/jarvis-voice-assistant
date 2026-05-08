// Jarvis V2 — Frontend
const orb = document.getElementById('orb');
const status = document.getElementById('status');

let ws;
let audioQueue = [];
let isPlaying = false;
let audioCtx = null;
let greeted = false;
let currentSource = null;

function stopAudio() {
    audioQueue = [];
    isPlaying = false;
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
            status.textContent = '';
            setOrbState('thinking');
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ text: "Jarvis activate" }));
            }
        }
    });
}

document.addEventListener('click', unlockAndGreet, { once: true });
document.addEventListener('keydown', unlockAndGreet, { once: true });

function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
        console.log('[jarvis] WebSocket connected');
        status.textContent = 'Klicke irgendwo — Jarvis erwacht.';
        setOrbState('idle');
    };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'stop') { stopAudio(); return; }
        if (data.type === 'response') {
            addTranscript('jarvis', data.text);
            if (data.audio && data.audio.length > 0) {
                queueAudio(data.audio);
            } else {
                setOrbState('listening');
            }
        }
    };
    ws.onclose = () => {
        status.textContent = 'Verbindung verloren...';
        setTimeout(connect, 3000);
    };
}

function queueAudio(base64Audio) {
    audioQueue.push(base64Audio);
    if (!isPlaying) playNext();
}

function playNext() {
    if (audioQueue.length === 0) {
        isPlaying = false;
        setOrbState('listening');
        status.textContent = '';
        return;
    }
    isPlaying = true;
    setOrbState('speaking');

    const b64 = audioQueue.shift();
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer;
    const ctx = getAudioContext();

    ctx.resume().then(() => {
        ctx.decodeAudioData(bytes, (buffer) => {
            const source = ctx.createBufferSource();
            source.buffer = buffer;
            source.connect(ctx.destination);
            currentSource = source;
            source.onended = () => {
                if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "audio_end"}));
                playNext();
            };
            source.start(0);
        }, (err) => {
            console.error('[jarvis] decodeAudioData error:', err);
            playNext();
        });
    });
}

const pttBtn = document.getElementById('pttBtn');
pttBtn.addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ ptt: true }));
        pttBtn.textContent = '🔴 Aufnahme...';
        pttBtn.disabled = true;
        setTimeout(() => {
            pttBtn.textContent = '🎤 SPRECHEN';
            pttBtn.disabled = false;
        }, 6000);
    }
});

function setOrbState(state) { orb.className = state; }

function addTranscript(role, text) {
    // transcript display removed
}

connect();
