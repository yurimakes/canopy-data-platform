"""Local HTTP integration server with a durable SQLite worker. Never deploy this file."""
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dotenv import load_dotenv
from trip_routes import dispatch
from services.runtime import service, local_mode


class Handler(BaseHTTPRequestHandler):
    def handle_api(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 16384:
                self.send_error(413)
                return
        except ValueError:
            self.send_error(400)
            return
        status, result = dispatch(self.command, self.path.split("?", 1)[0], self.headers, self.rfile.read(length))
        payload = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_POST = handle_api
    do_GET = handle_api


def main():
    load_dotenv()
    if not local_mode() or os.getenv("TRIP_STORE") != "sqlite":
        raise RuntimeError("local.py requires APP_ENV=development and TRIP_STORE=sqlite")
    api = service()
    stopped = threading.Event()

    def work():
        while not stopped.wait(1):
            try:
                api.process_pending()
            except Exception:
                logging.exception("local_trip_worker_failed")

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    server = ThreadingHTTPServer((os.getenv("API_HOST", "127.0.0.1"), int(os.getenv("API_PORT", "8000"))), Handler)
    print(f"Local Trip API: http://{server.server_address[0]}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        server.server_close()
        thread.join(timeout=10)


if __name__ == "__main__":
    main()
