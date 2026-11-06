# reelforge API image for a Linux GPU host (NVIDIA driver + nvidia-container-toolkit on the host).
# NOTE: written for deployment but NOT built or tested in the development environment (Windows, no Docker).
# Build:  docker build -f deploy/Dockerfile -t reelforge .
# Run:    docker run --gpus all -p 8088:8088 -e REELFORGE_API_KEY=... -v reelforge-jobs:/app/jobs -v hf-cache:/root/.cache reelforge
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 HF_HUB_DISABLE_SYMLINKS_WARNING=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv ffmpeg curl ca-certificates gnupg \
      libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
      libxfixes3 libxrandr2 libgbm1 libasound2t64 libpango-1.0-0 libcairo2 fonts-liberation \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir \
      torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128 \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt -c constraints.txt
ENV PATH=/venv/bin:$PATH

COPY . .
# warm the HyperFrames CLI + its headless Chrome so the first job does not download them
RUN npx --yes hyperframes --version && python -m reelforge doctor || true

EXPOSE 8088
HEALTHCHECK --interval=60s --timeout=10s CMD curl -fs http://127.0.0.1:8088/v1/health || exit 1
CMD ["python", "-m", "reelforge", "serve", "--host", "0.0.0.0", "--port", "8088"]
