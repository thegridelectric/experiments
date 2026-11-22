# Store pump through CT1, single turn: Valve 1 energized, Pump 2 on 20 s, ct1 sampled twice; then released.
import statistics, time
from adafruit_ads1x15.ads1x15 import Mode
import gw108_test_code as g
g.adc_ct.data_rate = 860; g.adc_ct.mode = Mode.CONTINUOUS
def sample(ct, n=1500, discard=30):
    _ = [ct.voltage for _ in range(discard)]
    t0 = time.perf_counter(); out = []
    while len(out) < n: out.append((time.perf_counter() - t0, ct.voltage))
    return out
def row(label, s):
    v = [x for _, x in s]; m = statistics.fmean(v); rms = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
    print(f"{label},{time.strftime('%H:%M:%S')},{m:.3f},{min(v):.3f},{max(v):.3f},{max(v)-min(v):.3f},{rms:.4f}")
    with open(f"/tmp/ct1_store_1turn_{label}.csv", "w") as f:
        f.write("t_s,volts\n"); f.writelines(f"{t:.6f},{v:.4f}\n" for t, v in s)
print("label,time,mean,min,max,p2p,rms_ac")
row("rest", sample(g.ct1))
try:
    g.set_valve_1(1); time.sleep(4); g.set_pump_2(1); time.sleep(8)
    row("run1", sample(g.ct1)); time.sleep(5); row("run2", sample(g.ct1))
finally:
    g.set_pump_2(0); time.sleep(2); g.set_valve_1(0)
    print("released: pump2 bit", g.get_tca9555_pin(0x21, 3, 4), "valve1 bit", g.get_tca9555_pin(0x21, 3, 1))
time.sleep(3); row("after", sample(g.ct1))
