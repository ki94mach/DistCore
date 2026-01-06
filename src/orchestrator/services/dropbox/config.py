"""Configuration loading for Dropbox connections using Windows Credential Manager."""

import os
import yaml
import base64
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Windows Credential Manager target name for Dropbox token
DROPBOX_CREDENTIAL_TARGET = "DistCore_Dropbox_AccessToken"
DROPBOX_REFRESH_TOKEN_TARGET = "DistCore_Dropbox_RefreshToken"
DROPBOX_APP_KEY_TARGET = "DistCore_Dropbox_AppKey"
DROPBOX_APP_SECRET_TARGET = "DistCore_Dropbox_AppSecret"


class DropboxConfigLoader:
    """
    Responsible for loading Dropbox configuration from Windows Credential Manager,
    environment variables, or direct parameter.
    
    Priority order:
    1. Direct access_token parameter
    2. Windows Credential Manager (if keyring is available)
    3. Environment variable DROPBOX_ACCESS_TOKEN
    """
    
    def __init__(self, access_token: Optional[str] = None, use_windows_auth: bool = True):
        """
        Initialize the Dropbox config loader.
        
        Args:
            access_token: Optional Dropbox access token. If not provided, will try to load from
                        Windows Credential Manager or environment variable.
            use_windows_auth: If True, attempt to load from Windows Credential Manager first.
                            Defaults to True.
        """
        self._access_token = access_token
        self._use_windows_auth = use_windows_auth and KEYRING_AVAILABLE
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load Dropbox configuration with support for multiple authentication methods.
        
        Supported methods:
        - access_token: Direct access token (legacy)
        - oauth_refresh: OAuth 2.0 with refresh token (auto-refreshes expired tokens)
        - app_key_secret: App-level authentication using app key and secret
        
        Returns:
            Dictionary containing authentication information:
            - For access_token: {'access_token': '...'}
            - For oauth_refresh: {'access_token': '...', 'refresh_token': '...', 'app_key': '...', 'app_secret': '...'}
            - For app_key_secret: {'app_key': '...', 'app_secret': '...'}
            
        Raises:
            ValueError: If authentication configuration is not found or invalid
        """
        # Priority 1: Direct parameter (legacy support)
        if self._access_token:
            return {'access_token': self._access_token, 'auth_method': 'access_token'}
        
        # Priority 2: Load from config file
        try:
            config_path = self._get_default_config_file_path()
            if config_path.exists():
                with open(config_path, 'r') as config_file:
                    yaml_config = yaml.safe_load(config_file)
                
                if yaml_config and 'dropbox' in yaml_config:
                    dropbox_config = yaml_config['dropbox']
                    auth_method = dropbox_config.get('auth_method', 'access_token')
                    
                    if auth_method == 'oauth_refresh':
                        return self._load_oauth_refresh_config(dropbox_config)
                    elif auth_method == 'app_key_secret':
                        return self._load_app_key_secret_config(dropbox_config)
                    elif auth_method == 'access_token':
                        # Check if access_token is in the config file
                        if 'access_token' in dropbox_config:
                            return {
                                'access_token': dropbox_config['access_token'],
                                'auth_method': 'access_token'
                            }
                    # Fall through to legacy access_token methods if not in config file
        except Exception:
            # If config file loading fails, fall through to other methods
            pass
        
        # Priority 3: Legacy access token methods (Windows Credential Manager, env var)
        return self._load_legacy_access_token_config()
    
    def _load_oauth_refresh_config(self, dropbox_config: Dict[str, Any]) -> Dict[str, Any]:
        """Load OAuth refresh token configuration."""
        # Try to get from config file first
        app_key = dropbox_config.get('app_key') or os.getenv('DROPBOX_APP_KEY')
        app_secret = dropbox_config.get('app_secret') or os.getenv('DROPBOX_APP_SECRET')
        refresh_token = dropbox_config.get('refresh_token') or os.getenv('DROPBOX_REFRESH_TOKEN')
        
        # Try Windows Credential Manager
        if not app_key and self._use_windows_auth:
            try:
                username = os.getlogin()
            except (OSError, AttributeError):
                username = os.getenv('USERNAME') or os.getenv('USER') or 'default'
            app_key = keyring.get_password(DROPBOX_APP_KEY_TARGET, username)
            app_secret = keyring.get_password(DROPBOX_APP_SECRET_TARGET, username)
            refresh_token = keyring.get_password(DROPBOX_REFRESH_TOKEN_TARGET, username)
        
        if not all([app_key, app_secret, refresh_token]):
            raise ValueError(
                "OAuth refresh token configuration incomplete. "
                "Required: app_key, app_secret, refresh_token. "
                "Set in dropbox.yml config file or environment variables."
            )
        
        # Get or refresh access token
        access_token = self._refresh_access_token(app_key, app_secret, refresh_token)
        
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'app_key': app_key,
            'app_secret': app_secret,
            'auth_method': 'oauth_refresh'
        }
    
    def _load_app_key_secret_config(self, dropbox_config: Dict[str, Any]) -> Dict[str, Any]:
        """Load app key/secret configuration."""
        app_key = dropbox_config.get('app_key') or os.getenv('DROPBOX_APP_KEY')
        app_secret = dropbox_config.get('app_secret') or os.getenv('DROPBOX_APP_SECRET')
        
        # Try Windows Credential Manager
        if not app_key and self._use_windows_auth:
            try:
                username = os.getlogin()
            except (OSError, AttributeError):
                username = os.getenv('USERNAME') or os.getenv('USER') or 'default'
            app_key = keyring.get_password(DROPBOX_APP_KEY_TARGET, username)
            app_secret = keyring.get_password(DROPBOX_APP_SECRET_TARGET, username)
        
        if not all([app_key, app_secret]):
            raise ValueError(
                "App key/secret configuration incomplete. "
                "Required: app_key, app_secret. "
                "Set in dropbox.yml config file or environment variables."
            )
        
        # Generate app auth token
        access_token = self._get_app_auth_token(app_key, app_secret)
        
        return {
            'access_token': access_token,
            'app_key': app_key,
            'app_secret': app_secret,
            'auth_method': 'app_key_secret'
        }
    
    def _load_legacy_access_token_config(self) -> Dict[str, Any]:
        """Load legacy access token configuration."""
        # Windows Credential Manager
        if self._use_windows_auth:
            try:
                try:
                    username = os.getlogin()
                except (OSError, AttributeError):
                    username = os.getenv('USERNAME') or os.getenv('USER') or 'default'
                
                token = keyring.get_password(DROPBOX_CREDENTIAL_TARGET, username)
                if token:
                    return {'access_token': token, 'auth_method': 'access_token'}
            except Exception:
                pass
        
        # Environment variable
        token = os.getenv('DROPBOX_ACCESS_TOKEN')
        if token:
            return {'access_token': token, 'auth_method': 'access_token'}
        
        # No token found
        error_msg = (
            "Dropbox access token not found. "
            "Please use one of the following methods:\n"
            "1. Set DROPBOX_ACCESS_TOKEN environment variable\n"
            "2. Configure OAuth refresh tokens in dropbox.yml (recommended)\n"
            "3. Configure app key/secret in dropbox.yml\n"
        )
        
        if self._use_windows_auth:
            try:
                username = os.getlogin()
            except (OSError, AttributeError):
                username = os.getenv('USERNAME') or os.getenv('USER') or 'default'
            
            error_msg += (
                f"4. Store token in Windows Credential Manager using:\n"
                f"   python scripts/store_dropbox_token.py\n"
            )
        
        raise ValueError(error_msg)
    
    def _refresh_access_token(self, app_key: str, app_secret: str, refresh_token: str) -> str:
        """Refresh an OAuth access token using refresh token."""
        if not REQUESTS_AVAILABLE:
            raise ImportError(
                "requests package is required for OAuth refresh. Install it with: pip install requests"
            )
        
        url = "https://api.dropbox.com/oauth2/token"
        auth_str = base64.b64encode(f"{app_key}:{app_secret}".encode()).decode()
        
        headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        
        result = response.json()
        return result['access_token']
    
    def _get_app_auth_token(self, app_key: str, app_secret: str) -> str:
        """Get app authentication token using app key and secret."""
        if not REQUESTS_AVAILABLE:
            raise ImportError(
                "requests package is required for app authentication. Install it with: pip install requests"
            )
        
        url = "https://api.dropbox.com/oauth2/token"
        auth_str = base64.b64encode(f"{app_key}:{app_secret}".encode()).decode()
        
        headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "client_credentials"
        }
        
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        
        result = response.json()
        return result['access_token']
    
    @staticmethod
    def store_token_in_windows_credential_manager(token: str, username: Optional[str] = None) -> None:
        """
        Store Dropbox access token in Windows Credential Manager.
        
        Args:
            token: Dropbox access token to store
            username: Optional username (defaults to current Windows user)
            
        Raises:
            ImportError: If keyring is not installed
            Exception: If storing fails
        """
        if not KEYRING_AVAILABLE:
            raise ImportError(
                "keyring package is required for Windows Credential Manager support. "
                "Install it with: pip install keyring"
            )
        
        if username is None:
            try:
                username = os.getlogin()
            except (OSError, AttributeError):
                username = os.getenv('USERNAME') or os.getenv('USER') or 'default'
        
        try:
            keyring.set_password(DROPBOX_CREDENTIAL_TARGET, username, token)
        except Exception as e:
            raise Exception(f"Failed to store token in Windows Credential Manager: {str(e)}")
    
    @staticmethod
    def delete_token_from_windows_credential_manager(username: Optional[str] = None) -> None:
        """
        Delete Dropbox access token from Windows Credential Manager.
        
        Args:
            username: Optional username (defaults to current Windows user)
            
        Raises:
            ImportError: If keyring is not installed
        """
        if not KEYRING_AVAILABLE:
            raise ImportError(
                "keyring package is required for Windows Credential Manager support. "
                "Install it with: pip install keyring"
            )
        
        if username is None:
            try:
                username = os.getlogin()
            except (OSError, AttributeError):
                username = os.getenv('USERNAME') or os.getenv('USER') or 'default'
        
        try:
            keyring.delete_password(DROPBOX_CREDENTIAL_TARGET, username)
        except keyring.errors.PasswordDeleteError:
            # Password doesn't exist, that's okay
            pass
        except Exception as e:
            raise Exception(f"Failed to delete token from Windows Credential Manager: {str(e)}")
    
    @property
    def access_token(self) -> str:
        """Get the Dropbox access token."""
        config = self.load_config()
        return config['access_token']
    
    @staticmethod
    def _get_default_config_file_path() -> Path:
        """
        Get the default path to the Dropbox configuration file.
        """
        current_file_directory = Path(__file__).parent.parent.parent
        return current_file_directory / 'config' / 'dropbox.yml'
    
    @staticmethod
    def load_folder_paths(config_file_path: Optional[Path] = None) -> Dict[str, str]:
        """
        Load Dropbox folder paths from YAML configuration file.
        
        Args:
            config_file_path: Optional path to configuration YAML file. 
                            If None, uses default path.
        
        Returns:
            Dictionary containing folder paths (e.g., {'distributor_deliveries_folder': '/Data/Deliveries'})
        
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid
        """
        config_path = config_file_path or DropboxConfigLoader._get_default_config_file_path()
        
        if not config_path.exists():
            raise FileNotFoundError(
                f"Dropbox configuration file not found: {config_path}"
            )
        
        with open(config_path, 'r') as config_file:
            config = yaml.safe_load(config_file)
        
        if not config or 'dropbox' not in config:
            raise ValueError("Invalid Dropbox configuration: 'dropbox' key not found")
        
        return config['dropbox']
    
    @staticmethod
    def get_distributor_deliveries_folder(config_file_path: Optional[Path] = None) -> str:
        """
        Get the distributor deliveries folder path from configuration.
        
        Args:
            config_file_path: Optional path to configuration YAML file.
                            If None, uses default path.
        
        Returns:
            Folder path string (e.g., '/Data/Deliveries')
        
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid or folder path not found
        """
        folder_paths = DropboxConfigLoader.load_folder_paths(config_file_path)
        
        if 'distributor_deliveries_folder' not in folder_paths:
            raise ValueError(
                "Invalid Dropbox configuration: 'distributor_deliveries_folder' not found"
            )
        
        return folder_paths['distributor_deliveries_folder']

