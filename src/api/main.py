from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from confluent_kafka import Consumer
import json
import asyncio
import logging
from typing import List, Dict
from prometheus_client import start_http_server, Counter, Gauge, Histogram
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
PREDICTIONS_TOTAL = Counter('predictions_total', 'Total predictions made')
ACTIVE_CONNECTIONS = Gauge('active_websocket_connections', 'Number of active WebSocket connections')
PREDICTION_ERROR = Histogram('prediction_error', 'Prediction error distribution')

app = FastAPI(title="Traffic Prediction API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Store active WebSocket connections
active_connections: List[WebSocket] = []

class KafkaConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str):
        self.consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'latest'
        })
        self.consumer.subscribe(['traffic_predictions'])
        
    async def consume_messages(self):
        while True:
            try:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    await asyncio.sleep(0.1)
                    continue
                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue
                    
                data = json.loads(msg.value().decode('utf-8'))
                
                # Update metrics
                PREDICTIONS_TOTAL.inc()
                error = abs(data['predicted_volume'] - data['actual_volume'])
                PREDICTION_ERROR.observe(error)
                
                # Send to all connected clients
                for connection in active_connections:
                    try:
                        await connection.send_json(data)
                    except WebSocketDisconnect:
                        active_connections.remove(connection)
                        ACTIVE_CONNECTIONS.dec()
                        
            except Exception as e:
                logger.error(f"Error in consume_messages: {e}")
                await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    """Start Prometheus metrics server and Kafka consumer"""
    # Start Prometheus metrics server
    start_http_server(8000)
    
    # Start Kafka consumer
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    group_id = os.getenv('CONSUMER_GROUP_ID', 'dashboard_group')
    
    consumer = KafkaConsumer(bootstrap_servers, group_id)
    asyncio.create_task(consumer.consume_messages())

@app.websocket("/ws/traffic")
async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connections"""
    await websocket.accept()
    active_connections.append(websocket)
    ACTIVE_CONNECTIONS.inc()
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        ACTIVE_CONNECTIONS.dec()
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)
            ACTIVE_CONNECTIONS.dec()

# REST API endpoints for metrics and status
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.get("/metrics/summary")
async def get_metrics_summary():
    """Get summary of prediction metrics"""
    return {
        "total_predictions": PREDICTIONS_TOTAL._value.get(),
        "active_connections": ACTIVE_CONNECTIONS._value.get(),
        "average_error": PREDICTION_ERROR.observe(),
    }