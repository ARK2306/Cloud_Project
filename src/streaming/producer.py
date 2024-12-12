from confluent_kafka import Producer
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any
from ..data_processing.data_collector import TrafficDataCollector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrafficProducer:
    def __init__(self, bootstrap_servers: str, api_keys: Dict[str, str]):
        """Initialize Kafka producer and data collector"""
        self.producer = Producer({
            'bootstrap.servers': bootstrap_servers,
            'client.id': 'traffic_producer'
        })
        self.collector = TrafficDataCollector(api_keys)
        self.topic = 'traffic_data'

    def delivery_report(self, err: Any, msg: Any):
        """Callback for message delivery reports"""
        if err is not None:
            logger.error(f'Message delivery failed: {err}')
        else:
            logger.info(f'Message delivered to {msg.topic()} [{msg.partition()}]')

    async def collect_and_send_data(self, source: str, parameters: Dict):
        """Collect traffic data and send to Kafka"""
        try:
            # Collect data
            data = await self.collector.collect_data(source, parameters)
            
            # Validate data
            if not self.collector.validate_data(data):
                logger.error("Invalid data received")
                return

            # Convert to JSON and send
            for _, row in data.iterrows():
                message = {
                    'timestamp': row['timestamp'].isoformat(),
                    'volume': float(row['volume']),
                    'speed': float(row['speed']),
                    'occupancy': float(row['occupancy'])
                }
                
                self.producer.produce(
                    topic=self.topic,
                    value=json.dumps(message).encode('utf-8'),
                    callback=self.delivery_report
                )
                
                # Trigger delivery reports
                self.producer.poll(0)

            # Wait for outstanding messages
            self.producer.flush()

        except Exception as e:
            logger.error(f"Error in collect_and_send_data: {e}")
            raise

if __name__ == "__main__":
    # Load configuration
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    api_keys = {
        'pems': os.getenv('PEMS_API_KEY'),
        'nyc_dot': os.getenv('NYC_DOT_API_KEY'),
        'uk_highway': os.getenv('UK_HIGHWAY_API_KEY')
    }

    # Initialize and run producer
    producer = TrafficProducer(bootstrap_servers, api_keys)
    
    # Set up parameters for data collection
    parameters = {
        'startTime': datetime.now().isoformat(),
        'interval': '5min'
    }

    import asyncio
    asyncio.run(producer.collect_and_send_data('pems', parameters))