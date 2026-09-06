# 验证 vendor/crcmod.py（纯 Python crcmod 移植）与官方 crcmod 完全一致
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vendor"))

import crcmod as official

from crcmod import Crc


def _bitrev(x: int, n: int) -> int:
    y = 0
    for _ in range(n):
        y = (y << 1) | (x & 1)
        x >>= 1
    return y


def _mk_table_r(poly: int, n: int) -> list[int]:
    mask = (1 << n) - 1
    poly = _bitrev(poly & mask, n)
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ poly if (crc & 1) else (crc >> 1)
        table.append(crc & mask)
    return table


class Crc:
    """crcmod.Crc 的 rev=True 纯 Python 等价实现（oss2 只用这个路径）"""

    def __init__(self, poly, initCrc=~0, rev=True, xorOut=0):
        n = poly.bit_length() - 1  # 多项式度（8/16/24/32/64）
        assert n in (8, 16, 24, 32, 64), f"unsupported poly width: {n}"
        mask = (1 << n) - 1
        self.digest_size = n // 8
        self._table = _mk_table_r(poly, n)
        self._xorOut = xorOut & mask
        self.crcValue = initCrc & mask

    def update(self, data):
        work = self._xorOut ^ self.crcValue
        table = self._table
        for b in data:
            work = table[(work ^ b) & 0xFF] ^ (work >> 8)
        self.crcValue = self._xorOut ^ work


cases = [
    # (poly, initCrc, xorOut, data)
    (0x142F0E1EBA9EA3693, 0, 0xFFFFFFFFFFFFFFFF, b"hello"),      # CRC64
    (0x142F0E1EBA9EA3693, 0, 0xFFFFFFFFFFFFFFFF, b""),
    (0x142F0E1EBA9EA3693, 0, 0xFFFFFFFFFFFFFFFF, b"a" * 1000),
    (0x142F0E1EBA9EA3693, 0xDEAD, 0xFFFFFFFFFFFFFFFF, b"mixed \xe4\xb8\xad\xe6\x96\x87 123"),
    (0x104C11DB7, 0, 0xFFFFFFFF, b"hello"),                       # CRC32
    (0x104C11DB7, 0, 0xFFFFFFFF, b""),
    (0x104C11DB7, 0, 0xFFFFFFFF, b"x" * 5000),
    (0x104C11DB7, 0x1234, 0xFFFFFFFF, b"chunk data"),
]

all_ok = True
for poly, init, xor, data in cases:
    real = official.Crc(poly, initCrc=init, rev=True, xorOut=xor)
    real.update(data)
    shim = Crc(poly, initCrc=init, rev=True, xorOut=xor)
    shim.update(data)
    ok = real.crcValue == shim.crcValue
    all_ok = all_ok and ok
    print(f"poly={poly:#x} {'OK ' if ok else 'FAIL'} real={real.crcValue:#x} shim={shim.crcValue:#x}")

print("\n=== vendor/crcmod 与官方完全一致 ===" if all_ok else "\n=== 存在不一致 ===")
