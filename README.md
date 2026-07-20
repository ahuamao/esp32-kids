# ESP32 Kids — 用 AI 编程，蓝牙控制开发板

教孩子用 AI 生成 Python，通过 **iPad 蓝牙**推到 **YD-ESP32 (WROOM-32)** 上运行。

## 它是怎么工作的

```
孩子说需求 → AI 生成 Python → iPad 网页通过 BLE 把代码文本推给板子
                                        ↓
                     板子执行 → print 输出/报错 通过 BLE 回传 → 网页显示
```

板子跑 **MicroPython**，常驻一个蓝牙代理（Nordic UART Service）。代码是纯文本、几 KB，
蓝牙秒传，改一行立刻看到结果——**不需要每次重新编译烧固件**。

## 目录

| 路径 | 说明 |
|---|---|
| `firmware/main.py` | 板载 BLE 代理（一次性烧录到板子上，之后常驻） |
| `web/index.html` | iPad 端网页控制台（在 Bluefy 浏览器里打开） |

---

## Phase 0 — 一次性烧录（每块板子做一次，用数据线）

> ⚠️ ESP32 无法裸机蓝牙冷烧录，第一次必须用 USB。之后就永远走蓝牙了。

### 1. 装工具（Mac）

```bash
pip3 install esptool mpremote
```

YD-ESP32 的 USB 串口芯片一般是 **CP2102** 或 **CH340**，Mac 上可能要先装驱动。
插上板子后确认端口：

```bash
ls /dev/tty.*        # 找 /dev/tty.usbserial-xxxx 或 /dev/tty.wchusbserial-xxxx
```

下面把这个端口记作 `PORT`。

### 2. 烧 MicroPython 固件

> 本板实测是 **ESP32-S3**：用 `--chip esp32s3`、`ESP32_GENERIC_S3` 固件，flash 偏移是 **0**（经典 ESP32 才是 0x1000）。

从 <https://micropython.org/download/ESP32_GENERIC_S3/> 下载最新 `ESP32_GENERIC_S3-*.bin`，然后：

```bash
esptool.py --chip esp32s3 --port PORT erase_flash
esptool.py --chip esp32s3 --port PORT --baud 460800 write_flash -z 0 ESP32_GENERIC_S3-xxxxxxxx.bin
```

### 3. 上传板载代理并重启

```bash
mpremote connect PORT fs cp firmware/main.py :main.py
mpremote connect PORT reset
```

看到串口打印 `BLE agent 已启动，广播名： ESP32-Kids` 就成功了。这块板子从此可被蓝牙发现。

---

## Phase 1 — 在 iPad 上测试蓝牙闭环

1. iPad 上安装 **Bluefy – Web BLE Browser**（App Store，免费；iOS Safari 不支持 Web Bluetooth，靠它补上）。
2. 在 Bluefy 地址栏打开永久地址（`web/` 目录经 GitHub Actions 自动部署到 Pages）：

   **<https://ahuamao.github.io/esp32-kids/>**

   > 改了 `web/` 里的东西后 `git push`，Pages 自动重新部署，iPad 刷新即用。
3. 在 Bluefy 里打开该页 → 点 **连接板子** → 选 `ESP32-Kids` → 点 **▶ 运行**。
4. 应看到板子回传：
   ```
   hello from ESP32 👋
   count 0
   count 1
   count 2
   — 运行结束 —
   ```

成功后就证明了最难的一环（BLE 通路 + 代码传输 + 输出回传）。

---

## 传输协议（Phase 1 版）

- 网页 → 板：UTF-8 代码文本，末尾加一个 `\x04` (EOT) 表示"发完，执行"。>180 字节自动分片。
- 板 → 网页：`print` 输出与异常 traceback 通过 notify 回传；每轮结束再发一个 `\x04`。

## 路线图

- [x] **Phase 1** — BLE 通路 hello-world（当前）
- [ ] **Phase 2** — 稳健传输协议：分片/ACK、推整个文件、停止运行、断点续传
- [ ] **Phase 3** — 网页里接入 AI 对话生成 MicroPython 代码
- [ ] **Phase 4** — 课堂化：多板扫描选择、示例库、防死循环等安全护栏
