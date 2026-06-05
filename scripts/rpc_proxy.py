#!/usr/bin/env python3
"""Simple HTTP proxy for JSON-RPC POST forwarding to a configured PRIMARY_RPC.
Usage: PRIMARY_RPC=https://... python3 scripts/rpc_proxy.py
Listens on 127.0.0.1:8545
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
import logging

PRIMARY = os.environ.get("PRIMARY_RPC")
if not PRIMARY:
    print("Set PRIMARY_RPC environment variable to the target RPC URL", file=sys.stderr)
    sys.exit(2)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            logging.info("Forwarding request to %s", PRIMARY)
            resp = requests.post(PRIMARY, data=body, headers={'Content-Type': 'application/json'}, timeout=30)
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() == 'transfer-encoding':
                    continue
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            logging.exception("Proxy forward failed: %s", e)
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        logging.debug(format % args)

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 8545), Handler)
    logging.info('Starting RPC proxy on http://127.0.0.1:8545 forwarding to %s', PRIMARY)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info('Proxy stopping')
    finally:
        server.server_close()
