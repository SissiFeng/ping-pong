import json
import gradio as gr
import paho.mqtt.client as mqtt
import time
import random
from queue import Queue

# 简单的全局配置和状态
MQTT_HOST = "broker.hivemq.com"
MQTT_PORT = 1883
command_queue = Queue()
mqtt_client = None

# 模拟设备状态
device_state = {
    "rgb": {"r": 0, "g": 0, "b": 0},
    "temperature": 25.0,
    "rpm": 0
}

# 基础的 MQTT 回调函数
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe("ping/command")

def on_message(client, userdata, msg):
    try:
        command = json.loads(msg.payload.decode())
        command_queue.put(command)
        print(f"Received command: {command}")
    except Exception as e:
        print(f"Error processing message: {e}")

# 处理接收到的命令
def process_command(command):
    command_type = command.get("type")
    data = command.get("data", {})
    session_id = command.get("session_id")
    
    if command_type == "RGB Command":
        device_state["rgb"] = data
        response_data = {
            "current_state": "applied",
            "power_consumption": random.uniform(0.1, 1.0),
            "applied_values": device_state["rgb"]
        }
    elif command_type == "Temperature Reading":
        device_state["temperature"] += random.uniform(-0.5, 0.5)
        response_data = {
            "current_temperature": device_state["temperature"],
            "humidity": random.uniform(40, 60),
            "pressure": random.uniform(980, 1020)
        }
    elif command_type == "Weight Data":
        if "set_rpm" in data:
            device_state["rpm"] = data["set_rpm"]
        response_data = {
            "calibrated_weight": random.uniform(95, 105),
            "current_rpm": device_state["rpm"],
            "stability": random.uniform(0.98, 1.02)
        }
    else:
        response_data = {"error": "Unknown command type"}
    
    return {
        "type": command_type,
        "data": response_data,
        "timestamp": time.time(),
        "session_id": session_id
    }

# MQTT 客户端控制
def start_mqtt():
    global mqtt_client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()
    return "MQTT client started"

def stop_mqtt():
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    return "MQTT client stopped"

# 检查和处理命令
def check_commands():
    if not mqtt_client:
        return "MQTT client not started"
    
    responses = []
    while not command_queue.empty():
        command = command_queue.get_nowait()
        response = process_command(command)
        mqtt_client.publish(f"pong/{response['session_id']}/response", 
                          json.dumps(response))
        responses.append(json.dumps(response, indent=2))
    
    return "\n".join(responses) if responses else "No new commands"

# Gradio 界面
with gr.Blocks(title="MQTT Pong", theme=gr.themes.Soft(
    primary_hue="gray",
    secondary_hue="blue",
)) as demo:
    gr.Markdown("# MQTT Pong Response System")
    
    with gr.Row():
        # 左侧控制面板
        with gr.Column(scale=1, variant="panel"):
            gr.Markdown("### System Control")
            with gr.Row():
                start_btn = gr.Button("Start System", variant="primary")
                stop_btn = gr.Button("Stop System", variant="secondary")
            status = gr.Textbox(label="System Status", lines=2)
            
            gr.Markdown("### Device Status")
            device_info = gr.JSON(
                label="Current Device State",
                value=device_state,
                show_label=True
            )
        
        # 右侧命令历史
        with gr.Column(scale=1, variant="panel"):
            gr.Markdown("### Command History")
            check_btn = gr.Button("Refresh Commands", variant="secondary")
            command_box = gr.Textbox(
                label="Command Log",
                lines=15,
                max_lines=20,
                show_copy_button=True
            )
    
    # 事件处理
    start_btn.click(start_mqtt, outputs=status)
    stop_btn.click(stop_mqtt, outputs=status)
    check_btn.click(check_commands, outputs=command_box)

if __name__ == "__main__":
    demo.launch()