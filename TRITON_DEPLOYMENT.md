# Triton Cluster Deployment

This document shows how to start the Noted frontend on a CPU node and the backend on a GPU node on Aalto Triton using the user account `jains6@trition.aalto.fi`.

## Assumptions

- The cluster uses SLURM (`salloc`, `srun`, `sbatch`).
- You can SSH to the login/gateway host at `jains6@trition.aalto.fi`.
- The CPU node and GPU node can communicate internally on the cluster network.
- You have a working repo copy on the Triton filesystem.

## 1. Build and deploy the frontend on a CPU node

### Allocate a CPU node

```bash
ssh jains6@trition.aalto.fi
salloc --partition=cpu --ntasks=1 --cpus-per-task=4 --mem=8G --time=08:00:00
```

If the cluster partition name is different, replace `cpu` with the correct CPU partition name.

### On the allocated CPU node

```bash
cd /path/to/noted-main/noted-frontend
npm install
VITE_API_BASE_URL=http://dgx16:8000/api \
VITE_WS_BASE_URL=ws://dgx16:8000/ws \
npm run build
```

### Serve the built frontend

```bash
cd dist
python3 -m http.server 3000
```

This exposes the frontend on the CPU node at:

- `http://<cpu-node-host>:3000`

## 2. Start the backend on a GPU node

### Allocate a GPU node

```bash
ssh jains6@trition.aalto.fi
salloc --partition=gpu --ntasks=1 --cpus-per-task=8 --gres=gpu:1 --mem=32G --time=08:00:00
```

If your cluster uses a different GPU partition name, replace `gpu` accordingly.

### On the allocated GPU node

```bash
cd /path/to/noted-main/noted-backend
pip install -r requirements.txt
```

Set runtime environment variables and start the backend:

```bash
export CORS_ORIGINS="http://<cpu-node-host>:3000"
export DATABASE_URL=sqlite+aiosqlite:///./noted.db
export HF_TOKEN=<your_hf_token>
export LLAMA_BASE_URL=http://<model-host>:8000/v1
export LLAMA_EMBED_URL=http://<model-host>:8000/v1
export LLAMA_API_KEY=ollama
export SUMMARY_MODEL=gemma2:2b
export ASR_BATCH_URL=http://disabled:8000
export ASR_BATCH_MODEL=none
export DIARIZATION_URL=http://disabled:8010
export DIARIZATION_MODEL=none

python3 main.py
```

The backend will be available on the GPU node at:

- `http://<gpu-node-host>:8000`
- REST API: `http://<gpu-node-host>:8000/api/v1`
- WebSocket base: `ws://<gpu-node-host>:8000/ws`

## 3. Access from your local PC via SSH port forwarding

If the cluster compute nodes are not directly reachable from your laptop, use SSH tunnels to forward ports.

### Example tunnel command

```bash
ssh -L 8080:<cpu-node-host>:3000 \
    -L 8000:<gpu-node-host>:8000 \
    jains6@trition.aalto.fi
```

Then open these URLs on your local PC:

- Frontend: `http://localhost:8080`
- Backend API: `http://localhost:8000/api/v1`
- Backend WebSocket base: `ws://localhost:8000/ws`

## 4. If you want the frontend to call the backend through local tunnels

If you also want the built frontend to use the local tunnel for backend calls, build it with:

```bash
VITE_API_BASE_URL=http://localhost:8000/api \
VITE_WS_BASE_URL=ws://localhost:8000/ws \
npm run build
```

Then serve it on the CPU node as before.

## 5. Example accessible URLs from anywhere with SSH access

Once the SSH tunnel is open from any machine with access to `jains6@trition.aalto.fi`, the service URLs are:

- `http://localhost:8080` → frontend UI
- `http://localhost:8000/api/v1` → backend API
- `ws://localhost:8000/ws` → backend WebSocket

## Notes

- Replace `<cpu-node-host>` and `<gpu-node-host>` with the actual compute node hostnames assigned by Triton.
- If you want HTTPS/WSS, use a TLS-capable reverse proxy on the cluster or a secure forwarding service.
- If `salloc` is not available, use your cluster's alternative allocation command.
