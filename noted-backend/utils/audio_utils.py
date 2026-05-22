import numpy as np
import logging
from typing import Union, Tuple
import librosa

logger = logging.getLogger(__name__)

def convert_audio_format(audio_array: Union[bytes, np.ndarray], 
                        target_sr: int = 16000, 
                        target_channels: int = 1) -> np.ndarray:
    """
    Convert audio data to target format
    
    Args:
        audio_data: Audio data as bytes or numpy array
        target_sr: Target sample rate
        target_channels: Target number of channels (1 for mono)
        
    Returns:
        Audio as numpy array (mono, target_sr)
    """
    try:
        # If input is bytes, convert to numpy array first
        if isinstance(audio_array, bytes):
            # Assume 16-bit PCM audio data
            audio_array = np.frombuffer(audio_array, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Convert to mono if needed
        if len(audio_array.shape) > 1:
            audio_array = np.mean(audio_array, axis=1)
         
        return audio_array.astype(np.float32)
        
    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        return np.array([], dtype=np.float32)

def load_audio_file(filepath: str, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
    """
    Load audio file
    
    Args:
        filepath: Path to audio file
        target_sr: Target sample rate
        
    Returns:
        Tuple of (audio_data, sample_rate)
    """
    try:
        audio_data, sr = librosa.load(filepath, sr=target_sr, mono=True)
        return audio_data, sr
    except Exception as e:
        logger.error(f"Error loading audio file {filepath}: {e}")
        return np.array([]), 0


def validate_audio_format(audio_data: np.ndarray, 
                         min_duration: float = 0.1,
                         max_duration: float = 300.0,
                         sample_rate: int = 16000) -> bool:
    """
    Validate audio format and duration
    
    Args:
        audio_data: Audio data to validate
        min_duration: Minimum duration in seconds
        max_duration: Maximum duration in seconds
        sample_rate: Sample rate
        
    Returns:
        True if valid
    """
    try:
        if len(audio_data) == 0:
            return False
        
        duration = len(audio_data) / sample_rate
        
        if duration < min_duration or duration > max_duration:
            return False
        
        # Check for reasonable audio values
        if np.all(audio_data == 0) or np.any(np.isnan(audio_data)) or np.any(np.isinf(audio_data)):
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Audio validation error: {e}")
        return False

def detect_silence(audio_data: np.ndarray, 
                  threshold: float = 0.01,
                  min_silence_duration: float = 0.5,
                  sample_rate: int = 16000) -> list:
    """
    Detect silence segments in audio
    
    Args:
        audio_data: Audio data
        threshold: Energy threshold for silence
        min_silence_duration: Minimum silence duration in seconds
        sample_rate: Sample rate
        
    Returns:
        List of silence segments [(start, end), ...]
    """
    try:
        # Calculate energy in small windows
        window_size = int(0.1 * sample_rate)  # 100ms windows
        hop_size = window_size // 2
        
        silence_segments = []
        in_silence = False
        silence_start = 0
        
        for i in range(0, len(audio_data) - window_size, hop_size):
            window = audio_data[i:i + window_size]
            energy = np.sqrt(np.mean(window**2))
            
            if energy < threshold:
                if not in_silence:
                    silence_start = i / sample_rate
                    in_silence = True
            else:
                if in_silence:
                    silence_end = i / sample_rate
                    duration = silence_end - silence_start
                    
                    if duration >= min_silence_duration:
                        silence_segments.append((silence_start, silence_end))
                    
                    in_silence = False
        
        # Handle final silence
        if in_silence:
            silence_end = len(audio_data) / sample_rate
            duration = silence_end - silence_start
            if duration >= min_silence_duration:
                silence_segments.append((silence_start, silence_end))
        
        return silence_segments
        
    except Exception as e:
        logger.error(f"Error detecting silence: {e}")
        return []

def apply_noise_reduction(audio_data: np.ndarray, 
                         noise_floor: float = 0.01) -> np.ndarray:
    """
    Apply basic noise reduction
    
    Args:
        audio_data: Audio data
        noise_floor: Noise floor threshold
        
    Returns:
        Noise-reduced audio
    """
    try:
        # Simple noise gating
        mask = np.abs(audio_data) > noise_floor
        cleaned_audio = audio_data * mask
        
        # Smooth transitions to avoid clicks
        kernel_size = 5
        kernel = np.ones(kernel_size) / kernel_size
        smooth_mask = np.convolve(mask.astype(float), kernel, mode='same')
        smooth_mask = np.clip(smooth_mask, 0, 1)
        
        return audio_data * smooth_mask
        
    except Exception as e:
        logger.error(f"Error applying noise reduction: {e}")
        return audio_data
