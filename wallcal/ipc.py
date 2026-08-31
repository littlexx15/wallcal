from __future__ import annotations

import socket
import threading
from collections.abc import Callable

HOST = "127.0.0.1"
PORT = 47231


def ask_running_instance_to_show() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.6) as conn:
            conn.sendall(b"SHOW")
        return True
    except OSError:
        return False


def listen_for_show(on_show: Callable[[], None]) -> None:
    def loop() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, PORT))
            sock.listen(2)
            sock.settimeout(1.0)
        except OSError:
            return
        while True:
            try:
                conn, _ = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                payload = conn.recv(32)
            except OSError:
                payload = b""
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            if payload.startswith(b"SHOW"):
                on_show()

    threading.Thread(target=loop, daemon=True, name="wallcal-ipc").start()
