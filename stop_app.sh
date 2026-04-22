#!/bin/bash

# 定义服务根目录
SERVICE_ROOT="$(dirname "$0")"

# 函数：获取当前目录下 km_portal.py 的进程PID
get_service_pid() {
    local script_dir="$1"
    pgrep -f "python.*km_portal.py" | while read pid; do
        if pwdx "$pid" 2>/dev/null | grep -q "${script_dir}"; then
            echo "$pid"
        fi
    done
}

# 获取主程序PID
PIDS=$(get_service_pid "${SERVICE_ROOT}")

# 无进程则直接退出
if [ -z "$PIDS" ]; then
    echo "没有找到运行中的 KM PORTAL 服务。"
    exit 0
fi

echo "即将关闭进程: $PIDS"

# 优雅关闭
for PID in $PIDS; do
    if kill -0 $PID 2>/dev/null; then
        kill -SIGTERM $PID
        echo "已向进程 $PID 发送优雅关闭信号"
    fi
done

# 等待退出（超时10秒强制杀死）
TIMEOUT=10
for PID in $PIDS; do
    COUNT=0
    while kill -0 $PID 2>/dev/null && [ $COUNT -lt $TIMEOUT ]; do
        sleep 1
        COUNT=$((COUNT + 1))
    done

    if kill -0 $PID 2>/dev/null; then
        kill -SIGKILL $PID 2>/dev/null
        echo "进程 $PID 已强制终止"
    else
        echo "进程 $PID 已正常退出"
    fi
done

echo "KM PORTAL 已关闭完成。"