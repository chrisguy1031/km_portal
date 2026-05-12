#!/bin/bash

CONDA_BIN_PATH=$(which conda 2>/dev/null)

if [ -z "$CONDA_BIN_PATH" ]; then
    POSSIBLE_PATHS=("$HOME/anaconda3/bin/conda" "$HOME/miniconda3/bin/conda" "/opt/anaconda3/bin/conda" "/opt/miniconda3/bin/conda")
    for path in "${POSSIBLE_PATHS[@]}"; do
        if [ -f "$path" ]; then
            CONDA_BIN_PATH="$path"
            break
        fi
    done
fi

if [ -z "$CONDA_BIN_PATH" ]; then
    echo "❌ Error: Conda command not found. Please ensure conda is installed."
    exit 1
fi

CONDA_ROOT=$(dirname "$(dirname "$CONDA_BIN_PATH")")

source "$CONDA_ROOT/etc/profile.d/conda.sh"

conda activate km

# ------------------------------

# Function: start service and check status
start_service() {
    local service_name=$1
    local directory=$2
    local script=$3
    local wait_for_ready=$4

    echo "Starting ${service_name}..."

    # Switch to directory and start service, discard all output
    cd "$directory" && python "$script" >/dev/null 2>&1 &
    local pid=$!

    sleep 1
    if kill -0 $pid 2>/dev/null; then
        echo "✅ ${service_name} started successfully (PID: $pid)"

        return 0
    else
        echo "❌ Failed to start ${service_name}!"
        return 1
    fi
}

# Start main program (and wait for full initialization)
start_service "KBOT3 Main Program" "$(dirname "$0")" "km_portal.py" "true" || exit 1

echo
echo "🎉 KM portal service started successfully!"