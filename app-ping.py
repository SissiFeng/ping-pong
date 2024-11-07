import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import logging
import threading
from queue import Queue
from dataclasses import dataclass
import uuid
from contextlib import contextmanager
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class AppConfig:
    MAX_QUEUE_SIZE: int = 1000
    MQTT_TIMEOUT: int = 30
    MAX_RECONNECT_ATTEMPTS: int = 5
    MQTT_BROKER: str = "broker.hivemq.com"
    MQTT_PORT: int = 1883
    MQTT_KEEPALIVE: int = 60

class MQTTClient:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.config = AppConfig()
        self.client = None
        self.response_queue = Queue()
        self.connected = False
        self.streaming = False
        self.streaming_thread = None

    def connect(self):
        try:
            self.client = mqtt.Client(client_id=self.client_id, clean_session=True)
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            
            self.client.connect(
                self.config.MQTT_BROKER,
                self.config.MQTT_PORT,
                keepalive=self.config.MQTT_KEEPALIVE
            )
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            self.client.subscribe(f"pong/{self.client_id}/response")
        else:
            logger.error(f"Connection failed with code {rc}")

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode())
            self.response_queue.put(payload)
            logger.info(f"Received message: {payload}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning(f"Disconnected with code: {rc}")

    def publish(self, topic: str, payload: dict):
        try:
            message = json.dumps(payload)
            result = self.client.publish(topic, message)
            return result.rc == 0
        except Exception as e:
            logger.error(f"Error publishing message: {e}")
            return False

    def start_temperature_streaming(self, interval=1.0):
        """开始温度数据流式传输"""
        self.streaming = True
        
        def stream_temp():
            while self.streaming and self.connected:
                command = {
                    "type": "Temperature Reading",
                    "mode": "streaming",
                    "session_id": self.client_id,
                    "timestamp": time.time()
                }
                self.publish("ping/command", command)
                time.sleep(interval)

        self.streaming_thread = threading.Thread(target=stream_temp)
        self.streaming_thread.start()

    def stop_temperature_streaming(self):
        """停止温度数据流式传输"""
        self.streaming = False
        if self.streaming_thread:
            self.streaming_thread.join()

    def cleanup(self):
        self.stop_temperature_streaming()
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

@contextmanager
def mqtt_session(client_id: str):
    client = MQTTClient(client_id)
    try:
        if client.connect():
            yield client
        else:
            yield None
    finally:
        client.cleanup()

def main():
    st.set_page_config(page_title="MQTT Ping", layout="wide")
    st.title("MQTT Ping Application")

    # 初始化会话状态
    if 'client_id' not in st.session_state:
        st.session_state.client_id = f"ping_{uuid.uuid4().hex[:8]}"
    if 'command_history' not in st.session_state:
        st.session_state.command_history = []
    if 'temperature_data' not in st.session_state:
        st.session_state.temperature_data = []

    # 创建侧边栏控制面板
    with st.sidebar:
        st.header("Control Panel")
        command_type = st.selectbox(
            "Select Communication Mode",
            ["RGB Command", "Temperature Streaming", "Weight with RPM Control"]
        )
        
        if command_type == "RGB Command":
            # RGB命令控制
            r = st.slider("Red", 0, 255, 128)
            g = st.slider("Green", 0, 255, 128)
            b = st.slider("Blue", 0, 255, 128)
            if st.button("Send RGB Command"):
                with mqtt_session(st.session_state.client_id) as mqtt_client:
                    if mqtt_client:
                        command = {
                            "type": "RGB Command",
                            "data": {"r": r, "g": g, "b": b},
                            "session_id": st.session_state.client_id,
                            "timestamp": time.time()
                        }
                        if mqtt_client.publish("ping/command", command):
                            st.session_state.command_history.append(command)
                            st.success("RGB command sent!")

        elif command_type == "Temperature Streaming":
            # 温度流式数据
            if 'streaming_active' not in st.session_state:
                st.session_state.streaming_active = False

            if not st.session_state.streaming_active:
                if st.button("Start Temperature Streaming"):
                    st.session_state.streaming_active = True
                    st.experimental_rerun()
            else:
                if st.button("Stop Temperature Streaming"):
                    st.session_state.streaming_active = False
                    st.experimental_rerun()

            # 显示温度数据图表
            if st.session_state.temperature_data:
                df = pd.DataFrame(st.session_state.temperature_data)
                st.line_chart(df.set_index('timestamp')['temperature'])

        else:  # Weight with RPM Control
            # 重量测量和RPM控制
            rpm = st.slider("Set RPM", 0, 5000, 1000)
            if st.button("Send Weight Measurement Request"):
                with mqtt_session(st.session_state.client_id) as mqtt_client:
                    if mqtt_client:
                        command = {
                            "type": "Weight Data",
                            "data": {
                                "set_rpm": rpm,
                                "request_weight": True
                            },
                            "session_id": st.session_state.client_id,
                            "timestamp": time.time()
                        }
                        if mqtt_client.publish("ping/command", command):
                            st.session_state.command_history.append(command)
                            st.success("Weight measurement request sent!")

    # 主界面显示响应数据
    st.header("Latest Responses")
    with mqtt_session(st.session_state.client_id) as mqtt_client:
        if mqtt_client:
            # 处理温度流式数据
            if command_type == "Temperature Streaming" and st.session_state.streaming_active:
                mqtt_client.start_temperature_streaming()
                
            # 检查响应
            while not mqtt_client.response_queue.empty():
                response = mqtt_client.response_queue.get_nowait()
                
                if response.get("type") == "Temperature Reading":
                    temp_data = {
                        'timestamp': response.get("timestamp"),
                        'temperature': response["data"]["current_temperature"]
                    }
                    st.session_state.temperature_data.append(temp_data)
                    # 只保留最近100个数据点
                    st.session_state.temperature_data = st.session_state.temperature_data[-100:]
                else:
                    st.json(response)

    # 显示历史命令
    with st.expander("Command History"):
        for cmd in reversed(st.session_state.command_history[-10:]):
            st.json(cmd)

if __name__ == "__main__":
    main()