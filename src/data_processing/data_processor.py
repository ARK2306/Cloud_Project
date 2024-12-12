import pandas as pd
import numpy as np
from typing import List, Tuple, Optional
from sklearn.preprocessing import StandardScaler
import joblib
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrafficDataProcessor:
    def __init__(self, scaler_path: Optional[str] = None):
        """Initialize data processor with optional pre-trained scaler"""
        self.scaler = joblib.load(scaler_path) if scaler_path else StandardScaler()
        
    def process_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process traffic data for model input"""
        try:
            # Clean data
            df_cleaned = self._clean_data(df)
            
            # Create features
            df_features = self._create_features(df_cleaned)
            
            # Scale features
            df_scaled = self._scale_features(df_features)
            
            return df_scaled
            
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            raise

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean raw traffic data"""
        df = df.copy()
        
        # Handle missing values
        df = df.interpolate(method='time')
        
        # Remove outliers
        df = self._remove_outliers(df)
        
        # Sort by timestamp
        df = df.sort_index()
        
        return df

    def _remove_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove outliers using IQR method"""
        for column in ['volume', 'speed', 'occupancy']:
            Q1 = df[column].quantile(0.25)
            Q3 = df[column].quantile(0.75)
            IQR = Q3 - Q1
            df = df[~((df[column] < (Q1 - 1.5 * IQR)) | 
                     (df[column] > (Q3 + 1.5 * IQR)))]
        return df

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create features for model input"""
        df = df.copy()
        
        # Time-based features
        df['hour'] = df.index.hour
        df['day_of_week'] = df.index.dayofweek
        df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
        
        # Rolling statistics
        windows = [1, 3, 6, 12, 24]
        for window in windows:
            df[f'volume_roll_{window}h'] = df['volume'].rolling(window).mean()
            df[f'speed_roll_{window}h'] = df['speed'].rolling(window).mean()
            
        # Lag features
        lags = [1, 24, 168]  # 1 hour, 1 day, 1 week
        for lag in lags:
            df[f'volume_lag_{lag}'] = df['volume'].shift(lag)
            
        return df.dropna()

    def _scale_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Scale features using StandardScaler"""
        scaled_data = self.scaler.fit_transform(df)
        return pd.DataFrame(scaled_data, columns=df.columns, index=df.index)

    def prepare_sequences(self, df: pd.DataFrame, 
                         sequence_length: int = 24) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for LSTM input"""
        data = df.values
        X, y = [], []
        
        for i in range(len(data) - sequence_length):
            X.append(data[i:(i + sequence_length)])
            y.append(data[i + sequence_length, df.columns.get_loc('volume')])
            
        return np.array(X), np.array(y)

    def save_scaler(self, path: str):
        """Save fitted scaler"""
        joblib.dump(self.scaler, path)
        logger.info(f"Scaler saved to {path}")