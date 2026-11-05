// Headless check of the local real-time page for one house: logs in, opens the
// page, waits for a snapshot, and prints the diagram's temperatures, the
// thermostat table and the pump table. Usage: node check.mjs <gnode-alias> <out-dir>
import { chromium } from 'playwright-core';
const [alias, out] = process.argv.slice(2);
const base = 'http://localhost:5173/gridworks-web-frontend';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 1400 } });
page.on('console', (m) => { if (m.type() === 'warning' || m.type() === 'error') console.log('console:', m.type(), m.text().slice(0, 300)); });
await page.goto(`${base}/login/`);
await page.fill('input[type="text"]', process.env.DEVRUN_API_USER);
await page.fill('input[type="password"]', process.env.DEVRUN_API_PASSWORD);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.endsWith('/login/'), { timeout: 20000 });
let snapshot = null;
page.on('websocket', (ws) => ws.on('framereceived', (f) => {
    try { const m = JSON.parse(f.payload); if (m.type === 'mqtt_message' && m.message_type === 'snapshot.spaceheat') snapshot = m.payload; } catch { /* not json */ }
}));
await page.goto(`${base}/real-time/${alias}/`);
await page.waitForSelector('#dashboard-pump-table', { timeout: 90000 });
await page.waitForTimeout(1500);
const texts = await page.$$eval('#dashboard-diagram-svg text', (els) => els.map((e) => e.textContent.trim()).filter((t) => t));
console.log('DIAGRAM_TEXT', JSON.stringify(texts));
for (const id of ['dashboard-thermostat-table', 'dashboard-hp-power-table', 'dashboard-pump-table', 'dashboard-resistive-table']) {
    const rows = await page.$$eval(`#${id} tr`, (trs) => trs.map((tr) => Array.from(tr.querySelectorAll('th,td')).map((c) => c.textContent.trim())));
    console.log('TABLE', id, JSON.stringify(rows));
}
const zone = await page.$$eval('.dashboard-zone-table tr', (trs) => trs.map((tr) => Array.from(tr.querySelectorAll('th,td')).map((c) => c.textContent.trim())));
console.log('TABLE zone', JSON.stringify(zone));
const fs = await import('node:fs');
fs.writeFileSync(`${out}/snapshot-${alias.split('.').pop()}.json`, JSON.stringify(snapshot, null, 1));
console.log('SNAPSHOT_READINGS', snapshot ? snapshot.LatestReadingList.length : 'none');
await page.screenshot({ path: `${out}/realtime-${alias.split('.').pop()}.png`, fullPage: true });
await browser.close();
