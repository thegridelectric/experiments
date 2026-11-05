// The visualizer's numbers for the channels the page check names: the bundle
// through the API, converted by the visualizer's own converter, against the
// real-time page's DOM at the captured snapshot time.
import fs from 'node:fs';
import { getValueConverter } from '/Users/jessica/GridWorks/gridworks-web-frontend/src/sema/units';
const [snapPath, outPath, token] = process.argv.slice(2);
const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
const dom = fs.readFileSync(outPath, 'utf8');
const t = snap.SnapshotTimeUnixMs;
const start = new Date(t - 10 * 60_000).toISOString(); const end = new Date(t + 1000).toISOString();
const chans = ['hp-ewt', 'hp-lwt', 'dist-swt', 'tank1-depth1', 'zone1-living-kitchen-temp', 'secondary-flow', 'secondary-pump-pwr'];
const url = `http://localhost:8000/api/v2/installations/hw1.isone.me.versant.keene.elm/synced.readings.bundle?start=${start}&end=${end}&channels=${chans.join(',')}`;
const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
console.log('bundle', res.status, start, end);
const b = await res.json();
console.log('snapshot time', new Date(t).toISOString());
for (const item of b.ChannelReadingsList ?? []) {
    let last: number | null = null; let lastTs = '';
    item.ValueList.forEach((v: number | null, i: number) => { if (v !== null) { last = v; lastTs = b.TimestampList[i]; } });
    if (last === null) { console.log('NONE', item.ChannelName); continue; }
    const shown = getValueConverter(item.Unit, 1)(last);
    const digits = item.ChannelName.endsWith('-pwr') ? 3 : 1;
    const text = shown.toFixed(digits);
    const raw = snap.LatestReadingList.find((r: { ChannelName: string }) => r.ChannelName === item.ChannelName)?.Value;
    const hit = item.ChannelName.endsWith('-pwr') ? dom.includes(`"${(shown * 1000).toFixed(1)}"`) : dom.includes(`"${text}`);
    console.log(`${hit ? 'OK  ' : 'DIFF'} ${item.ChannelName} journal=${last} ${item.Unit} @${lastTs} -> ${text}; snapshot raw=${raw}`);
}
