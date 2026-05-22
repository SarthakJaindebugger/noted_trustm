#!/bin/bash

set -eu

usage() {
  cat << EOF
Usage: $0 [OPTIONS]
Run llama-server with CUDA support and dynamic model downloading

Options:
  --model-url URL         Download model from URL and use it
  --model-path PATH       Use existing model file at PATH
  --skip-checksum         Skip SHA256 verification (use with caution)
  --gpu-layers N          Number of layers to offload to GPU (default: -1 for auto)
  --context-size N        Context size (default: 2048)
  --batch-size N          Batch size (default: 512)
  --help                  Show this help message

Environment Variables:
  LLAMA_ARG_HOST         Server host (default: 0.0.0.0)
  LLAMA_ARG_PORT         Server port (default: 8003)
  LLAMA_ARG_N_GPU_LAYERS GPU layers to offload (default: -1)

Examples:
  $0 --model-url https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf
  $0 --model-path /home/llama/models/my-model.gguf --gpu-layers 35
  $0 --model-url https://example.com/model.gguf --skip-checksum --context-size 4096

EOF
}

download_and_verify_model() {
  local model_url="$1"
  local skip_checksum="$2"
  local model_name=$(basename "$model_url")
  local model_path="/home/llama/models/$model_name"
  
  echo "Downloading model from: $model_url"
  echo "Model filename: $model_name"
  echo "Saving to: $model_path"
  
  # Check if model already exists
  if [ -f "$model_path" ]; then
    echo "Model already exists at $model_path, skipping download"
    export LLAMA_ARG_MODEL="$model_path"
    return 0
  fi
  
  # Download the model to models directory
  cd /home/llama/models
  if ! curl -LO "$model_url"; then
    echo "Error: Failed to download model from $model_url" >&2
    exit 1
  fi
  
  # Optional: Download and verify checksum if available
  if [ "$skip_checksum" = "false" ]; then
    echo "Checking for available checksums..."
    # Try to download SHA256SUMS file from the same directory
    model_dir=$(dirname "$model_url")
    if curl -s -f "${model_dir}/SHA256SUMS" -o SHA256SUMS 2>/dev/null; then
      if grep -q "$model_name" SHA256SUMS; then
        echo "Found checksum file, verifying..."
        if sha256sum -c SHA256SUMS --ignore-missing; then
          echo "Checksum verification passed"
        else
          echo "Warning: Checksum verification failed" >&2
        fi
      else
        echo "Model not found in checksum file, skipping verification"
      fi
      rm -f SHA256SUMS
    else
      echo "No checksum file found, skipping verification"
    fi
  else
    echo "Skipping checksum verification as requested"
  fi
  
  # Set the model path for llama-server
  export LLAMA_ARG_MODEL="$model_path"
  echo "Model ready at: $LLAMA_ARG_MODEL"
}

parse_args() {
  MODEL_URL=""
  MODEL_PATH=""
  SKIP_CHECKSUM="false"
  GPU_LAYERS=""
  CONTEXT_SIZE=""
  BATCH_SIZE=""
  
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --model-url)
        if [ -z "${2:-}" ]; then
          echo "Error: --model-url requires a URL argument" >&2
          exit 1
        fi
        MODEL_URL="$2"
        shift 2
        ;;
      --model-path)
        if [ -z "${2:-}" ]; then
          echo "Error: --model-path requires a path argument" >&2
          exit 1
        fi
        MODEL_PATH="$2"
        shift 2
        ;;
      --skip-checksum)
        SKIP_CHECKSUM="true"
        shift
        ;;
      --gpu-layers)
        if [ -z "${2:-}" ]; then
          echo "Error: --gpu-layers requires a number argument" >&2
          exit 1
        fi
        GPU_LAYERS="$2"
        shift 2
        ;;
      --context-size)
        if [ -z "${2:-}" ]; then
          echo "Error: --context-size requires a number argument" >&2
          exit 1
        fi
        CONTEXT_SIZE="$2"
        shift 2
        ;;
      --batch-size)
        if [ -z "${2:-}" ]; then
          echo "Error: --batch-size requires a number argument" >&2
          exit 1
        fi
        BATCH_SIZE="$2"
        shift 2
        ;;
      --help)
        usage
        exit 0
        ;;
      *)
        echo "Error: Unknown option $1" >&2
        usage
        exit 1
        ;;
    esac
  done
  
  # Handle model download or path setting
  if [ -n "$MODEL_URL" ] && [ -n "$MODEL_PATH" ]; then
    echo "Error: Cannot specify both --model-url and --model-path" >&2
    exit 1
  elif [ -n "$MODEL_URL" ]; then
    download_and_verify_model "$MODEL_URL" "$SKIP_CHECKSUM"
  elif [ -n "$MODEL_PATH" ]; then
    if [ ! -f "$MODEL_PATH" ]; then
      echo "Error: Model file not found at $MODEL_PATH" >&2
      exit 1
    fi
    export LLAMA_ARG_MODEL="$MODEL_PATH"
    echo "Using existing model at: $LLAMA_ARG_MODEL"
  else
    echo "Warning: No model specified. llama-server may fail to start." >&2
  fi
}

set_default_env_vars() {
  # Set default host
  if [ -z ${LLAMA_ARG_HOST+x} ]; then
    export LLAMA_ARG_HOST="0.0.0.0"
  fi
  
  # Set default port (using your current port)
  if [ -z ${LLAMA_ARG_PORT+x} ]; then
    export LLAMA_ARG_PORT="8003"
  fi
  
  # Set GPU layers (default to auto)
  if [ -n "$GPU_LAYERS" ]; then
    export LLAMA_ARG_N_GPU_LAYERS="$GPU_LAYERS"
  elif [ -z ${LLAMA_ARG_N_GPU_LAYERS+x} ]; then
    export LLAMA_ARG_N_GPU_LAYERS="-1"  # -1 means auto-detect
  fi
  
  # Set context size if specified
  if [ -n "$CONTEXT_SIZE" ]; then
    export LLAMA_ARG_CTX_SIZE="$CONTEXT_SIZE"
  fi
  
  # Set batch size if specified
  if [ -n "$BATCH_SIZE" ]; then
    export LLAMA_ARG_N_BATCH="$BATCH_SIZE"
  fi
  
  # Enable Jinja templates for tools/function calling support
  export LLAMA_ARG_CHAT_TEMPLATE=""  # Use model's built-in template
  export LLAMA_ARG_JINJA="true"      # Enable Jinja templates
}

check_cuda() {
  echo "Checking CUDA availability..."
  if command -v nvidia-smi >/dev/null 2>&1; then
    echo "NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits
  else
    echo "Warning: nvidia-smi not available. CUDA support may not work properly."
  fi
}

# Parse command line arguments
parse_args "$@"

# Set default environment variables
set_default_env_vars

# Check CUDA setup
check_cuda

# Show final configuration
echo ""
echo "Starting llama-server with CUDA support:"
echo "  Host: ${LLAMA_ARG_HOST}"
echo "  Port: ${LLAMA_ARG_PORT}"
echo "  GPU Layers: ${LLAMA_ARG_N_GPU_LAYERS}"
echo "  Jinja Templates: ${LLAMA_ARG_JINJA}"
if [ -n "${LLAMA_ARG_MODEL:-}" ]; then
  echo "  Model: ${LLAMA_ARG_MODEL}"
fi
if [ -n "${LLAMA_ARG_CTX_SIZE:-}" ]; then
  echo "  Context Size: ${LLAMA_ARG_CTX_SIZE}"
fi
if [ -n "${LLAMA_ARG_N_BATCH:-}" ]; then
  echo "  Batch Size: ${LLAMA_ARG_N_BATCH}"
fi
echo ""

# Start the server with jinja support
set -x
exec llama-server
