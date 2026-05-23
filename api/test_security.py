"""
Pruebas unitarias para security.py - Autenticación y Seguridad
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
from django.conf import settings

from api.security import (
    hash_password,
    verify_password,
    is_bcrypt_hash,
    create_access_token,
    _encode_jwt,
    _decode_jwt,
    AuthTokenError,
    _token_hash,
)


class TestPasswordHashing:
    """Pruebas para hashing y verificación de contraseñas"""
    
    def test_hash_password_creates_valid_bcrypt_hash(self):
        """Verifica que hash_password crea un hash bcrypt válido"""
        raw_password = "SuperPassword123!"
        hashed = hash_password(raw_password)
        
        # El hash debe ser válido y empezar con prefijo bcrypt
        assert is_bcrypt_hash(hashed)
        assert hashed != raw_password
        assert len(hashed) >= 60  # Longitud típica de bcrypt
    
    def test_verify_password_validates_correctly(self):
        """Verifica que verify_password compara correctamente contraseñas"""
        raw_password = "CorrectPassword456"
        hashed = hash_password(raw_password)
        
        # Contraseña correcta debe verificar
        assert verify_password(raw_password, hashed) is True
        
        # Contraseña incorrecta debe fallar
        assert verify_password("WrongPassword", hashed) is False
    
    def test_hash_password_raises_on_empty_password(self):
        """Verifica que hash_password rechaza contraseña vacía"""
        with pytest.raises(ValueError, match="contrasena no puede estar vacia"):
            hash_password("")
        
        with pytest.raises(ValueError):
            hash_password(None)
    
    def test_verify_password_handles_edge_cases(self):
        """Verifica que verify_password maneja casos límite"""
        # Ambos vacíos
        assert verify_password("", "") is False
        
        # Uno vacío
        assert verify_password("password", "") is False
        assert verify_password("", "$2b$12$abcdef") is False
        
        # Ambos None
        assert verify_password(None, None) is False
        
        # Hash inválido
        assert verify_password("password", "not_a_valid_hash") is False


class TestJWTTokens:
    """Pruebas para creación y validación de JWT tokens"""
    
    def test_create_access_token_generates_valid_jwt(self):
        """Verifica que create_access_token genera un JWT válido"""
        usuario_mock = Mock()
        usuario_mock.id_usuario = 1
        usuario_mock.rol = "estudiante"
        
        token = create_access_token(usuario_mock)
        
        # Token debe ser string
        assert isinstance(token, str)
        
        # Token debe poder ser decodificado
        payload = _decode_jwt(token)
        assert payload["sub"] == "1"
        assert payload["rol"] == "estudiante"
        assert payload["type"] == "access"
    
    def test_create_access_token_includes_required_claims(self):
        """Verifica que el token incluye todos los claims requeridos"""
        usuario_mock = Mock()
        usuario_mock.id_usuario = 42
        usuario_mock.rol = "profesor"
        
        token = create_access_token(usuario_mock)
        payload = _decode_jwt(token)
        
        # Claims requeridos
        assert "sub" in payload
        assert "rol" in payload
        assert "type" in payload
        assert "iat" in payload  # issued at
        assert "exp" in payload  # expiration
        
        assert payload["sub"] == "42"
        assert payload["rol"] == "profesor"
        assert payload["type"] == "access"
    
    def test_token_hash_produces_sha256_hash(self):
        """Verifica que _token_hash produce un SHA256 válido"""
        raw_token = "test_token_string"
        hash_result = _token_hash(raw_token)
        
        # SHA256 produce 64 caracteres hexadecimales
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)
        
        # Mismo input debe producir mismo hash
        assert _token_hash(raw_token) == hash_result
    
    def test_decode_jwt_raises_on_invalid_token(self):
        """Verifica que _decode_jwt rechaza tokens inválidos"""
        with pytest.raises(AuthTokenError, match="Token inválido"):
            _decode_jwt("invalid.token.string")
        
        with pytest.raises(AuthTokenError):
            _decode_jwt("")
