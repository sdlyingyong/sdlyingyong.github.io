#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 http 流升级成 https（能升的才升）

Radio Browser 里大量电台登记的是 http:// 地址，但服务器其实同时开着 TLS。
https 页面里浏览器会拦掉 http 流，所以这里先自己探一遍：
同一个 (host, port) 用 TLS 连上去、发同样的 path，能拿到音频或 https 跳转的，
就把 URL 改写成 https。

产出：
  data/meta.json 的 u[] 就地改写，s[] 标记 1
  scripts/.https_probe.json 探测缓存（可断点续跑）

用法：
  python3 fix_streams.py              # 探测 + 改写
  python3 fix_streams.py --dry        # 只探测并打印统计，不改文件
  python3 fix_streams.py --workers 96
"""

import argparse
import json
import os
import socket
import ssl
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
CACHE = os.path.join(HERE, ".https_probe.json")
UA = "Mozilla/5.0 (compatible; RoamRadio/0.2; +https://sdlyingyong.github.io/radio/)"

AUDIO_CT = ("audio/", "application/ogg", "application/octet-stream",
            "video/mp2t", "application/x-mpegurl", "application/vnd.apple.mpegurl",
            "video/mp4", "application/aac", "audio/aac")

lock = threading.Lock()
cache = {}


def key_of(scheme_http_url):
    p = urlsplit(scheme_http_url)
    host = (p.hostname or "").lower()
    port = p.port or 80
    # 80 口的 https 一般在 443
    tls_port = 443 if port == 80 else port
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    return host, port, tls_port, path


def probe(host, tls_port, path, timeout=7.0):
    """返回 (kind, detail)。kind ∈ direct / redir / no"""
    ctx = ssl.create_default_context()
    sock = None
    try:
        sock = socket.create_connection((host, tls_port), timeout=timeout)
        sock = ctx.wrap_socket(sock, server_hostname=host)
        req = ("GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: %s\r\n"
               "Icy-MetaData: 0\r\nAccept: */*\r\nConnection: close\r\n\r\n"
               % (path, host, UA))
        sock.sendall(req.encode("latin-1", "replace"))
        buf = b""
        while len(buf) < 2048:
            chunk = sock.recv(2048)
            if not chunk:
                break
            buf += chunk
            if b"\r\n\r\n" in buf:
                break
        head = buf.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace")
        lines = head.split("\r\n")
        first = lines[0] if lines else ""
        # "HTTP/1.0 200 OK" 或 "ICY 200 OK"
        parts = first.split()
        status = 0
        for tok in parts:
            if tok.isdigit() and len(tok) == 3:
                status = int(tok)
                break
        hdrs = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                hdrs[k.strip().lower()] = v.strip()
        ct = hdrs.get("content-type", "").lower()
        loc = hdrs.get("location", "")
        if 300 <= status < 400 and loc.lower().startswith("https://"):
            return "redir", status
        if 200 <= status < 300 and ct.startswith(AUDIO_CT):
            return "direct", ct
        if 200 <= status < 300 and buf.split(b"\r\n\r\n", 1)[-1][:1]:
            # 没给 content-type 但确实在吐字节，多半也是流
            if not ct or ct.startswith("text/"):
                return ("no", ct or "empty-ct") if ct.startswith("text/") else ("direct", "bytes")
            return "direct", ct
        return "no", "%s %s" % (status, ct or "-")
    except ssl.SSLError as e:
        return "no", "tls:" + type(e).__name__
    except (socket.timeout, TimeoutError):
        return "no", "timeout"
    except OSError as e:
        return "no", "net:" + str(e.errno)
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def load_cache():
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache():
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--workers", type=int, default=72)
    args = ap.parse_args()

    meta_path = os.path.join(DATA, "meta.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    urls = meta["u"]
    flags = meta.get("s") or [0] * len(urls)

    todo = {}
    for u in urls:
        if u.startswith("http://"):
            host, port, tls_port, path = key_of(u)
            if not host:
                continue
            k = "%s:%d" % (host, tls_port)
            if k not in todo:
                todo[k] = (host, tls_port, path)

    global cache
    cache = load_cache()
    need = {k: v for k, v in todo.items() if k not in cache}
    print("http 流主机 %d 个，已缓存 %d，待探 %d"
          % (len(todo), len(todo) - len(need), len(need)), file=sys.stderr)

    done = [0]
    total = len(need)

    def work(item):
        k, (host, tls_port, path) = item
        kind, detail = probe(host, tls_port, path)
        with lock:
            cache[k] = [kind, detail]
            done[0] += 1
            if done[0] % 200 == 0 or done[0] == total:
                print("  %d/%d …" % (done[0], total), file=sys.stderr)
                save_cache()

    if need:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(work, list(need.items())))
        save_cache()

    # ---- 统计 + 改写 ----
    upgraded = 0
    score = {"direct": 0, "redir": 0, "no": 0}
    new_urls = list(urls)
    new_flags = list(flags)
    for i, u in enumerate(urls):
        if not u.startswith("http://"):
            continue
        host, port, tls_port, path = key_of(u)
        k = "%s:%d" % (host, tls_port)
        kind = cache.get(k, ["no", ""])[0]
        score[kind] = score.get(kind, 0) + 1
        if kind in ("direct", "redir"):
            nu = "https://" + (host if tls_port == 443 else "%s:%d" % (host, tls_port)) + path
            new_urls[i] = nu
            new_flags[i] = 1
            upgraded += 1

    print("可升级 %d 台（direct %d · redirect %d · 不可用 %d）"
          % (upgraded, score.get("direct", 0), score.get("redir", 0), score.get("no", 0)),
          file=sys.stderr)

    if args.dry:
        return

    meta["u"] = new_urls
    meta["s"] = new_flags
    tmp = meta_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, meta_path)

    https_n = sum(1 for u in new_urls if u.startswith("https://"))
    print("写出 %s：https %d / %d（%.1f%%）"
          % (meta_path, https_n, len(new_urls), 100.0 * https_n / len(new_urls)),
          file=sys.stderr)


if __name__ == "__main__":
    main()
