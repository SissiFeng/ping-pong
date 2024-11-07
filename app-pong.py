import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import logging
from queue import Queue
from dataclasses import dataclass
import uuid
from contextlib import contextmanager
import random

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
        self.command_queue = Queue()
        self.connected = False

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
            self.client.subscribe("ping/command")
        else:
            logger.error(f"Connection failed with code {rc}")

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode())
            self.command_queue.put(payload)
            logger.info(f"Received command: {payload}")
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

    def cleanup(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

class DeviceSimulator:
    def __init__(self):
        self.current_rgb = {"r": 0, "g": 0, "b": 0}
        self.current_rpm = 0
        self.current_temperature = 25.0

    def process_rgb_command(self, data):
        """处理RGB命令"""
        self.current_rgb = data
        return {
            "current_state": "applied",
            "power_consumption": random.uniform(0.1, 1.0),
            "applied_values": self.current_rgb
        }

    def process_temperature_reading(self, data):
        """处理温度读取请求"""
        self.current_temperature += random.uniform(-0.5, 0.5)
        return {
            "current_temperature": self.current_temperature,
            "humidity": random.uniform(40, 60),
            "pressure": random.uniform(980, 1020)
        }

    def process_weight_data(self, data):
        """处理重量测量和RPM设置"""
        if "set_rpm" in data:
            self.current_rpm = data["set_rpm"]
        
        return {
            "calibrated_weight": random.uniform(95, 105),
            "current_rpm": self.current_rpm,
            "stability": random.uniform(0.98, 1.02)
        }

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
    st.set_page_config(page_title="MQTT Pong", layout="wide")
    st.title("MQTT Pong Application")

    # 初始化会话状态
    if 'client_id' not in st.session_state:
        st.session_state.client_id = f"pong_{uuid.uuid4().hex[:8]}"
    if 'device_simulator' not in st.session_state:
        st.session_state.device_simulator = DeviceSimulator()
    if 'command_history' not in st.session_state:
        st.session_state.command_history = []

    # 创建MQTT客户端并处理命令
    with mqtt_session(st.session_state.client_id) as mqtt_client:
        if mqtt_client:
            while not mqtt_client.command_queue.empty():
                command = mqtt_client.command_queue.get_nowait()
                command_type = command.get("type")
                data = command.get("data", {})
                session_id = command.get("session_id")
                
                # 处理不同类型的命令
                if command_type == "RGB Command":
                    response_data = st.session_state.device_simulator.process_rgb_command(data)
                elif command_type == "Temperature Reading":
                    response_data = st.session_state.device_simulator.process_temperature_reading(data)
                elif command_type == "Weight Data":
                    response_data = st.session_state.device_simulator.process_weight_data(data)
                else:
                    response_data = {"error": "Unknown command type"}

                # 发送响应
                response = {
                    "type": command_type,
                    "data": response_data,
                    "timestamp": time.time(),
                    "session_id": session_id
                }
                
                response_topic = f"pong/{session_id}/response"
                if mqtt_client.publish(response_topic, response):
                    st.session_state.command_history.append({
                        "command": command,
                        "response": response,
                        "timestamp": time.time()
                    })

    # 显示命令历史
    if st.session_state.command_history:
        st.subheader("Command History")
        for item in st.session_state.command_history:
            st.json(item)

if __name__ == "__main__":
    main()