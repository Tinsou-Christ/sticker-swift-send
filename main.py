import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import bot


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, format, *args):
        # evite de polluer les logs avec chaque requete de health check
        pass


def run_health_check_server():
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()


if __name__ == '__main__':
    # lance le serveur HTTP en arriere-plan pour satisfaire le health check de Render
    threading.Thread(target=run_health_check_server, daemon=True).start()

    # lance le bot (bloquant) dans le thread principal
    bot.main()
