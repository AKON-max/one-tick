# ============================================================
# 纯 Python crcmod 替代实现（vendor 目录，仅容器内使用）
#
# 背景：oss2 依赖 crcmod（纯 C 扩展，无 cp312 预编译轮子），
#       在精简容器里编译需要 gcc（国内网络下 apt 极易卡死）。
#       crcmod 运行时本身支持纯 Python 回退，这里按 crcmod/crcmod.py
#       的 rev=True 表驱动算法完整移植（oss2 只用这个路径）。
#
# 使用方式：容器内通过 PYTHONPATH=/app/vendor 让 `import crcmod`
#       命中本文件；宿主机（Windows，自带编译器）仍用 PyPI 真包。
# 正确性：scripts/test_crcmod_shim.py 与官方 crcmod 逐字节对拍通过。
# ============================================================

__all__ = "mkCrcFun Crc".split()


def _bitrev(x: int, n: int) -> int:
    """按位反转（对应 crcmod 的 _bitrev）"""
    y = 0
    for _ in range(n):
        y = (y << 1) | (x & 1)
        x >>= 1
    return y


def _mk_table_r(poly: int, n: int) -> list[int]:
    """bit-reversed 查找表（对应 crcmod 的 _mkTable_r + _bytecrc_r）"""
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
    """crcmod.Crc 的纯 Python 等价实现（支持 oss2 用到的 rev=True 反射算法）"""

    def __init__(self, poly, initCrc=~0, rev=True, xorOut=0):
        n = poly.bit_length() - 1  # 多项式度：8/16/24/32/64
        if n not in (8, 16, 24, 32, 64):
            raise ValueError("The degree of the polynomial must be 8, 16, 24, 32 or 64")
        if not rev:
            raise NotImplementedError("仅实现 rev=True（oss2 只用到反射算法）")
        mask = (1 << n) - 1
        self.digest_size = n // 8
        self.poly = poly
        self.reverse = True
        self.table = _mk_table_r(poly, n)
        self.initCrc = initCrc & mask
        self.xorOut = xorOut & mask
        self.crcValue = self.initCrc

    def new(self, arg=None):
        n = Crc.__new__(Crc)
        n.digest_size = self.digest_size
        n.poly = self.poly
        n.reverse = self.reverse
        n.table = self.table
        n.initCrc = self.initCrc
        n.xorOut = self.xorOut
        n.crcValue = self.initCrc
        if arg is not None:
            n.update(arg)
        return n

    def copy(self):
        c = self.new()
        c.crcValue = self.crcValue
        return c

    def update(self, data):
        # 对应 crcmod 的 crcfun：初值/终值都 XOR xorOut，中间走表驱动
        work = self.xorOut ^ self.crcValue
        table = self.table
        for b in data:
            work = table[(work ^ b) & 0xFF] ^ (work >> 8)
        self.crcValue = self.xorOut ^ work

    def digest(self):
        n = self.digest_size
        crc = self.crcValue
        lst = []
        while n > 0:
            lst.append(crc & 0xFF)
            crc >>= 8
            n -= 1
        lst.reverse()
        return bytes(lst)

    def hexdigest(self):
        return self.digest().hex().upper()


def mkCrcFun(poly, initCrc=~0, rev=True, xorOut=0):
    """crcmod.mkCrcFun 的纯 Python 等价：返回 crcfun(data, crc=initCrc)"""
    n = poly.bit_length() - 1
    mask = (1 << n) - 1
    init = initCrc & mask
    xout = xorOut & mask
    table = _mk_table_r(poly, n)

    def crcfun(data, crc=init):
        work = xout ^ crc
        for b in data:
            work = table[(work ^ b) & 0xFF] ^ (work >> 8)
        return xout ^ work

    return crcfun
