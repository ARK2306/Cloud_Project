import requests
import pandas as pd
from datetime import datetime, timedelta
import logging
import os
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrafficDataCollector:
    def __init__(self, api_keys: Dict[str, str]):
        """
        Initialize traffic data collector with API keys
        api_keys: Dictionary of API keys for different services
        """
        self.api_keys = api_keys
        self.base_urls = {
            'pems': 'https://pems.dot.ca.gov/api',
            'nyc_dot': 'https://data.cityofnewyork.us/api',
        }

    async def collect_data(self, source: str, parameters: Dict) -> pd.DataFrame:
        """Collect traffic data from specified source"""
        try:
            headers = self._get_headers(source)
            url = self.base_urls[source]
            response = requests.get(url, headers=headers, params=parameters)
            response.raise_for_status()
            
            data = response.json()
            return self._format_data(data, source)
            
        except Exception as e:
            logger.error(f"Error collecting data from {source}: {e}")
            raise

    def _get_headers(self, source: str) -> Dict[str, str]:
        """Get API headers for specified source"""
        api_key = self.api_keys.get(source)
        if not api_key:
            raise ValueError(f"No API key found for source: {source}")
            
        return {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

    def _format_data(self, data: Dict, source: str) -> pd.DataFrame:
        """Format raw data into standardized DataFrame"""
        if source == 'pems':
            return self._format_pems_data(data)
        elif source == 'nyc_dot':
            return self._format_nyc_data(data)
        elif source == 'uk_highway':
            return self._format_uk_data(data)
        else:
            raise ValueError(f"Unsupported data source: {source}")

    def _format_pems_data(self, data: Dict) -> pd.DataFrame:
        """Format PeMS data into standard format"""
        df = pd.DataFrame(data['data'])
        df.columns = ['timestamp', 'volume', 'speed', 'occupancy']
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df

    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate collected data"""
        if df.empty:
            return False
            
        required_columns = ['timestamp', 'volume', 'speed', 'occupancy']
        if not all(col in df.columns for col in required_columns):
            return False
            
        # Check for invalid values
        if (df['volume'] < 0).any() or (df['speed'] < 0).any():
            return False
            
        return True