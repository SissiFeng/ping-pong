import json
import gradio as gr
import paho.mqtt.client as mqtt
import time
from queue import Queue

# 简单的全局配置和状态
MQTT_HOST = "broker.hivemq.com"
MQTT_PORT = 1883
response_queue = Queue()
mqtt_client = None
session_id = None

# 基础的 MQTT 回调函数
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    if session_id:
        client.subscribe(f"pong/{session_id}/response")

def on_message(client, userdata, msg):
    try:
        response = json.loads(msg.payload.decode())
        response_queue.put(response)
        print(f"Received: {response}")
    except Exception as e:
        print(f"Error processing message: {e}")

# 简单的会话初始化
def initialize_session():
    global mqtt_client, session_id
    session_id = f"ping_{int(time.time())}"
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()
    return f"Connected with session: {session_id}"

# 发送命令的基础函数
def send_command(command_type, data=None):
    if not mqtt_client:
        return "Please initialize session first"
    
    payload = {
        "type": command_type,
        "data": data or {},
        "session_id": session_id,
        "timestamp": time.time()
    }
    
    mqtt_client.publish("ping/command", json.dumps(payload))
    return f"Sent {command_type}"

# 简单的命令函数
def send_rgb(r, g, b):
    return send_command("RGB Command", {"r": r, "g": g, "b": b})

def send_weight_request(rpm):
    return send_command("Weight Data", {"set_rpm": rpm, "request_weight": True})

def check_responses():
    responses = []
    while not response_queue.empty():
        response = response_queue.get_nowait()
        responses.append(json.dumps(response, indent=2))
    return "\n".join(responses) if responses else "No new responses"

# Gradio 界面
with gr.Blocks(title="MQTT Ping", theme=gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="gray",
)) as demo:
    gr.Markdown("# MQTT Ping Control System")
    
    with gr.Row():
        # 左侧控制面板
        with gr.Column(scale=1, variant="panel"):
            gr.Markdown("### System Control")
            connect_btn = gr.Button("Initialize Connection", variant="primary")
            status = gr.Textbox(label="Connection Status", lines=2)
            
            with gr.Tabs():
                # RGB 控制面板
                with gr.TabItem("RGB Control"):
                    with gr.Group():
                        r = gr.Slider(0, 255, 128, label="Red Value", container=False)
                        g = gr.Slider(0, 255, 128, label="Green Value", container=False)
                        b = gr.Slider(0, 255, 128, label="Blue Value", container=False)
                        send_rgb_btn = gr.Button("Apply RGB Settings", variant="secondary")
                        rgb_status = gr.Textbox(label="RGB Status", lines=2)
                
                # 重量控制面板
                with gr.TabItem("Weight Control"):
                    with gr.Group():
                        rpm = gr.Slider(0, 5000, 1000, label="RPM Setting", container=False)
                        send_weight_btn = gr.Button("Send Weight Request", variant="secondary")
                        weight_status = gr.Textbox(label="Weight Status", lines=2)
        
        # 右侧状态显示
        with gr.Column(scale=1, variant="panel"):
            gr.Markdown("### System Status")
            with gr.Row():
                check_btn = gr.Button("Refresh Status", variant="secondary")
            responses = gr.Textbox(
                label="System Response",
                lines=10,
                max_lines=15,
                show_copy_button=True
            )
    
    # 事件处理
    connect_btn.click(initialize_session, outputs=status)
    send_rgb_btn.click(send_rgb, [r, g, b], rgb_status)
    send_weight_btn.click(send_weight_request, rpm, weight_status)
    check_btn.click(check_responses, outputs=responses)

if __name__ == "__main__":
    demo.launch()