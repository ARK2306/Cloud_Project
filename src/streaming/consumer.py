from confluent_kafka import Consumer, Producer
import json
import logging
import os
from typing import Dict, Any
import numpy as np
from ..ml.model import TrafficPredictionModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrafficConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str):
        """Initialize Kafka consumer and producer"""
        self.consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'latest'
        })
        
        self.producer = Producer({
            'bootstrap.servers': bootstrap_servers,
            'client.id': 'prediction_producer'
        })
        
        self.input_topic = 'traffic_data'
        self.output_topic = 'traffic_predictions'
        
        # Load ML model
        self.model = TrafficPredictionModel.load('models/traffic_model.h5')
        
        # Initialize data buffer for sequences
        self.data_buffer = []
        self.sequence_length = 24

    def delivery_report(self, err: Any, msg: Any):
        """Callback for prediction delivery reports"""
        if err is not None:
            logger.error(f'Prediction delivery failed: {err}')
        else:
            logger.info(f'Prediction delivered to {msg.topic()} [{msg.partition()}]')

    def process_message(self, message: Dict):
        """Process incoming message and generate prediction"""
        try:
            # Add to buffer
            self.data_buffer.append(message)
            
            # Keep buffer at sequence length
            if len(self.data_buffer) > self.sequence_length:
                self.data_buffer.pop(0)
            
            # Generate prediction if we have enough data
            if len(self.data_buffer) == self.sequence_length:
                # Prepare sequence for prediction
                sequence = self._prepare_sequence()
                
                # Make prediction
                prediction = self.model.predict(sequence)
                
                # Prepare output message
                output = {
                    'timestamp': message['timestamp'],
                    'actual_volume': message['volume'],
                    'predicted_volume': float(prediction[0][0])
                }
                
                # Send prediction
                self.producer.produce(
                    topic=self.output_topic,
                    value=json.dumps(output).encode('utf-8'),
                    callback=self.delivery_report
                )
                
                self.producer.poll(0)

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise

    def _prepare_sequence(self) -> np.ndarray:
        """Prepare sequence for model input"""
        sequence = np.array([[
            float(msg['volume']),
            float(msg['speed']),
            float(msg['occupancy'])
        ] for msg in self.data_buffer])
        
        return np.expand_dims(sequence, axis=0)

    def run(self):
        """Run the consumer"""
        try:
            self.consumer.subscribe([self.input_topic])
            
            while True:
                msg = self.consumer.poll(1.0)
                
                if msg is None:
                    continue
                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue
                    
                try:
                    message = json.loads(msg.value().decode('utf-8'))
                    self.process_message(message)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except KeyboardInterrupt:
            logger.info("Shutting down consumer...")
        finally:
            self.consumer.close()
            self.producer.flush()

if __name__ == "__main__":
    # Load configuration
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    group_id = os.getenv('CONSUMER_GROUP_ID', 'traffic_prediction_group')

    # Initialize and run consumer
    consumer = TrafficConsumer(bootstrap_servers, group_id)
    consumer.run()