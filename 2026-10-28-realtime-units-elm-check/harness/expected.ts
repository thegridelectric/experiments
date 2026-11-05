// Expected display strings for the captured snapshot, through the frontend's own modules.
import fs from 'node:fs';
import { displayReadings, formatReading } from '/Users/jessica/GridWorks/gridworks-web-frontend/src/sema/displayReadings';
import { AnyLayoutLite } from '/Users/jessica/GridWorks/gridworks-web-frontend/src/sema/types/AnyLayoutLite';
const [snapPath, layoutPath, outPath] = process.argv.slice(2);
const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
const layout = AnyLayoutLite.parse(JSON.parse(fs.readFileSync(layoutPath, 'utf8')));
const raw: Record<string, number> = Object.fromEntries(snap.LatestReadingList.map((r: { ChannelName: string; Value: number }) => [r.ChannelName, r.Value]));
const shown = displayReadings(layout, raw);
const dom = fs.readFileSync(outPath, 'utf8');
const want: [string, number, string][] = [
    ['hp-ewt', 1, '°F'], ['hp-lwt', 1, '°F'], ['dist-swt', 1, '°F'], ['tank1-depth1', 1, '°F'],
    ['zone1-living-kitchen-temp', 1, '°F'], ['zone1-living-kitchen-set', 1, '°F'],
    ['primary-flow', 1, ''], ['secondary-flow', 1, ''], ['hp-odu-pwr', 2, ''],
];
console.log('snapshot time', new Date(snap.SnapshotTimeUnixMs).toISOString());
for (const [name, digits, suffix] of want) {
    const s = formatReading(shown[name], digits, suffix);
    console.log(`${dom.includes(`"${s}"`) ? 'OK  ' : 'MISS'} ${name} raw=${raw[name]} unit=${shown[name]?.unit} shown=${s}`);
}
const w = shown['secondary-pump-pwr']; console.log('secondary-pump-pwr raw', raw['secondary-pump-pwr'], 'kW', w?.display, 'W shown', dom.includes(`"${Math.max(0,(w?.display??0)*1000).toFixed(1)}"`) ? 'OK' : 'MISS');
const undeclared = Object.entries(shown).filter(([, r]) => r.display === undefined).map(([n, r]) => `${n}(${r.unit ?? 'undeclared'})`);
console.log('no display value:', undeclared.join(' '));
