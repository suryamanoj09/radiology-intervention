# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React SPA ----------
FROM node:20-slim AS frontend
WORKDIR /app
# Install deps first so this layer caches unless the lockfile changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
# Build the static bundle -> /app/dist
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: FastAPI + baked model + built SPA ----------
FROM python:3.11-slim AS runtime

# libglib2.0-0 is the one native lib opencv-python-headless still needs at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root uid-1000 user (Hugging Face Spaces run the container as uid 1000).
RUN useradd -m -u 1000 user

# HOME-scoped caches so baked weights + any runtime cache live under the
# user-owned home; PORT default 7860; storage under the app dir (user-owned).
ENV HOME=/home/user \
    TORCH_HOME=/home/user/.cache/torch \
    XDG_CACHE_HOME=/home/user/.cache \
    PORT=7860 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STORAGE_DIR=/home/user/app/storage

WORKDIR /home/user/app

# 1) CPU-only torch/torchvision FIRST, from the PyTorch CPU index, so pip never
#    resolves the multi-GB CUDA wheels. Both pins have cp311 linux CPU wheels.
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.2.2 torchvision==0.17.2

# 2) THEN the rest of the backend deps from plain PyPI. requirements.txt no
#    longer lists torch/torchvision, so the CPU wheels installed above are kept.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 3) Backend source.
COPY backend/ ./

# Make the app tree + caches + storage owned by the runtime user.
RUN mkdir -p /home/user/.cache /home/user/app/storage \
    && chown -R user:user /home/user

USER user

# 4) BAKE the pretrained weights into the image at build time so a cold Space
#    does zero downloading on first request. Runs as `user` so the download
#    lands in the user-owned HOME cache that is committed into the image.
#    If the ensemble later adds more weight sets, add one bake line per set.
RUN python -c "import cv2; import numpy as np; import torch; import torchxrayvision as xrv; torch.from_numpy(np.zeros((1,), dtype=np.float32)); xrv.models.DenseNet(weights='densenet121-res224-all'); print('runtime dependencies and weights baked')"

# 5) Built SPA from stage 1 -> ./frontend_dist. main.py mounts this at '/' as
#    the LAST route (config.BASE_DIR/frontend_dist == /home/user/app/frontend_dist).
COPY --chown=user:user --from=frontend /app/dist ./frontend_dist

EXPOSE 7860

# Shell form so ${PORT} (default 7860) is read from the environment at runtime.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
