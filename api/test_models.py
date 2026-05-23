"""
Pruebas unitarias para models.py - Integridad de Base de Datos
"""
import pytest
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError

from api.models import Usuario, Pregunta, Opcion


@pytest.mark.django_db
class TestUsuarioModel:
    """Pruebas para el modelo Usuario"""
    
    def test_usuario_creation_with_required_fields(self):
        """Verifica que se puede crear un usuario con campos requeridos"""
        usuario = Usuario.objects.create(
            nombre_usuario="Santiago",
            apellido_usuario="Rodríguez",
            correo="santiago@example.com",
            contrasena="hashed_password_here",
            rol="estudiante"
        )
        
        assert usuario.id_usuario is not None
        assert usuario.nombre_usuario == "Santiago"
        assert usuario.apellido_usuario == "Rodríguez"
        assert usuario.correo == "santiago@example.com"
        assert usuario.rol == "estudiante"
    
    def test_usuario_string_representation(self):
        """Verifica que el __str__ retorna nombre completo"""
        usuario = Usuario.objects.create(
            nombre_usuario="Pedro",
            apellido_usuario="Martínez",
            correo="pedro@example.com",
            contrasena="hash123",
            rol="profesor"
        )
        
        assert str(usuario) == "Pedro Martínez"
    
    def test_usuario_unique_email_constraint(self):
        """Verifica que el email debe ser único"""
        Usuario.objects.create(
            nombre_usuario="Ana",
            apellido_usuario="García",
            correo="ana@example.com",
            contrasena="hash123",
            rol="estudiante"
        )
        
        # Crear otro usuario con mismo email debe fallar
        with pytest.raises(IntegrityError):
            Usuario.objects.create(
                nombre_usuario="Otra",
                apellido_usuario="Persona",
                correo="ana@example.com",
                contrasena="hash456",
                rol="profesor"
            )
    
    def test_usuario_is_authenticated_property(self):
        """Verifica que is_authenticated siempre retorna True"""
        usuario = Usuario.objects.create(
            nombre_usuario="Test",
            apellido_usuario="User",
            correo="test@example.com",
            contrasena="hash123",
            rol="estudiante"
        )
        
        assert usuario.is_authenticated is True
    
    def test_usuario_is_anonymous_property(self):
        """Verifica que is_anonymous siempre retorna False"""
        usuario = Usuario.objects.create(
            nombre_usuario="Test",
            apellido_usuario="User",
            correo="test@example.com",
            contrasena="hash123",
            rol="estudiante"
        )
        
        assert usuario.is_anonymous is False


@pytest.mark.django_db
class TestPreguntaOpcionRelationship:
    """Pruebas para la relación Pregunta-Opcion"""
    
    def test_pregunta_opcion_foreign_key_relationship(self):
        """Verifica que se puede crear una Opción vinculada a Pregunta"""
        pregunta = Pregunta.objects.create(
            enunciado="¿Cuál es la capital de España?",
            figura_correcta_canva="figura1.svg",
            retro_trazado="Well done!"
        )
        
        opcion = Opcion.objects.create(
            texto_opcion="Madrid",
            pregunta=pregunta,
            es_correcta=True
        )
        
        assert opcion.pregunta == pregunta
        assert opcion.es_correcta is True
    
    def test_pregunta_opcion_protect_delete(self):
        """Verifica que no se pueda eliminar una Pregunta con Opciones asociadas"""

        pregunta = Pregunta.objects.create(
            enunciado="Test question",
            retro_trazado="Feedback"
        )

        Opcion.objects.create(
            texto_opcion="Option A",
            pregunta=pregunta,
            es_correcta=True
        )

        Opcion.objects.create(
            texto_opcion="Option B",
            pregunta=pregunta,
            es_correcta=False
        )

        assert Opcion.objects.filter(pregunta=pregunta).count() == 2

        # Verificar que no puede eliminarse
        with pytest.raises(ProtectedError):
            pregunta.delete()

        # La pregunta y sus opciones siguen existiendo
        assert Pregunta.objects.filter(id_pregunta=pregunta.id_pregunta).exists()
        assert Opcion.objects.filter(pregunta=pregunta).count() == 2
