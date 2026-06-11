const express  = require('express');
const webpush  = require('web-push');
const fs       = require('fs');
const path     = require('path');
const crypto   = require('crypto');

const app  = express();
const PORT = process.env.PORT || 3000;
const DB   = path.join(__dirname, 'data.json');

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ── Data helpers ────────────────────────────────────────
function db() {
  try { return JSON.parse(fs.readFileSync(DB, 'utf8')); }
  catch { return { reminders: [], subs: [], vapid: null }; }
}
function save(data) {
  fs.writeFileSync(DB, JSON.stringify(data));
}

// ── VAPID keys: auto-generate once, persist to data.json ──
function getVapid() {
  const data = db();
  if (!data.vapid) {
    data.vapid = webpush.generateVAPIDKeys();
    save(data);
    console.log('Generated VAPID keys and saved to data.json');
  }
  return data.vapid;
}

const vapid = getVapid();
const VAPID_PUBLIC  = process.env.VAPID_PUBLIC  || vapid.publicKey;
const VAPID_PRIVATE = process.env.VAPID_PRIVATE || vapid.privateKey;

webpush.setVapidDetails('mailto:notify@app.local', VAPID_PUBLIC, VAPID_PRIVATE);

// ── API ─────────────────────────────────────────────────
app.get('/api/key', (_, res) => res.json({ key: VAPID_PUBLIC }));

app.get('/api/reminders', (_, res) => res.json(db().reminders));

app.post('/api/reminders', (req, res) => {
  const data = db();
  const r = { id: crypto.randomUUID(), ...req.body, fired: false };
  data.reminders.push(r);
  save(data);
  res.json(r);
});

app.put('/api/reminders/:id', (req, res) => {
  const data = db();
  const i = data.reminders.findIndex(r => r.id === req.params.id);
  if (i < 0) return res.status(404).end();
  data.reminders[i] = { ...data.reminders[i], ...req.body, fired: false };
  save(data);
  res.json(data.reminders[i]);
});

app.delete('/api/reminders/:id', (req, res) => {
  const data = db();
  data.reminders = data.reminders.filter(r => r.id !== req.params.id);
  save(data);
  res.json({ ok: true });
});

app.post('/api/subscribe', (req, res) => {
  const data = db();
  const sub  = req.body;
  if (!data.subs.find(s => s.endpoint === sub.endpoint)) {
    data.subs.push(sub);
    save(data);
  }
  res.json({ ok: true });
});

// ── Notification scheduler ──────────────────────────────
function tick() {
  const data = db();
  let changed = false;
  const dead  = new Set();

  data.reminders.forEach(r => {
    if (r.fired) return;
    if (Date.now() < new Date(r.at).getTime()) return;

    r.fired   = true;
    changed   = true;
    const payload = JSON.stringify({ title: 'Notify', body: r.msg, tag: r.id });

    data.subs.forEach(sub => {
      webpush.sendNotification(sub, payload).catch(err => {
        if (err.statusCode === 410 || err.statusCode === 404) dead.add(sub.endpoint);
      });
    });

    if (r.repeat !== 'once') {
      const d = new Date(r.at);
      if (r.repeat === 'daily')   d.setDate(d.getDate() + 1);
      if (r.repeat === 'weekly')  d.setDate(d.getDate() + 7);
      if (r.repeat === 'monthly') d.setMonth(d.getMonth() + 1);
      r.at    = d.toISOString();
      r.fired = false;
    }
  });

  if (dead.size > 0) {
    data.subs = data.subs.filter(s => !dead.has(s.endpoint));
    changed = true;
  }

  if (changed) save(data);
}

setInterval(tick, 30_000); // every 30 seconds
tick();

app.listen(PORT, () => console.log(`Notify running on http://localhost:${PORT}`));
