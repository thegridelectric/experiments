import json, socket, struct, time
from pyModbusTCP.client import ModbusClient
d = json.load(open("/home/pi/.config/gridworks/scada-experiment/hardware-layout.json"))
comp = [c for c in d["Components"] if c.get("DeviceType") == "EgaugePowerMeter"][0]
host = [v for k, v in comp.items() if "host" in k.lower()][0]
c = ModbusClient(host=socket.gethostbyname(host), port=comp.get("ModbusPort", 502), unit_id=1, timeout=5, auto_open=True)
print(time.strftime("%H:%M:%S"), host)
for cfg in comp["ConfigList"]:
    r = cfg["EgaugeRegisterConfig"]
    regs = c.read_input_registers(r["Address"], 2)
    v = struct.unpack(">f", struct.pack(">HH", *regs))[0] if regs else None
    print(cfg["ChannelName"].ljust(24), "n/a" if v is None else str(round(v)).rjust(7))
