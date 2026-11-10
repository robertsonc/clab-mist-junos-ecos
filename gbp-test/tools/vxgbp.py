"""Parse concatenated pcap streams; print VXLAN flags / GBP id / VNI / inner IPs."""
import struct, sys, socket
data = open(sys.argv[1], "rb").read(); i = 0; n = 0
while i < len(data):
    if data[i:i+4] in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        i += 24; continue
    ts, tu, cap, orig = struct.unpack("<IIII", data[i:i+16]); p = data[i+16:i+16+cap]; i += 16 + cap
    if len(p) < 50 or p[12:14] != b"\x08\x00": continue
    ihl = (p[14] & 0xf) * 4; o = 14 + ihl
    outer = socket.inet_ntoa(p[26:30]) + ">" + socket.inet_ntoa(p[30:34])
    vx = p[o+8:o+16]; flags = vx[0]; gpid = struct.unpack(">H", vx[2:4])[0]; vni = int.from_bytes(vx[4:7], "big")
    inn = p[o+16:]
    if inn[12:14] == b"\x08\x00":
        src, dst = socket.inet_ntoa(inn[26:30]), socket.inet_ntoa(inn[30:34])
    else: src = dst = "non-ip"
    print("%s vni=%d flags=0x%02x G=%d gpid=%d inner %s>%s" % (outer, vni, flags, flags >> 7, gpid, src, dst)); n += 1
print(n, "packets")
