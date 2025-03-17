import json
import os
from pathlib import Path
from typing import Any, Dict, List, Union

from global_config.settings import DATA_ROOT


CACHE_PATH = DATA_ROOT / "data_cache.json"



def dump_to_json(data: Union[Dict[str, Any], List[Any]], filepath: Union[str, Path] = CACHE_PATH) -> None:
    """
    Dump dictionary or list data to a JSON file at the specified path.
    
    Args:
        data: Dictionary or list to be written to JSON
        filepath: Path where JSON file should be written, either as string or Path object
    
    Raises:
        IOError: If there are issues writing to the file
        TypeError: If data is not JSON serializable
    """
    # Convert string path to Path object if needed
    if isinstance(filepath, str):
        filepath = Path(filepath)
        
    # Create parent directories if they don't exist
    filepath.parent.mkdir(parents=True, exist_ok=True)
    cache_data = load_from_json(filepath)
    if cache_data:
        cache_data.update(data)
        data = cache_data
    data_dump = json.dumps(data, indent=4, ensure_ascii=False)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(data_dump)
            # json.dump(data, f, indent=4, ensure_ascii=False)
    except (IOError, TypeError) as e:
        print(f"Error writing to JSON file: {e}")
        raise

def load_and_get_key(key: str, filepath: Union[str, Path] = CACHE_PATH) -> Union[Dict[str, Any], List[Any]]:
    data = load_from_json(filepath)
    if not data:
        return None
    return data[key] if key in data else None

def load_from_json(filepath: Union[str, Path] = CACHE_PATH) -> Union[Dict[str, Any], List[Any]]:
    """
    Load data from a JSON file at the specified path.
    
    Args:
        filepath: Path to JSON file, either as string or Path object
        
    Returns:
        Dictionary or list loaded from the JSON file
        
    Raises:
        FileNotFoundError: If the specified file does not exist
        json.JSONDecodeError: If the file contains invalid JSON
        IOError: If there are issues reading the file
    """
    # Convert string path to Path object if needed
    if isinstance(filepath, str):
        filepath = Path(filepath)
        
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in file {filepath}: {e}")
        raise
    except IOError as e:
        print(f"Error reading JSON file: {e}")
        raise

def cache_result(cache_file: Union[str, Path] = CACHE_PATH):
    """
    Decorator that caches function/method return values to a JSON file.
    
    The cache key is constructed from:
    - Function name
    - Stringified positional and keyword arguments (with special handling for dicts)
    - For methods, the instance's class name is also included
    
    Args:
        cache_file: Path to JSON cache file, either as string or Path object
        
    Returns:
        Decorated function that implements caching behavior
        
    Example:
        @cache_result()
        def expensive_operation(x, y):
            # Complex computation
            return result
            
        @cache_result('custom_cache.json') 
        def another_operation(a, b, c=None):
            # Another expensive operation
            return result
    """
    def decorator(func):
        def dict_to_str(d: Dict) -> str:
            """Convert dictionary to deterministic string representation."""
            # Sort dictionary items and convert to string
            return json.dumps(d.items(), sort_keys=True)
            
        def arg_to_str(arg: Any) -> str:
            """Convert argument to string with special handling for dictionaries."""
            if isinstance(arg, dict):
                return dict_to_str(arg)
            elif isinstance(arg, list) or isinstance(arg, tuple) or isinstance(arg, set):
                return json.dumps(sorted(list(arg)))
            else:
                return str(arg)
            
        def create_cache_key(*args, **kwargs):
            # For methods, include class name in key
            if args and hasattr(args[0], '__class__'):
                prefix = f"{args[0].__class__.__name__}.{func.__name__}"
                # Remove self/cls from args
                args = args[1:]
            else:
                prefix = func.__name__
                
            # Convert args/kwargs to strings with special dict handling
            args_str = ','.join(map(arg_to_str, args))
            kwargs_str = ','.join(f"{k}={arg_to_str(v)}" for k, v in sorted(kwargs.items()))
            
            return f"{prefix}|{args_str}|{kwargs_str}"
            
        def wrapper(*args, **kwargs):
            cache_key = create_cache_key(*args, **kwargs)
            
            try:
                # Load existing cache
                cache = load_from_json(cache_file)
            except (FileNotFoundError, json.JSONDecodeError):
                cache = {}
                
            # Return cached result if it exists
            if cache_key in cache:
                return cache[cache_key]
                
            # Calculate and cache result
            result = func(*args, **kwargs)
            cache[cache_key] = result
            dump_to_json(cache, cache_file)
            
            return result
            
        return wrapper
    return decorator

caching_decorator = cache_result()
