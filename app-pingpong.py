import json
import gradio as gr
import paho.mqtt.client as mqtt
import time
import random
from queue import Queue

# 全局配置
MQTT_HOST = "broker.hivemq.com"
MQTT_PORT = 1883

# 全局状态
response_queue = Queue()
command_queue = Queue()
mqtt_ping_client = None
mqtt_pong_client = None
session_id = None
device_state = {
    "rgb": {"r": 0, "g": 0, "b": 0},
    "temperature": 25.0,
    "rpm": 0
}

# MQTT 回调函数
def on_ping_connect(client, userdata, flags, rc):
    print(f"Ping connected with result code {rc}")
    if session_id:
        client.subscribe(f"pong/{session_id}/response")

def on_pong_connect(client, userdata, flags, rc):
    print(f"Pong connected with result code {rc}")
    client.subscribe("ping/command")

def on_ping_message(client, userdata, msg):
    try:
        response = json.loads(msg.payload.decode())
        response_queue.put(response)
        print(f"Ping received: {response}")
    except Exception as e:
        print(f"Ping error: {e}")

def on_pong_message(client, userdata, msg):
    try:
        command = json.loads(msg.payload.decode())
        command_queue.put(command)
        print(f"Pong received: {command}")
    except Exception as e:
        print(f"Pong error: {e}")

# Ping 功能
def initialize_ping():
    global mqtt_ping_client, session_id
    session_id = f"ping_{int(time.time())}"
    mqtt_ping_client = mqtt.Client()
    mqtt_ping_client.on_connect = on_ping_connect
    mqtt_ping_client.on_message = on_ping_message
    mqtt_ping_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_ping_client.loop_start()
    return f"Ping initialized: {session_id}"

def send_command(command_type, data=None):
    if not mqtt_ping_client:
        return "Please initialize ping first"
    
    payload = {
        "type": command_type,
        "data": data or {},
        "session_id": session_id,
        "timestamp": time.time()
    }
    mqtt_ping_client.publish("ping/command", json.dumps(payload))
    return f"Sent {command_type}"

def send_rgb(r, g, b):
    if not mqtt_ping_client:
        return "Please initialize ping first"
    
    payload = {
        "type": "RGB Command",
        "data": {"r": r, "g": g, "b": b},
        "session_id": session_id,
        "timestamp": time.time()
    }
    # 发送命令
    mqtt_ping_client.publish("ping/command", json.dumps(payload))
    # 将命令放入命令队列供 pong 显示
    command_queue.put(payload)
    return f"Sent RGB Command: R={r}, G={g}, B={b}"

def send_weight_request(rpm):
    return send_command("Weight Data", {"set_rpm": rpm, "request_weight": True})

# Pong 功能
def initialize_pong():
    global mqtt_pong_client
    mqtt_pong_client = mqtt.Client()
    mqtt_pong_client.on_connect = on_pong_connect
    mqtt_pong_client.on_message = on_pong_message
    mqtt_pong_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_pong_client.loop_start()
    return "Pong started"

def process_command(command):
    global device_state
    command_type = command.get("type")
    data = command.get("data", {})
    session_id = command.get("session_id")
    
    if command_type == "RGB Command":
        # 更新设备状态
        device_state = {
            **device_state,
            "rgb": {
                "r": int(data.get("r", 0)),
                "g": int(data.get("g", 0)),
                "b": int(data.get("b", 0))
            }
        }
        print(f"Processing RGB command: {data}")
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
    
    response = {
        "type": command_type,
        "data": response_data,
        "timestamp": time.time(),
        "session_id": session_id
    }
    
    if mqtt_pong_client:
        mqtt_pong_client.publish(f"pong/{session_id}/response", json.dumps(response))
    return json.dumps(response, indent=2)

def check_ping_responses():
    """检查 ping 的响应队列"""
    responses = []
    while not response_queue.empty():
        response = response_queue.get_nowait()
        responses.append(json.dumps(response, indent=2))
    return "\n".join(responses) if responses else "No new responses"

def check_pong_commands():
    """检查并处理命令队列"""
    responses = []
    while not command_queue.empty():
        command = command_queue.get_nowait()
        response = process_command(command)
        responses.append(response)
    return "\n".join(responses) if responses else "No new commands"

# 添加 stop_mqtt 函数
def stop_mqtt():
    global mqtt_ping_client, mqtt_pong_client
    if mqtt_ping_client:
        mqtt_ping_client.loop_stop()
        mqtt_ping_client.disconnect()
    if mqtt_pong_client:
        mqtt_pong_client.loop_stop()
        mqtt_pong_client.disconnect()
    return "Both Ping and Pong clients stopped"

# 添加实时更新函数
def update_rgb_preview(r, g, b):
    """实时更新 RGB 预览值"""
    global device_state
    device_state = {
        **device_state,
        "rgb": {
            "r": int(r),
            "g": int(g),
            "b": int(b)
        }
    }
    return gr.update(value=device_state)

# 添加 RPM 预览更新函数
def update_rpm_preview(rpm):
    """实时更新 RPM 预览值"""
    global device_state
    device_state = {
        **device_state,
        "rpm": int(rpm)
    }
    return gr.update(value=device_state)

# 添加温度湿度预览更新函数
def update_temperature_preview(temperature):
    """实时更新温度预览值"""
    global device_state
    device_state = {
        **device_state,
        "temperature": float(temperature)
    }
    return gr.update(value=device_state)

# Gradio 界面
with gr.Blocks(title="MQTT Ping-Pong System", theme=gr.themes.Base(
    primary_hue=gr.themes.colors.Color(
        c50="#edf2f0",
        c100="#dbE5E1",
        c200="#B8CCC6",
        c300="#96B3AB",
        c400="#7FA595",  # 右侧主色
        c500="#5C8072",  # 左侧主色
        c600="#4A665B",
        c700="#374D45",
        c800="#25332E",
        c900="#121917",
        c950="#080C0B",  # 添加这个
    )
)) as demo:
    gr.Markdown("# 🏓 MQTT Ping-Pong Communication System <span class='pong-emoji'>🏓</span>")
    
    # 添加 CSS，包括字体设置
    gr.HTML("""
        <style>
            /* 基础样式 */
            .ping-panel {
                background-color: #5C8072 !important;
                border-radius: 8px;
                padding: 20px;
            }
            .pong-panel {
                background-color: #7FA595 !important;
                border-radius: 8px;
                padding: 20px;
            }
            
            /* 字体设置 */
            * {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, 
                           "Helvetica Neue", Arial, sans-serif;
            }
            
            /* 标题样式 */
            h1, h2, h3, .header {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, 
                           "Helvetica Neue", Arial, sans-serif;
                font-weight: 600;
                color: #2c3e50;
            }
            
            /* 按钮样式 */
            .gr-button {
                margin: 10px 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, 
                           "Helvetica Neue", Arial, sans-serif;
                font-weight: 500;
            }
            
            /* 分组样式 */
            .gr-group {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 15px;
                margin: 10px 0;
            }
            
            /* 标签样式 */
            label {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, 
                           "Helvetica Neue", Arial, sans-serif;
                font-weight: 500;
            }
            
            /* Pong emoji 翻转 - 应用于所有带 pong-emoji 类的元素 */
            .pong-emoji {
                display: inline-block;
                transform: scaleX(-1);
                margin-left: 5px;  /* 添加一点间距 */
            }
            
            /* 步骤标题样式 */
            .step-header {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, 
                           "Helvetica Neue", Arial, sans-serif;
                font-weight: 600;
                color: #2c3e50;
                margin: 15px 0 10px 0;
            }
        </style>
    """)
    
    with gr.Row():
        # Ping 部分（左侧）
        with gr.Column(scale=1, variant="panel", elem_classes=["ping-panel"]):
            gr.Markdown("### 🏓 Ping Control (Sender)")
            with gr.Group():
                gr.Markdown("**Step 1: Initialize Connection**")
                ping_init_btn = gr.Button("Initialize Ping", variant="primary", size="lg")
                ping_status = gr.Textbox(label="Connection Status", lines=2)
            
            with gr.Tabs():
                with gr.TabItem("RGB Control"):
                    with gr.Group():
                        gr.Markdown("**Step 2: Configure RGB Values**")
                        r = gr.Slider(0, 255, 128, label="Red Value", interactive=True)
                        g = gr.Slider(0, 255, 128, label="Green Value", interactive=True)
                        b = gr.Slider(0, 255, 128, label="Blue Value", interactive=True)
                        gr.Markdown("**Step 3: Send Command**")
                        send_rgb_btn = gr.Button("Send RGB Command", variant="secondary", size="lg")
                        rgb_status = gr.Textbox(label="RGB Status", lines=2)
                
                with gr.TabItem("Weight Control"):
                    with gr.Group():
                        gr.Markdown("**Step 2: Set RPM Value**")
                        rpm = gr.Slider(0, 5000, 1000, label="RPM Setting", interactive=True)
                        gr.Markdown("**Step 3: Send Request**")
                        send_weight_btn = gr.Button("Send Weight Request", variant="secondary", size="lg")
                        weight_status = gr.Textbox(label="Weight Status", lines=2)
                
                # 添加温度湿度控制标签页
                with gr.TabItem("Temperature Control"):
                    with gr.Group():
                        gr.Markdown("**Step 2: Set Temperature Value**")
                        temperature = gr.Slider(0, 50, 25, label="Temperature (°C)", interactive=True)
                        gr.Markdown("**Step 3: Send Request**")
                        send_temp_btn = gr.Button("Send Temperature Request", variant="secondary", size="lg")
                        temp_status = gr.Textbox(label="Temperature Status", lines=2)
            
            with gr.Group():
                gr.Markdown("**Step 4: Check Responses**")
                check_ping_btn = gr.Button("Check Responses", variant="secondary", size="lg")
                ping_responses = gr.Textbox(
                    label="Response Log", 
                    lines=10, 
                    show_copy_button=True
                )
        
        # Pong 部分（右侧）
        with gr.Column(scale=1, variant="panel", elem_classes=["pong-panel"]):
            gr.Markdown("### Pong Monitor (Receiver) <span class='pong-emoji'>🏓</span>")
            with gr.Group():
                gr.Markdown("**Step 1: Start System**")
                with gr.Row():
                    pong_init_btn = gr.Button("Start Pong", variant="primary", size="lg")
                    pong_stop_btn = gr.Button("Stop Pong", variant="secondary", size="lg")
                pong_status = gr.Textbox(label="System Status", lines=2)
            
            with gr.Group():
                gr.Markdown("**Step 2: Monitor Device Status**")
                refresh_btn = gr.Button("🔄 Refresh All", variant="primary", size="lg")
                device_info = gr.JSON(
                    label="Current Device State",
                    value=device_state,
                    show_label=True
                )
            
            with gr.Group():
                gr.Markdown("**Step 3: Check Incoming Commands**")
                check_pong_btn = gr.Button("Check Commands", variant="secondary", size="lg")
                pong_commands = gr.Textbox(
                    label="Command Log",
                    lines=10,
                    show_copy_button=True
                )
    
    # 添加自动刷新功能
    def auto_refresh():
        # 检查命令并更新设备状态
        commands = check_pong_commands()
        current_state = device_state
        return [commands, current_state]

    # 添加手动刷新功能
    def refresh_all():
        """手动刷新所有状态"""
        commands = check_pong_commands()
        print(f"Current device state: {device_state}")
        
        # 返回三个更新：命令历史、设备状态和命令日志
        return [
            commands,  # pong_commands
            gr.update(value=device_state),  # device_info
            commands  # command_log
        ]

    # 修改事件处理
    ping_init_btn.click(initialize_ping, outputs=ping_status)
    pong_init_btn.click(initialize_pong, outputs=pong_status)
    pong_stop_btn.click(stop_mqtt, outputs=pong_status)
    
    # 发送命令时自动刷新 pong 端状态
    send_rgb_btn.click(
        send_rgb,
        [r, g, b],
        rgb_status
    ).then(
        check_pong_commands,  # 更新 pong 的命令显示
        outputs=[pong_commands]
    ).then(
        check_ping_responses,  # 更新 ping 的响应显示
        outputs=[ping_responses]
    )
    send_weight_btn.click(
        send_weight_request,
        rpm,
        weight_status
    ).then(
        refresh_all,
        outputs=[pong_commands, device_info, pong_commands]  # 添加 pong_commands 作为第三个输出
    )
    
    check_ping_btn.click(
        check_ping_responses,
        outputs=ping_responses
    )
    check_pong_btn.click(check_pong_commands, outputs=pong_commands)
    
    # 修改手动刷新按钮的事件处理
    refresh_btn.click(
        check_pong_commands,
        outputs=[pong_commands],
        show_progress=True
    )

    # 添加滑块值变化时的实时更新
    r.change(update_rgb_preview, inputs=[r, g, b], outputs=device_info)
    g.change(update_rgb_preview, inputs=[r, g, b], outputs=device_info)
    b.change(update_rgb_preview, inputs=[r, g, b], outputs=device_info)

    # 添加 RPM 滑块的实时更新
    rpm.change(update_rpm_preview, inputs=rpm, outputs=device_info)

    # 添加温度滑块的实时更新
    temperature.change(update_temperature_preview, inputs=temperature, outputs=device_info)

    # 添加温度命令发送处理
    send_temp_btn.click(
        lambda temp: send_command("Temperature Reading", {"temperature": temp}),
        inputs=[temperature],
        outputs=temp_status
    ).then(
        check_pong_commands,
        outputs=[pong_commands]
    ).then(
        check_ping_responses,
        outputs=[ping_responses]
    )

    demo.load(lambda: None)  # 初始化

if __name__ == "__main__":
    demo.launch()