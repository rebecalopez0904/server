"""
Pruebas unitarias para serializers.py - Validación de Datos
"""
import pytest
from rest_framework import serializers
from unittest.mock import patch, Mock

from api.serializers import (
    AuthRegisterSerializer,
    UsuarioSerializer,
)
from api.models import Usuario


class TestAuthRegisterSerializer:
    """Pruebas para validación de registro de usuarios"""
    
    def test_register_serializer_validates_valid_data(self):
        """Verifica que el serializador acepta datos válidos"""
        valid_data = {
            "nombre_usuario": "Juan",
            "apellido_usuario": "Pérez",
            "correo": "juan@example.com",
            "contrasena": "SecurePass123",
            "rol": "estudiante",
        }
        
        serializer = AuthRegisterSerializer(data=valid_data)
        assert serializer.is_valid()
        assert serializer.errors == {}
    
    def test_register_serializer_rejects_short_password(self):
        """Verifica que rechaza contraseñas menores a 8 caracteres"""
        invalid_data = {
            "nombre_usuario": "Juan",
            "apellido_usuario": "Pérez",
            "correo": "juan@example.com",
            "contrasena": "Short12",  # 7 caracteres
            "rol": "estudiante",
        }
        
        serializer = AuthRegisterSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert "contrasena" in serializer.errors
    
    def test_register_serializer_validates_email(self):
        """Verifica que valida formato de email"""
        invalid_email_data = {
            "nombre_usuario": "Juan",
            "apellido_usuario": "Pérez",
            "correo": "not_an_email",
            "contrasena": "SecurePass123",
            "rol": "estudiante",
        }
        
        serializer = AuthRegisterSerializer(data=invalid_email_data)
        assert not serializer.is_valid()
        assert "correo" in serializer.errors
    
    def test_register_serializer_validates_role_choices(self):
        """Verifica que valida roles permitidos"""
        invalid_role_data = {
            "nombre_usuario": "Juan",
            "apellido_usuario": "Pérez",
            "correo": "juan@example.com",
            "contrasena": "SecurePass123",
            "rol": "admin",  # Rol no permitido
        }
        
        serializer = AuthRegisterSerializer(data=invalid_role_data)
        assert not serializer.is_valid()
        assert "rol" in serializer.errors


@pytest.mark.django_db
class TestUsuarioSerializer:
    """Pruebas para serialización de Usuario con hashing de contraseña"""
    
    def test_usuario_serializer_hashes_password_on_create(self):
        """Verifica que la contraseña se hashea al crear un usuario"""
        valid_data = {
            "nombre_usuario": "Carlos",
            "apellido_usuario": "López",
            "correo": "carlos@example.com",
            "contrasena": "MyPassword789",
            "rol": "profesor",
        }
        
        serializer = UsuarioSerializer(data=valid_data)
        assert serializer.is_valid()
        
        usuario = serializer.save()
        
        # La contraseña no debe ser la original
        assert usuario.contrasena != "MyPassword789"
        
        # La contraseña debe empezar con prefijo bcrypt
        assert usuario.contrasena.startswith("$2a$") or \
               usuario.contrasena.startswith("$2b$") or \
               usuario.contrasena.startswith("$2y$")
    
    def test_usuario_serializer_validates_password_length(self):
        """Verifica que valida longitud mínima de contraseña"""
        short_password_data = {
            "nombre_usuario": "María",
            "apellido_usuario": "García",
            "correo": "maria@example.com",
            "contrasena": "Short1",  # Menos de 8 caracteres
            "rol": "estudiante",
        }
        
        serializer = UsuarioSerializer(data=short_password_data)
        assert not serializer.is_valid()
        assert "contrasena" in serializer.errors
