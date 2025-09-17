# Ship Proxy System

Cost-efficient HTTP/HTTPS proxy architecture for cruise ships. All on-board traffic is funneled through **one persistent TCP connection** to an offshore forward-proxy, cutting satellite charges that are billed per connection.

---

## ⚙️ Architecture

```
Browser / cURL ──▶ Ship Proxy (8080) ── single TCP ──▶ Offshore Proxy (9999) ──▶ Internet
```
* **Ship Proxy (client)** – Runs on the ship, listens on **port 8080**, queues requests, sends one-by-one over the single TCP link.
* **Offshore Proxy (server)** – Runs in the cloud or on shore, receives framed requests, performs real HTTP(S) fetch, returns responses.

Key points
- **Single TCP connection** ⇒ one satellite session ⇒ reduced cost
- **Sequential processing** (FIFO queue) ⇒ stable on high-latency links
- Supports **all HTTP verbs** (GET/POST/PUT/DELETE/…)
- **HTTPS** handled via the CONNECT method
- Packaged as two tiny Docker images (\<60 MB each)

---

##  Repo Layout

```
ship-proxy-system/
│  Dockerfile.offshore  
│  Dockerfile.ship      
│  docker-compose.yml    
│  offshore_proxy.py     # server code
│  ship_proxy.py         # client code
└─ README.md             
```

---

## 🚀 Quick Start (local dev)

```bash
# clone & enter
 git clone https://github.com/SairamBojedla/ship-proxy-system.git
 cd ship-proxy-system


 docker compose build   # or: docker build -t ship-proxy-offshore -f Dockerfile.offshore .


 docker compose up -d   # launches offshore+ship containers


 curl -x http://localhost:8080 http://httpforever.com/
```

---

##  Run Directly From Docker Hub

```bash
# 1 – start offshore 
docker run -d --restart unless-stopped \
  --name offshore-proxy \
  -p 9999:9999 \
  sairam2/offshore-proxy:latest

# 2 – start ship proxy
docker run -d --restart unless-stopped \
  --name ship-proxy \
  -p 8080:8080 \
  --add-host=offshore:$(HOST_IP) \  # optional DNS shortcut
  sairam2/ship-proxy:latest \
  python -u ship_proxy.py --offshore-host <OFFSHORE_IP> --offshore-port 9999
```

> Replace `<OFFSHORE_IP>` with the public IP/DNS of your offshore host.

## Common Ops

```bash

docker compose down


docker compose up -d --build


docker compose logs -f
```

---

## ✨ Implementation Notes

* Custom **5-byte frame** (4-byte length + 1-byte type) lets many messages travel over one TCP stream.
* Ship proxy uses `queue.Queue()` + single worker thread for strict ordering.
* Both containers run as non-root users; healthchecks verify ports 8080/9999.
* No external Python deps → pure stdlib → minimal images.

---

