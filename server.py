#!/usr/bin/env python3
"""
Servidor TV RARUS com Sincronização em Tempo Real (SSE)
- Serve arquivos estáticos (index.html, fundo.mp4, etc.)
- Sincroniza configurações globalmente em tempo real via Server-Sent Events (SSE)
- Salva o estado em config.json para persistência entre reinicializações
"""

import os
import sys
import re
import json
import time
import socket
import threading
from queue import Queue, Empty
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "audioMode": "stream",
    "streamUrl": "https://streams.ilovemusic.de/iloveradio17.mp3",
    "youtubeId": "5yx6BWlEVcY",
    "title": "🎧 Lofi Chillhop 24/7",
    "volume": 80,
    "isPlaying": True,
    "showClock": True,
    "updatedAt": int(time.time() * 1000),
    "updatedBy": "server"
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(data)
                return merged
        except Exception as e:
            print(f"[Aviso] Erro ao ler {CONFIG_FILE}, usando padrões: {e}", flush=True)
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Erro] Falha ao salvar {CONFIG_FILE}: {e}", flush=True)

global_config = load_config()
config_lock = threading.Lock()

subscribers = set()
subscribers_lock = threading.Lock()

def broadcast_config(cfg):
    payload = json.dumps(cfg, ensure_ascii=False)
    msg = f"data: {payload}\n\n"
    with subscribers_lock:
        dead = []
        for q in subscribers:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            subscribers.discard(q)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

class TVRarusHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        # 1. Endpoint SSE em tempo real: /api/events
        if self.path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            q = Queue(maxsize=100)
            with subscribers_lock:
                subscribers.add(q)

            # Envia estado global atual imediatamente ao conectar
            with config_lock:
                initial_msg = f"data: {json.dumps(global_config, ensure_ascii=False)}\n\n"
            try:
                self.wfile.write(initial_msg.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                with subscribers_lock:
                    subscribers.discard(q)
                return

            try:
                while True:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with subscribers_lock:
                    subscribers.discard(q)
            return

        # 2. Endpoint REST: /api/config
        if self.path == "/api/config":
            with config_lock:
                cfg_copy = dict(global_config)
                cfg_copy["localIp"] = get_local_ip()
                cfg_copy["port"] = self.server.server_address[1]
                data = json.dumps(cfg_copy, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return

        # 3. Suporte a Range Requests (HTTP 206) para streaming perfeito de vídeo (fundo.mp4)
        range_header = self.headers.get("Range")
        path_clean = self.path.split("?")[0].lstrip("/")
        full_path = os.path.join(BASE_DIR, path_clean)

        if range_header and os.path.isfile(full_path):
            try:
                file_size = os.path.getsize(full_path)
                range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if range_match:
                    start = int(range_match.group(1))
                    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                    end = min(end, file_size - 1)
                    if start <= end:
                        content_length = end - start + 1
                        mime_type = self.guess_type(full_path)

                        self.send_response(206, "Partial Content")
                        self.send_header("Content-Type", mime_type)
                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                        self.send_header("Content-Length", str(content_length))
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()

                        with open(full_path, "rb") as f:
                            f.seek(start)
                            remaining = content_length
                            while remaining > 0:
                                chunk = f.read(min(remaining, 65536))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                        return
            except Exception:
                pass

        # 4. Arquivos Estáticos Padrão
        super().do_GET()

    def do_POST(self):
        # Atualização de configuração: /api/config
        if self.path == "/api/config":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                new_data = json.loads(body.decode("utf-8"))
            except Exception:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"JSON invalido"}')
                return

            global global_config
            with config_lock:
                new_data["updatedAt"] = int(time.time() * 1000)
                global_config.update(new_data)
                save_config(global_config)
                current_copy = dict(global_config)

            # Transmite para todas as telas conectadas imediatamente!
            broadcast_config(current_copy)

            resp = json.dumps({"success": True, "config": current_copy}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # Suprime logs de ping para manter o terminal legível
        if args and ("api/events" in args[0] or "ping" in args[0]):
            return
        super().log_message(format, *args)


import socketserver

class FastHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = "0.0.0.0"
        self.server_port = self.server_address[1]

def run_server(port=8080):
    server = None
    for p in range(port, port + 10):
        try:
            server = FastHTTPServer(("0.0.0.0", p), TVRarusHandler)
            port = p
            break
        except OSError:
            continue
    else:
        print("[Erro] Nenhuma porta disponível entre 8080 e 8090.", flush=True)
        sys.exit(1)

    local_ip = get_local_ip()

    print("=" * 64, flush=True)
    print("           🌟 TV RARUS - SERVIDOR CENTRAL ATIVO 🌟           ", flush=True)
    print("=" * 64, flush=True)
    print(f"  📺 No seu PC / Mac:   http://localhost:{port}", flush=True)
    print(f"  📱 Na TV ou Celular:  http://{local_ip}:{port}", flush=True)
    print(f"  📲 Controle Mobile:   http://{local_ip}:{port}/controle.html", flush=True)
    print("=" * 64, flush=True)
    print("  ⚡ Sincronização global ativa:", flush=True)
    print("     Qualquer alteração de vídeo, rádio ou volume feita", flush=True)
    print("     no PC atualiza a TV e outros aparelhos no mesmo instante!", flush=True)
    print("=" * 64, flush=True)
    print("  [Pressione CTRL+C para encerrar]", flush=True)
    print("=" * 64, flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Servidor encerrado]", flush=True)
        server.server_close()

if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
