# Store pump through CT1: Valve 1 energized, Pump 2 on, Dac3 B swept, ct1 sampled; then released.
import statistics, time
from adafruit_ads1x15.ads1x15 import Mode
import gw108_test_code as g
g.adc_ct.data_rate = 860; g.adc_ct.mode = Mode.CONTINUOUS
def sample(ct, n=1500, discard=30):
    _ = [ct.voltage for _ in range(discard)]
    t0 = time.perf_counter(); out = []
    while len(out) < n: out.append((time.perf_counter() - t0, ct.voltage))
    return out
def stats(s):
    v = [x for _, x in s]; m = statistics.fmean(v)
    return m, min(v), max(v), max(v) - min(v), (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
def row(label, raw, s):
    m, lo, hi, p2p, rms = stats(s)
    print(f"{label},{raw},{time.strftime('%H:%M:%S')},{m:.3f},{lo:.3f},{hi:.3f},{p2p:.3f},{rms:.4f}")
    with open(f"/tmp/ct1_store_{label}_{raw}.csv", "w") as f:
        f.write("t_s,volts\n"); f.writelines(f"{t:.6f},{v:.4f}\n" for t, v in s)
print("label,dac3B_raw,time,mean,min,max,p2p,rms_ac")
row("rest", g.dac3.channel_b.raw_value, sample(g.ct1))
try:
    g.set_valve_1(1); time.sleep(4); print("valve1 bit", g.get_tca9555_pin(0x21, 3, 1))
    g.set_pump_2(1); print("pump2 bit", g.get_tca9555_pin(0x21, 3, 4))
    for raw in [3040, 1600, 2400, 3400, 4095, 3040]:
        g.set_pump2_analog(raw); time.sleep(7); row("run", raw, sample(g.ct1))
finally:
    g.set_pump_2(0); time.sleep(2); g.set_valve_1(0)
    print("released: pump2 bit", g.get_tca9555_pin(0x21, 3, 4), "valve1 bit", g.get_tca9555_pin(0x21, 3, 1), "dac3 B", g.dac3.channel_b.raw_value)
time.sleep(3); row("after", g.dac3.channel_b.raw_value, sample(g.ct1))
