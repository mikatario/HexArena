# -*- coding: utf-8 -*-
"""通信（ホストPCが部屋を作り、他の人が部屋コードで入る）"""
import json
import os
import queue
import socket
import threading
import urllib.request

PORT = 7777
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _pack(msg):
    return (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


# ---------- 部屋コード（IPアドレスとポートを10文字に変換） ----------
def encode_room(ip, port=PORT):
    a, b, c, d = [int(x) for x in ip.split(".")]
    n = (a << 40) | (b << 32) | (c << 24) | (d << 16) | port
    s = ""
    for _ in range(10):
        s = ALPHABET[n & 31] + s
        n >>= 5
    return s[:5] + "-" + s[5:]


def decode_room(code):
    s = code.upper().replace("-", "").replace(" ", "").strip()
    if len(s) != 10:
        raise ValueError("bad code")
    n = 0
    for ch in s:
        n = n * 32 + ALPHABET.index(ch)
    port = n & 0xFFFF
    ip = ".".join(str((n >> sh) & 255) for sh in (40, 32, 24, 16))
    return ip, port


def parse_address(text):
    """部屋コード or 'IP' or 'IP:ポート' を (host, port) に"""
    text = text.strip()
    if "." in text:
        if ":" in text:
            h, p = text.rsplit(":", 1)
            return h.strip(), int(p)
        return text, PORT
    return decode_room(text)


def local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def public_ip():
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=4) as r:
                ip = r.read().decode().strip()
                socket.inet_aton(ip)
                return ip
        except Exception:
            continue
    return None


# ---------- ホスト側 ----------
class _Conn:
    def __init__(self, sock, cid):
        self.sock = sock
        self.cid = cid
        self.q = queue.Queue()
        self.alive = True


class Server:
    def __init__(self, port=PORT, max_clients=7):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.sock.listen(8)
        self.port = port
        self.max_clients = max_clients
        self.inbox = queue.Queue()
        self.conns = {}
        self.lock = threading.Lock()
        self.next_id = 1
        self.accepting = True
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self.running:
            try:
                s, addr = self.sock.accept()
            except OSError:
                break
            if not self.accepting or len(self.conns) >= self.max_clients:
                try:
                    s.sendall(_pack({"t": "error", "text": "部屋が満員か、すでにゲームが始まっています"}))
                    s.close()
                except OSError:
                    pass
                continue
            try:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            with self.lock:
                cid = self.next_id
                self.next_id += 1
                c = _Conn(s, cid)
                self.conns[cid] = c
            threading.Thread(target=self._reader, args=(c,), daemon=True).start()
            threading.Thread(target=self._writer, args=(c,), daemon=True).start()

    def _reader(self, c):
        buf = b""
        try:
            while True:
                data = c.sock.recv(65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self.inbox.put((c.cid, json.loads(line.decode("utf-8"))))
        except (OSError, ValueError):
            pass
        self._drop(c)

    def _writer(self, c):
        while c.alive:
            data = c.q.get()
            if data is None:
                break
            try:
                c.sock.sendall(data)
            except OSError:
                break
        self._drop(c)

    def _drop(self, c):
        with self.lock:
            if c.cid not in self.conns:
                return
            del self.conns[c.cid]
        c.alive = False
        c.q.put(None)
        try:
            c.sock.close()
        except OSError:
            pass
        self.inbox.put((c.cid, {"t": "_disconnect"}))

    def send(self, cid, msg):
        c = self.conns.get(cid)
        if c is not None and c.alive:
            c.q.put(_pack(msg))

    def broadcast(self, msg):
        data = _pack(msg)
        for c in list(self.conns.values()):
            if c.alive:
                c.q.put(data)

    def kick(self, cid):
        c = self.conns.get(cid)
        if c:
            self._drop(c)

    def close(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass
        for c in list(self.conns.values()):
            self._drop(c)


# ---------- 参加者側 ----------
class Client:
    def __init__(self, host, port, timeout=6.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(None)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.inbox = queue.Queue()
        self.lock = threading.Lock()
        self.alive = True
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        buf = b""
        try:
            while True:
                data = self.sock.recv(262144)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self.inbox.put(json.loads(line.decode("utf-8")))
        except (OSError, ValueError):
            pass
        self.alive = False
        self.inbox.put({"t": "_disconnect"})

    def send(self, msg):
        if not self.alive:
            return
        try:
            with self.lock:
                self.sock.sendall(_pack(msg))
        except OSError:
            self.alive = False

    def close(self):
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass
