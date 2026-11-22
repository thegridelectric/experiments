# Secondary pump speed sweep: Dac3 C raw -> ct2 waveform stats. Relay untouched.
import statistics, time
from adafruit_ads1x15.ads1x15 import Mode
import gw108_test_code as g
g.adc_ct.data_rate = 860
g.adc_ct.mode = Mode.CONTINUOUS
RESTORE = 3040
def sample(ct, n=1500, discard=30):
    _ = [ct.voltage for _ in range(discard)]
    t0 = time.perf_counter(); out = []
    while len(out) < n:
        out.append((time.perf_counter() - t0, ct.voltage))
    return out
def stats(s):
    v = [x for _, x in s]; m = statistics.fmean(v)
    rms = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
    return m, min(v), max(v), max(v) - min(v), rms
print("pump3 relay bit", g.get_tca9555_pin(0x21, 3, 5), "dac3 C before", g.dac3.channel_c.raw_value)
print("raw,volts,time,mean,min,max,p2p,rms_ac")
for raw in [1600, 2000, 2400, 3040, 3400, 4095]:
    g.set_pump3_analog(raw); time.sleep(6)
    s = sample(g.ct2)
    with open(f"/tmp/ct2_sweep_{raw}.csv", "w") as f:
        f.write("t_s,volts\n"); f.writelines(f"{t:.6f},{v:.4f}\n" for t, v in s)
    m, lo, hi, p2p, rms = stats(s)
    print(f"{raw},{raw/400:.2f},{time.strftime('%H:%M:%S')},{m:.3f},{lo:.3f},{hi:.3f},{p2p:.3f},{rms:.4f}")
g.set_pump3_analog(RESTORE)
print("dac3 C restored", g.dac3.channel_c.raw_value, "relay bit", g.get_tca9555_pin(0x21, 3, 5))
