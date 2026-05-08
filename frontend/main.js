// Jarvis V2 — Frontend
const orb = document.getElementById('orb');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');

let ws;
let audioQueue = [];
let isPlaying = false;
let audioCtx = null;
let greeted = false;

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
            source.onended = playNext;
            source.start(0);
        }, (err) => {
            console.error('[jarvis] decodeAudioData error:', err);
            playNext();
        });
    });
}

function setOrbState(state) { orb.className = state; }

function addTranscript(role, text) {
    const div = document.createElement('div');
    div.className = role;
    div.textContent = role === 'user' ? `Du: ${text}` : `Jarvis: ${text}`;
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
}

connect();
