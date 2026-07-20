# main.py — ESP32 Kids 板载 BLE 代理 (Phase 1)
#
# 作用：开机自启，开一个 Nordic UART Service (NUS)。
#   - 网页把 Python 代码文本写进来，以 \x04 (EOT) 结尾表示"发完了，开始执行"
#   - 板子执行代码，把 print 输出和异常 traceback 通过 BLE 回传网页
#   - 每轮执行完再回传一个 \x04，网页据此知道"这轮跑完了"
#
# 设计要点：
#   - 只用 MicroPython 内置的 bluetooth 模块，零外部依赖（不需要装 aioble）
#   - 代码在主循环里执行，不在 BLE 中断回调里执行——否则长循环会卡死蓝牙栈

import bluetooth
import io
import sys
import time
from micropython import const

# ---- BLE 中断事件 ----
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

# ---- 特征 flag ----
_FLAG_WRITE = const(0x0008)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_NOTIFY = const(0x0010)

# ---- Nordic UART Service UUID（业界通用，网页/App 都认）----
_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_TX = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_NOTIFY)          # 板 -> 网页
_RX = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"),
       _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)                                          # 网页 -> 板
_UART_SERVICE = (_UART_UUID, (_TX, _RX))

_NAME = "ESP32-Kids"       # 网页按这个名字扫描
_EOT = const(0x04)         # "代码结束/输出结束" 标记
_CHUNK = const(180)        # 每次 notify 的字节数；iOS 协商后 MTU≈185，若某设备更小就调低


def _adv_payload(name):
    """拼一个最小广播包：flags + 完整设备名。"""
    p = bytearray()
    p += bytes((2, 0x01, 0x06))               # flags: 通用可发现
    nb = name.encode()
    p += bytes((len(nb) + 1, 0x09)) + nb      # 0x09 = complete local name
    return p


class BLEAgent:
    def __init__(self):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((_UART_SERVICE,))
        self._ble.gatts_set_buffer(self._rx_handle, 256)   # RX 缓冲，够放一次写入
        self._conn = None
        self._rx_buf = bytearray()   # 累积收到的代码
        self._pending = None         # 收齐一段待执行的代码
        self._payload = _adv_payload(_NAME)
        self._advertise()

    def _advertise(self):
        self._ble.gap_advertise(100_000, adv_data=self._payload)   # 100ms 广播间隔

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._conn = conn_handle
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn = None
            self._rx_buf = bytearray()
            self._advertise()                 # 断开后重新可被发现
        elif event == _IRQ_GATTS_WRITE:
            _, attr_handle = data
            if attr_handle == self._rx_handle:
                self._on_rx(self._ble.gatts_read(self._rx_handle))

    def _on_rx(self, chunk):
        # 只在中断里做最轻的事：攒字节，收到 EOT 就把整段交给主循环去执行
        for b in chunk:
            if b == _EOT:
                self._pending = bytes(self._rx_buf)
                self._rx_buf = bytearray()
            else:
                self._rx_buf.append(b)

    def send(self, s):
        if self._conn is None:
            return
        data = s.encode() if isinstance(s, str) else s
        mv = memoryview(data)
        i = 0
        while i < len(mv):
            try:
                self._ble.gatts_notify(self._conn, self._tx_handle, mv[i:i + _CHUNK])
            except OSError:
                return   # 连接可能刚断开
            i += _CHUNK

    def run(self, code):
        # 自定义 print：输出走 BLE，不动全局 stdout，也就不影响 USB REPL 调试
        def _print(*args, sep=" ", end="\n"):
            self.send(sep.join(str(a) for a in args) + end)

        ns = {"print": _print, "__name__": "__main__"}
        try:
            exec(code, ns)
        except Exception as e:
            buf = io.StringIO()
            sys.print_exception(e, buf)
            self.send(buf.getvalue())
        self.send(chr(_EOT))    # 结束标记

    def poll(self):
        if self._pending is not None:
            code = self._pending
            self._pending = None
            self.run(code)


agent = BLEAgent()
print("BLE agent 已启动，广播名：", _NAME)   # 这条走 USB REPL，方便烧录时确认

while True:
    agent.poll()
    time.sleep_ms(20)
