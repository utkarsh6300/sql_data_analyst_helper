from typing import Union
import hashlib

def deterministic_uuid(data: Union[str, bytes]) -> str:
    """
    Generate a deterministic UUID based on input data using SHA-256.
    
    Args:
        data (Union[str, bytes]): Input string or bytes to generate UUID from
        
    Returns:
        str: A deterministic UUID-like string (first 32 chars of SHA-256 hex)
        
    Raises:
        ValueError: If data is empty or None
        TypeError: If data is not a string or bytes
    """
    if not data:
        raise ValueError("Input data cannot be empty or None")
        
    if not isinstance(data, (str, bytes)):
        raise TypeError("Input data must be a string or bytes")
    
    try:
        if isinstance(data, str):
            data = data.encode()
        return hashlib.sha256(data).hexdigest()[:32]
    except Exception as e:
        raise RuntimeError(f"Failed to generate UUID: {str(e)}") from e