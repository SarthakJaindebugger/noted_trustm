FROM vllm/vllm-openai:nightly

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    librosa \
    soundfile \
    soxr \
    transformers
