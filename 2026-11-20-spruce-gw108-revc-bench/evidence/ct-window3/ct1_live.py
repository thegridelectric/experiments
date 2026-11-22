# ct1 under a live scada: mux channel 4, ADS1115 at 0x48, P0 only. Nothing else touched.
import statistics, time
import adafruit_ads1x15.ads1115 as ADS1115
import adafruit_tca9548a, board
from adafruit_ads1x15.ads1x15 import Mode
from adafruit_ads1x15.analog_in import AnalogIn
i2c = board.I2C(); tca = adafruit_tca9548a.TCA9548A(i2c)
adc = ADS1115.ADS1115(tca[4], address=0x48); adc.data_rate = 860; adc.mode = Mode.CONTINUOUS
ct1 = AnalogIn(adc, ADS1115.P0)
_ = [ct1.voltage for _ in range(30)]
t0 = time.perf_counter(); s = []
while len(s) < 1500: s.append((time.perf_counter() - t0, ct1.voltage))
v = [x for _, x in s]; m = statistics.fmean(v); rms = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
print(f"{time.strftime('%H:%M:%S')} ct1 mean={m:.3f} min={min(v):.3f} max={max(v):.3f} p2p={max(v)-min(v):.3f} rms_ac={rms:.4f}")
with open("/tmp/ct1_live.csv", "w") as f:
    f.write("t_s,volts\n"); f.writelines(f"{t:.6f},{x:.4f}\n" for t, x in s)
