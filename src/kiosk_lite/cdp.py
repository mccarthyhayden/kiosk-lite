"""Minimal Chromium DevTools client. Speaks HTTP and WebSocket itself.

The debugging port is used only on 127.0.0.1. Callers must not log the
JavaScript they send: a login submission contains the password.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import urllib.request


class CdpError(RuntimeError):
    pass


class Cdp:
    def __init__(self, port: int) -> None:
        self.port = port
        self._sock: socket.socket | None = None
        self._next_id = 0

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def connect_page(self) -> None:
        targets = _http_json(self.port, "/json/list")
        for target in targets:
            if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                self._connect(target["webSocketDebuggerUrl"])
                return
        raise CdpError(f"no page target on port {self.port}")

    def connect_browser(self) -> None:
        version = _http_json(self.port, "/json/version")
        url = version.get("webSocketDebuggerUrl")
        if not url:
            raise CdpError(f"no browser target on port {self.port}")
        self._connect(url)

    def call(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        if self._sock is None:
            raise CdpError("not connected")
        self._next_id += 1
        message_id = self._next_id
        payload = {"id": message_id, "method": method}
        if params:
            payload["params"] = params
        _send_text(self._sock, json.dumps(payload))
        self._sock.settimeout(timeout)
        while True:
            message = json.loads(_recv_text(self._sock))
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise CdpError(message["error"].get("message", "cdp error"))
            return message.get("result") or {}

    def evaluate(self, expression: str, timeout: float = 30):
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=timeout,
        )
        if "exceptionDetails" in result:
            raise CdpError("page evaluation failed")
        inner = result.get("result") or {}
        return inner.get("value")

    def _connect(self, ws_url: str) -> None:
        self.close()
        self._sock = _open_websocket(ws_url, self.port)


def _http_json(port: int, path: str):
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode())


def _open_websocket(ws_url: str, port: int) -> socket.socket:
    if not ws_url.startswith("ws://127.0.0.1:") and not ws_url.startswith("ws://localhost:"):
        raise CdpError("refusing a debugging socket that is not local")
    path = ws_url.split("/", 3)[-1]
    path = "/" + path
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    origin = f"http://127.0.0.1:{port}"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Origin: {origin}\r\n"
        "\r\n"
    )
    sock.sendall(request.encode())
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise CdpError("websocket handshake closed")
        header += chunk
        if len(header) > 8192:
            sock.close()
            raise CdpError("websocket handshake too large")
    status = header.split(b"\r\n", 1)[0]
    if b" 101 " not in status:
        sock.close()
        raise CdpError("websocket upgrade failed")
    return sock


def _send_text(sock: socket.socket, text: str) -> None:
    data = text.encode()
    header = bytearray([0x81])
    length = len(data)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header += length.to_bytes(2, "big")
    else:
        header.append(0x80 | 127)
        header += length.to_bytes(8, "big")
    mask = os.urandom(4)
    header += mask
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
    sock.sendall(header + masked)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise CdpError("websocket closed")
        buf += chunk
    return bytes(buf)


def _recv_text(sock: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        first, second = _recv_exact(sock, 2)
        opcode = first & 0x0F
        masked = second & 0x80
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(_recv_exact(sock, 2), "big")
        elif length == 127:
            length = int.from_bytes(_recv_exact(sock, 8), "big")
        mask = _recv_exact(sock, 4) if masked else b""
        payload = _recv_exact(sock, length) if length else b""
        if mask:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            raise CdpError("websocket closed by peer")
        if opcode == 0x9:
            _send_control(sock, 0x8A, payload)
            continue
        if opcode == 0xA:
            continue
        if opcode in (0x0, 0x1):
            chunks.append(payload)
            if first & 0x80:
                return b"".join(chunks).decode()
            continue
        raise CdpError(f"unsupported websocket opcode {opcode}")


def _send_control(sock: socket.socket, opcode: int, payload: bytes) -> None:
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    frame = bytes([opcode, 0x80 | len(payload)]) + mask + masked
    sock.sendall(frame)
