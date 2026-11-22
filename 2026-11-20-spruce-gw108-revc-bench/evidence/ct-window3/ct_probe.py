# Which CT sees the secondary pump? Sample each CT fast and report swing.
import statistics, time
import gw108_test_code as g
g.adc_ct.data_rate = 860
g.adc_ct.mode = g.ADS1115.Mode.CONTINUOUS
print("dac3 raw a/b/c/d", [c.raw_value for c in (g.dac3.channel_a, g.dac3.channel_b, g.dac3.channel_c, g.dac3.channel_d)])
print("pump3 relay bit", g.get_tca9555_pin(0x21, 3, 5) if hasattr(g, "get_tca9555_pin") else "?")
for i, ct in enumerate([g.ct1, g.ct2, g.ct3, g.ct4], 1):
    _ = ct.voltage; time.sleep(0.01)
    t0 = time.perf_counter(); v = [ct.voltage for _ in range(600)]; dt = time.perf_counter() - t0
    m = statistics.fmean(v); rms = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
    print(f"ct{i}: n={len(v)} {len(v)/dt:.0f} sps mean={m:.3f} min={min(v):.3f} max={max(v):.3f} p2p={max(v)-min(v):.3f} rms_ac={rms:.4f}")
